"""智能交易 · 平仓编排(智能交易 PR-5)· 🔴纯虚拟绝不真单。

monitor beat:逐个 intelligent 活仓查三退出(★做多做空对称 · 优先级 止损 > 止盈 > 信号反转):
  ① ATR 止损:开多 标记价 ≤ stop / 开空 标记价 ≥ stop(intelligent_stop_price · PR-4 开仓时记)
  ② 2:1 止盈:开多 标记价 ≥ tp / 开空 标记价 ≤ tp(intelligent_tp_price)
  ③ 信号反转:重算当前方向分(build_decisions 读两快照)· 开多 score < 0 / 开空 score > 0(穿过中性)
满足任一 → route_close_perp(★平仓唯一入口 · close_all)→ post-close 写 intelligent_close_reason。

★★开关只控【新开仓】(open_scan)· 平仓监控【不被开关 OFF 拦】:已有 intelligent 仓必须被监控平仓 ——
  否则关开关 = 持仓永不平 · 危险。「空转零副作用」靠【无 intelligent 活仓查询空 → return】。
★保留强平兜底:intelligent 仓 managed=False 自然进强平扫描(ATR 止损先触发 ~20% · 强平 100% 极端
  兜底 · 双层风控)· ★PR-5 不碰强平 worker(diff 空)。
★唯一入口铁律:平仓【只】调 route_close_perp · 不重写撮合/盈亏 · 引擎枚举 PerpCloseReason 零碰
  (智能平仓原因记自己的 intelligent_close_reason 列 · post-close 在编排层写)。
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.perp import PerpSide, VirtualPerpPosition
from app.models.virtual import OrderStatus
from app.services.virtual_trading.intelligent import account as iacc
from app.services.virtual_trading.intelligent import guard as iguard
from app.services.virtual_trading.intelligent import strategy as istrategy
from app.services.virtual_trading.perp_dispatcher import route_close_perp

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_BOLL_KEY = "boll:snapshot:latest"
_SIGNALS_KEY = "intelligent:signals:latest"


async def _read_items(redis: Any, key: str) -> list[dict[str, Any]]:
    """读快照 → items 列表(仿 open · 缺/坏 → 空)。"""
    raw = await redis.get(key)
    if not raw:
        return []
    data = json.loads(raw)
    items = data.get("items", []) if isinstance(data, dict) else []
    return [x for x in items if isinstance(x, dict)]


def _exit_reason(
    pos: VirtualPerpPosition,
    mark: Decimal | None,
    decision: istrategy.StrategyDecision | None,
) -> str | None:
    """三退出判定(★做多做空对称 · 优先级 止损 > 止盈 > 信号反转)· 都不满足 → None。

    ★做多做空相反:开多止损在下/止盈在上,开空止损在上/止盈在下。
    decision = build_decisions 重算的当前决策(可 None=当前快照无该币 → 不触信号反转,留止损止盈)。
    """
    if mark is None:
        return None
    is_long = pos.side == PerpSide.LONG
    stop = pos.intelligent_stop_price
    tp = pos.intelligent_tp_price
    # ① ATR 止损(优先级最高)
    if stop is not None:
        if is_long and mark <= stop:
            return "stop_loss"
        if not is_long and mark >= stop:
            return "stop_loss"
    # ② 2:1 止盈
    if tp is not None:
        if is_long and mark >= tp:
            return "take_profit"
        if not is_long and mark <= tp:
            return "take_profit"
    # ③ 信号反转(重算当前方向分 · 开多 score 跌破 0 / 开空 score 升破 0 · 穿过中性即离场)
    if decision is not None:
        if is_long and decision.score < 0:
            return "signal_reversal"
        if not is_long and decision.score > 0:
            return "signal_reversal"
    return None


async def run_intelligent_close(
    session: AsyncSession,
    redis: Any,
    get_mark_price: Callable[[str], Awaitable[Decimal | None]],
) -> dict[str, Any]:
    """监控所有 intelligent 活仓 → 三退出即 route_close_perp + 记 intelligent_close_reason。

    ★不被开关 OFF 拦(已有仓必须被监控)· 无活仓 → {"status":"ok","closed":[]}(空转零副作用)。
    """
    uid = await iacc.get_intelligent_user_id(session)
    if uid is None:
        return {"status": "skip", "reason": "no_account"}  # 智能账户没建过 → 无仓可监控

    positions = list(await session.scalars(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.intelligent.is_(True),
            VirtualPerpPosition.closed_at.is_(None),
        ),
    ))
    if not positions:
        return {"status": "ok", "closed": []}  # 无 intelligent 活仓 → 空转

    # ★读两快照重算当前方向分(信号反转用)· 当前快照无该币 → decisions 无 → 只止损止盈
    boll_items = await _read_items(redis, _BOLL_KEY)
    signal_items = await _read_items(redis, _SIGNALS_KEY)
    # ★信号反转判 score 穿 0 · 用与开仓一致的 weights 重算(Redis · 即时生效)
    weights = await iguard.get_strategy_weights(redis)
    decisions = {
        d.symbol: d
        for d in istrategy.build_decisions(boll_items, signal_items, weights=weights)
    }

    closed: list[tuple[str, str]] = []
    for pos in positions:
        symbol = pos.symbol
        mark = await get_mark_price(symbol)
        reason = _exit_reason(pos, mark, decisions.get(symbol))
        if reason is None:
            continue
        try:
            order = await route_close_perp(
                session,
                user_id=uid,
                symbol=symbol,
                quantity=None,
                close_all=True,  # ★全平(系统账户同币去重 · 平的就这一仓)
                get_mark_price=get_mark_price,
            )
            if order.status == OrderStatus.FILLED:
                pos.intelligent_close_reason = reason  # ★post-close 写智能原因(引擎枚举零碰)
                await session.commit()
                closed.append((symbol, reason))
                logger.info("[intelligent] ✓ 平仓 %s · 原因=%s", symbol, reason)
            else:
                await session.rollback()
                logger.info("[intelligent] 平仓被拒 %s · %s", symbol, order.reject_reason)
        except Exception:  # noqa: BLE001 · 单仓失败隔离
            await session.rollback()
            logger.exception("[intelligent] 平仓异常 %s", symbol)

    logger.info("[intelligent] 平仓监控 · 活仓 %d 平了 %d:%s", len(positions), len(closed), closed)
    return {"status": "ok", "closed": closed}
