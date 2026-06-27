"""托管交易 · 平仓编排(托管交易 PR-3)· 🔴纯虚拟绝不真单。

monitor beat:逐个 managed 活仓查三种退出(统一一个监控逻辑 · 不复用 conditional_order):
  ① 止盈 TP:LONG · 标记价 ≥ entry_price × 1.20(涨 20% = 盈利 100% @ 5x)
  ② 信号转换:当前 bias ≠ 偏多(boll 快照该币离开偏多)
  ③ 超时:now − opened_at > 24h
满足任一 → route_close_perp(★平仓唯一入口 · close_all)→ post-close 写 managed_close_reason。

★★开关只控【新开仓】(open_scan)· 平仓监控【不被开关 OFF 拦】:已有 managed 仓必须被监控平仓 ——
  否则【禁强平 + 平仓监控也停 = 持仓单永不平】危险。关开关 = 停新开仓 + 继续平已有仓 → 干净退出。
  「空转零副作用」靠【无 managed 活仓时查询空 → return】,不靠开关。
★唯一入口铁律:平仓【只】调 route_close_perp · 不重写撮合/盈亏 · 引擎枚举 PerpCloseReason 零碰
  (托管平仓原因记自己的 managed_close_reason 列 · post-close 在编排层写)。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.perp import VirtualPerpPosition
from app.models.virtual import OrderStatus
from app.services.virtual_trading.managed import account as macc
from app.services.virtual_trading.perp_dispatcher import route_close_perp

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_SNAPSHOT_KEY = "boll:snapshot:latest"
_LONG_BIAS = "偏多"
TP_MULTIPLIER = Decimal("1.20")  # 止盈:标记价 ≥ entry × 1.20(涨 20% = ROI 100% @ 5x)
TIMEOUT_HOURS = 24


async def _read_bias_map(redis: Any) -> dict[str, str]:
    """boll 快照 → {symbol: bias}(信号转换判定:当前 bias 离开偏多)。"""
    raw = await redis.get(_SNAPSHOT_KEY)
    if not raw:
        return {}
    data = json.loads(raw)
    items = data.get("items", []) if isinstance(data, dict) else []
    return {
        str(x["symbol"]): str(x.get("bias") or "")
        for x in items
        if isinstance(x, dict) and x.get("symbol")
    }


def _exit_reason(
    pos: VirtualPerpPosition, mark: Decimal | None, bias: str | None, now: datetime,
) -> str | None:
    """三种退出判定(优先级 TP > 信号 > 超时)· 都不满足 → None(继续持有)。"""
    if mark is not None and mark >= pos.entry_price * TP_MULTIPLIER:
        return "tp"  # 止盈(LONG · 标记价涨到 entry×1.20)
    if bias is not None and bias != _LONG_BIAS:
        return "signal"  # 信号转换(离开偏多)
    if now - pos.opened_at > timedelta(hours=TIMEOUT_HOURS):
        return "timeout"  # 超时(持仓 > 24h)
    return None


async def run_managed_close(
    session: AsyncSession,
    redis: Any,
    get_mark_price: Callable[[str], Awaitable[Decimal | None]],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """监控所有 managed 活仓 → 满足 TP/信号/超时即 route_close_perp + 记 managed_close_reason。

    ★不被开关 OFF 拦(已有仓必须被监控)· 无活仓 → {"status":"ok","closed":[]}(空转零副作用)。
    """
    now = now or datetime.now(tz=UTC)
    uid = await macc.get_managed_user_id(session)
    if uid is None:
        return {"status": "skip", "reason": "no_account"}  # 托管账户没建过 → 无仓可监控

    positions = list(await session.scalars(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.managed.is_(True),
            VirtualPerpPosition.closed_at.is_(None),
        ),
    ))
    if not positions:
        return {"status": "ok", "closed": []}  # 无 managed 活仓 → 空转

    bias_map = await _read_bias_map(redis)
    closed: list[tuple[str, str]] = []
    for pos in positions:
        symbol = pos.symbol
        mark = await get_mark_price(symbol)
        reason = _exit_reason(pos, mark, bias_map.get(symbol), now)
        if reason is None:
            continue
        try:
            order = await route_close_perp(
                session,
                user_id=uid,
                symbol=symbol,
                quantity=None,
                close_all=True,  # ★全平
                get_mark_price=get_mark_price,
            )
            if order.status == OrderStatus.FILLED:
                pos.managed_close_reason = reason  # ★post-close 写托管原因(引擎枚举零碰)
                await session.commit()
                closed.append((symbol, reason))
                logger.info("[managed] ✓ 托管平仓 %s · 原因=%s", symbol, reason)
            else:
                await session.rollback()
                logger.info("[managed] 平仓被拒 %s · %s", symbol, order.reject_reason)
        except Exception:  # noqa: BLE001 · 单仓失败隔离
            await session.rollback()
            logger.exception("[managed] 平仓异常 %s", symbol)
    logger.info("[managed] 平仓监控 · 活仓 %d 平了 %d:%s", len(positions), len(closed), closed)
    return {"status": "ok", "closed": closed}
