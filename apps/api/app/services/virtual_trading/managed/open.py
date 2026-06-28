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

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.models.virtual import OrderStatus
from app.services.virtual_trading.managed import account as macc
from app.services.virtual_trading.managed import guard as mguard
from app.services.virtual_trading.perp_dispatcher import route_open_perp

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_SNAPSHOT_KEY = "boll:snapshot:latest"  # boll_scan 落 · 只读挑币(同自动托管源)
MANAGED_MARGIN_USDT = Decimal("100")    # 每单本金 100U(Hans 定)
MANAGED_LEVERAGE = 5                     # 5 倍杠杆
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
) -> dict[str, Any]:
    """守卫 → 选偏多 transition → 去重 → 每轮最多开 5 新单 → route_open_perp → 标 managed。

    ★每轮(单次扫描)最多开 MAX_PER_ROUND 个【新】单 · ★总活仓数不限(下轮可继续累积 · Hans 定)。
    任一守卫不过 → {"status":"skip","reason":...}· 返回开了哪些币。★per-币 commit 隔离失败。
    """
    if not await mguard.is_enabled(redis):
        return {"status": "skip", "reason": "disabled"}

    account = await macc.ensure_managed_account(session)
    # ★每轮最多开 MAX_PER_ROUND 个【新】单 · ★总活仓数不限(不查当前活仓当上限 · Hans 定:下轮可累积)
    picks = await _read_bullish_transition(redis)
    opened: list[str] = []
    for row in picks:
        if len(opened) >= mguard.MAX_PER_ROUND:  # ★只限本轮新开数,不限总持仓
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
                leverage=MANAGED_LEVERAGE,
                margin=MANAGED_MARGIN_USDT,
                quantity=None,
                preferred_mode=MarginMode.CROSS,  # ★全仓
                get_mark_price=get_mark_price,
            )
            if order.status == OrderStatus.FILLED and order.position_id is not None:
                await _mark_managed(session, order.position_id)  # ★标 managed
                await session.commit()
                opened.append(symbol)
                logger.info("[managed] ✓ 托管开仓 %s LONG 100U 5x", symbol)
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
