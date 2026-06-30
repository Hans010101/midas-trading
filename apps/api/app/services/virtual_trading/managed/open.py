"""托管交易 · 开仓编排(托管交易 PR-2)· 🔴纯虚拟绝不真单。

每轮(worker beat):守卫 → 选偏多 transition 币 → 去重(同币跳过)+ 并行≤5 → route_open_perp
(LONG/100U/5x/全仓)→ ★标 position.managed=True(post-open update · 零碰引擎)。

★唯一入口铁律:开仓【只】调 route_open_perp(虚拟撮合唯一入口)· 不重写撮合 · 不碰引擎内核。
★managed 标记:engine 建仓默认 managed=False,本编排在 route_open_perp 返回后 UPDATE 该仓为 True
(靠 order.position_id)· 引擎 perp_dispatcher/perp_cross_engine/perp_engine 一字不碰。
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import IntegrityError

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.models.virtual import OrderStatus, VirtualAccount
from app.services.virtual_trading import platinum
from app.services.virtual_trading.managed import account as macc
from app.services.virtual_trading.managed import guard as mguard
from app.services.virtual_trading.perp_dispatcher import route_open_perp

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_SNAPSHOT_KEY = "boll:snapshot:latest"  # boll_scan 落 · 只读挑币(同自动托管源)
# ★每单本金/杠杆改为可调(读 Redis · 见 guard.get_open_margin/get_open_leverage · 默认 100U/5x)
_LONG_BIAS = "偏多"

PerpPriceFetcher = "Callable[[str], Awaitable[Decimal | None]]"


async def _read_bullish_transition(redis: Any) -> list[dict[str, Any]]:
    """读 boll 快照 → 偏多 ∩ transition · 按 change_pct_24h 降序(最强势在前)。"""
    raw = await redis.get(_SNAPSHOT_KEY)
    if not raw:
        return []
    data = json.loads(raw)
    items = data.get("items", []) if isinstance(data, dict) else []
    picks = [
        x for x in items
        if isinstance(x, dict) and x.get("bias") == _LONG_BIAS and x.get("transition")
    ]
    picks.sort(key=lambda x: x.get("change_pct_24h") or 0.0, reverse=True)
    return picks


async def _mark_managed(session: AsyncSession, position_id: int) -> None:
    """★post-open:把引擎刚开的仓标 managed=True(零碰引擎 · 靠 order.position_id)。"""
    pos = await session.get(VirtualPerpPosition, position_id)
    if pos is not None:
        pos.managed = True
        pos.last_bias = _LONG_BIAS  # ★开仓记当时 bias(条件=偏多∩transition · 信号列/判平初值)
        await session.flush()


async def run_managed_open(
    session: AsyncSession,
    redis: Any,
    get_mark_price: Callable[[str], Awaitable[Decimal | None]],
    *,
    account: VirtualAccount | None = None,
    enabled_user_id: UUID | None = None,
) -> dict[str, Any]:
    """守卫 → 选偏多 transition → 去重 → 每轮≤5 ∧ 总数≤max → route_open_perp → 标 managed。

    ★三参数读 Redis(margin/leverage/max_positions · 即时生效)· ★本轮可开 = min(每轮≤5, max−当前活仓)
    两约束并存 · 任一守卫不过 → skip · per-币 commit 隔离失败。
    ★PR-4b per-user(路径 A · 向后兼容):account/enabled_user_id 默认 None = 旧全局路径一字不变
      (全局账户 + 全局开关·现在跑的托管交易走这条);给定 = 某铂金用户的影子账户 + per-user 开关。
    """
    if not await mguard.is_enabled(redis, enabled_user_id):
        return {"status": "skip", "reason": "disabled"}
    # ★PR-8 方向过滤(托管恒做多):allow_long OFF → 不开新仓(只 gate 开仓·close 零碰)
    if not await mguard.get_allow_long(redis, enabled_user_id):
        return {"status": "skip", "reason": "long_disabled"}

    if account is None:
        account = await macc.ensure_managed_account(session)
    # ★PR-7a 透 enabled_user_id:全局=None 读全局 key、影子=uid 读 per-user key(即时生效)
    margin = await mguard.get_open_margin(redis, enabled_user_id)
    leverage = await mguard.get_open_leverage(redis, enabled_user_id)
    max_positions = await mguard.get_max_positions(redis, enabled_user_id)
    current_open = await mguard.count_open_positions(session, account.id)
    # ★本轮可开 = min(每轮≤5, 总数上限剩余空间)· 两约束并存 · 负/0 → 不开(已达总上限)
    room = min(mguard.MAX_PER_ROUND, max_positions - current_open)
    picks = await _read_bullish_transition(redis)
    opened: list[str] = []
    for row in picks:
        if len(opened) >= room:  # ★到本轮可开上限(每轮≤5 AND 总数≤max 取小)
            break
        symbol = str(row.get("symbol") or "")
        if not symbol:
            continue
        if await mguard.has_open_position(session, account.id, symbol):
            continue  # ★同币不重复开
        try:
            order = await route_open_perp(
                session,
                user_id=account.user_id,
                symbol=symbol,
                side=PerpSide.LONG,       # ★只做多
                leverage=leverage,        # ★读 Redis(可调 1-20)
                margin=margin,            # ★读 Redis(可调 10-10000)
                quantity=None,
                preferred_mode=MarginMode.CROSS,  # ★全仓
                get_mark_price=get_mark_price,
            )
            if order.status == OrderStatus.FILLED and order.position_id is not None:
                await _mark_managed(session, order.position_id)  # ★标 managed
                await session.commit()
                opened.append(symbol)
                logger.info("[managed] ✓ 托管开仓 %s LONG %sU %sx", symbol, margin, leverage)
            else:
                await session.rollback()  # 拒单 → 回滚(不留半截)
                logger.info("[managed] 开仓被拒 %s · %s", symbol, order.reject_reason)
        except Exception:  # noqa: BLE001 · 单币失败隔离,不中断本轮
            await session.rollback()
            logger.exception("[managed] 开仓异常 %s", symbol)
    logger.info(
        "[managed] 开仓编排 · 本轮新开 %d(上限 %d · 总数不限):%s",
        len(opened), mguard.MAX_PER_ROUND, opened,
    )
    return {"status": "ok", "opened": opened, "per_round_cap": mguard.MAX_PER_ROUND}


# ── ★PR-4b:铂金 per-user 开仓(全局 loop 之外叠加 · 全局零影响)─────────────────
async def _ensure_shadow_managed_account(
    session: AsyncSession, user_id: UUID,
) -> VirtualAccount:
    """幂等建铂金用户托管影子账户 · 首建撞 User.email unique → rollback 重查兜底(不 500)。"""
    try:
        return await macc.ensure_managed_account_for_user(session, user_id)
    except IntegrityError:
        await session.rollback()  # ★另一并发已建 → 回滚后重查(幂等收敛)
        return await macc.ensure_managed_account_for_user(session, user_id)


async def run_managed_open_platinum(
    session: AsyncSession,
    redis: Any,
    get_mark_price: Callable[[str], Awaitable[Decimal | None]],
) -> list[dict[str, Any]]:
    """★铂金 per-user 开仓:遍历铂金用户 → 各自影子账户 + per-user 开关开仓。

    ★全局 loop 由 worker 先跑、本函数只【叠加】铂金,绝不碰全局(红线①)。
    ★每 uid 独立 try/except + rollback 隔离(单用户失败不连累全局/其他铂金)。
    ★每轮顶部先 ensure(撞 unique 兜底)→ session 干净后再开;开仓内 per-币 commit。
    """
    uids = await platinum.get_platinum_user_ids(session)
    results: list[dict[str, Any]] = []
    for uid in uids:
        try:
            account = await _ensure_shadow_managed_account(session, uid)
            r = await run_managed_open(
                session, redis, get_mark_price,
                account=account, enabled_user_id=uid,
            )
            results.append({"uid": str(uid), **r})
        except Exception:  # noqa: BLE001 · 单用户失败隔离(不连累全局/其他铂金)
            await session.rollback()
            logger.exception("[managed] per-user 开仓异常 uid=%s", uid)
            results.append({"uid": str(uid), "status": "error"})
    return results
