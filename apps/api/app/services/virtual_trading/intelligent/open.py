"""智能交易 · 开仓编排(智能交易 PR-4 · ★第一个真下单 · 虚拟引擎)· 🔴绝不真单。

每轮(worker beat):★守卫第一行 is_enabled OFF → 立刻 return(空转零副作用)· 读两快照
(boll + intelligent)→ build_decisions/open_decisions(PR-3 引擎)→ route_open_perp(★做多做空·
LONG/SHORT·100U/5x/全仓)→ post-open 标 intelligent=True + 记止损/止盈价 + 共振明细(零碰引擎)。

★唯一入口铁律:开仓【只】调 route_open_perp(虚拟撮合唯一入口)· 不重写撮合 · 引擎零碰
  (route_open_perp/open_cross_position/_find_crypto_account 一字不碰 · 靠系统账户 user_id 定位)。
★差异(vs managed):做多做空对称 · 每仓带 ATR 止损/止盈 · 并发不限(Hans 定)。
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.models.virtual import OrderStatus
from app.services.virtual_trading.intelligent import account as iacc
from app.services.virtual_trading.intelligent import guard as iguard
from app.services.virtual_trading.intelligent import strategy as istrategy
from app.services.virtual_trading.perp_dispatcher import route_open_perp

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_BOLL_KEY = "boll:snapshot:latest"
_SIGNALS_KEY = "intelligent:signals:latest"
# ★每单本金/杠杆改为可调(读 Redis · 见 guard.get_open_margin/get_open_leverage · 默认 100U/5x)


async def _read_items(redis: Any, key: str) -> list[dict[str, Any]]:
    """读快照 → items 列表(仿 managed _read_bias_map · 缺/坏 → 空)。"""
    raw = await redis.get(key)
    if not raw:
        return []
    data = json.loads(raw)
    items = data.get("items", []) if isinstance(data, dict) else []
    return [x for x in items if isinstance(x, dict)]


async def _mark_intelligent(
    session: AsyncSession, position_id: int, decision: istrategy.StrategyDecision,
) -> None:
    """★post-open:标 intelligent + 记 ATR 止损/止盈 + 共振明细(靠 position_id · 零碰引擎)。"""
    pos = await session.get(VirtualPerpPosition, position_id)
    if pos is None:
        return
    pos.intelligent = True
    pos.intelligent_stop_price = (
        Decimal(str(decision.stop_loss)) if decision.stop_loss is not None else None
    )
    pos.intelligent_tp_price = (
        Decimal(str(decision.take_profit)) if decision.take_profit is not None else None
    )
    pos.intelligent_signals = {"contributions": decision.contributions, "score": decision.score}
    await session.flush()


async def run_intelligent_open(
    session: AsyncSession,
    redis: Any,
    get_mark_price: Callable[[str], Awaitable[Decimal | None]],
) -> dict[str, Any]:
    """守卫 → 读两快照 → 打分共振决策 → route_open_perp 做多做空 → 标 intelligent + 记止损止盈。

    ★守卫第一行:开关 OFF → 立刻 return(空转零副作用 · 选币/下单在其后绝不执行)。
    ★同币不重复开 · 并发不限(Hans 定)· per-币 commit 隔离失败。
    """
    if not await iguard.is_enabled(redis):
        return {"status": "skip", "reason": "disabled"}

    account = await iacc.ensure_intelligent_account(session)
    # ★三参数读 Redis(即时生效)· margin/leverage 传 route(引擎零碰)· max_positions 限总持仓
    margin = await iguard.get_open_margin(redis)
    leverage = await iguard.get_open_leverage(redis)
    max_positions = await iguard.get_max_positions(redis)
    current_open = await iguard.count_open_positions(session, account.id)
    # ★总数上限约束(智能原本并发不限·现加 total 上限)· room = 剩余空间 · ≤0 不开
    room = max_positions - current_open
    boll_items = await _read_items(redis, _BOLL_KEY)
    signal_items = await _read_items(redis, _SIGNALS_KEY)
    # ★策略参数读 Redis(即时生效)· 传给纯函数 build_decisions/decide(保持可测)
    threshold = await iguard.get_strategy_threshold(redis)
    weights = await iguard.get_strategy_weights(redis)
    atr_stop = await iguard.get_strategy_atr_stop_mult(redis)
    atr_tp = await iguard.get_strategy_atr_tp_mult(redis)
    decisions = istrategy.open_decisions(istrategy.build_decisions(
        boll_items, signal_items,
        threshold=threshold, weights=weights, atr_stop_mult=atr_stop, atr_tp_mult=atr_tp,
    ))

    opened: list[dict[str, Any]] = []
    for d in decisions:
        if len(opened) >= room:  # ★到总数上限(开到刚好 max_positions·不超)
            break
        symbol = d.symbol
        if await iguard.has_open_position(session, account.id, symbol):
            continue  # ★同币不重复开
        side = PerpSide.LONG if d.action == "open_long" else PerpSide.SHORT  # ★做多做空对称
        try:
            order = await route_open_perp(
                session,
                user_id=account.user_id,
                symbol=symbol,
                side=side,
                leverage=leverage,        # ★读 Redis(可调 1-20)
                margin=margin,            # ★读 Redis(可调 10-10000)
                quantity=None,
                preferred_mode=MarginMode.CROSS,  # ★全仓
                get_mark_price=get_mark_price,
            )
            if order.status == OrderStatus.FILLED and order.position_id is not None:
                await _mark_intelligent(session, order.position_id, d)  # ★标 + 记止损止盈+共振
                await session.commit()
                opened.append({"symbol": symbol, "side": side.value, "score": d.score})
                logger.info(
                    "[intelligent] ✓ 开仓 %s %s %sU %sx · score=%s · 止损=%s 止盈=%s",
                    symbol, side.value, margin, leverage, d.score, d.stop_loss, d.take_profit,
                )
            else:
                await session.rollback()
                logger.info("[intelligent] 开仓被拒 %s · %s", symbol, order.reject_reason)
        except Exception:  # noqa: BLE001 · 单币失败隔离,不中断本轮
            await session.rollback()
            logger.exception("[intelligent] 开仓异常 %s", symbol)

    logger.info("[intelligent] 开仓编排 · 本轮新开 %d(并发不限):%s",
                len(opened), [o["symbol"] for o in opened])
    return {"status": "ok", "opened": opened}
