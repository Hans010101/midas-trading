"""订单 → 通知事件 的纯函数 builder(#296)。

放在 notifications 层(而非 worker)以便 apps/api 单测直接导入验证,且 bot 富回执
(改动一去重)与 worker 异步推送共用同一套构造逻辑 —— 文案/字段单一事实源。

纯函数:入参是已读好的 ORM 对象,出参是 frozen 事件 · 无 DB / IO · 可单测。
- build_perp_filled_event / build_liquidation_event_single:永续(perp)
- build_trade_filled_event:现货(spot · 抽自 worker send_trade_notification)
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, cast

from app.models.perp import PerpAction
from app.services.notifications.events import (
    LiquidationEvent,
    PerpFilledEvent,
    TradeFilledEvent,
)

if TYPE_CHECKING:
    from app.models.perp import VirtualPerpOrder, VirtualPerpPosition
    from app.models.virtual import VirtualAccount, VirtualOrder

_CLOSE_ACTIONS = (PerpAction.CLOSE_LONG, PerpAction.CLOSE_SHORT)


def build_perp_filled_event(
    order: VirtualPerpOrder,
    position: VirtualPerpPosition | None,
    account: VirtualAccount,
) -> PerpFilledEvent:
    """perp 成交订单 → PerpFilledEvent。leverage 优先取订单(仅开仓有),否则回落持仓。"""
    leverage = order.leverage
    if leverage is None and position is not None:
        leverage = position.leverage
    margin_mode = position.margin_mode if position is not None else "isolated"
    is_close = order.action in _CLOSE_ACTIONS
    return PerpFilledEvent(
        symbol=order.symbol,
        action=order.action.value,
        margin_mode=str(margin_mode),
        leverage=leverage,
        quantity=order.quantity,
        price=order.price or Decimal("0"),
        notional=order.notional or Decimal("0"),
        fee=order.fee or Decimal("0"),
        realized_pnl=order.realized_pnl if is_close else None,
        currency=account.currency.value,
    )


def build_liquidation_event_single(
    order: VirtualPerpOrder,
    position: VirtualPerpPosition | None,
    account: VirtualAccount,
) -> LiquidationEvent:
    """逐仓强平订单(is_liquidation=True)→ 单仓 LiquidationEvent。"""
    side = cast("str | None", position.side.value) if position is not None else None
    return LiquidationEvent(
        is_cross=False,
        symbol=order.symbol,
        side=side,  # type: ignore[arg-type]
        leverage=position.leverage if position is not None else None,
        liquidation_price=(
            position.liquidation_price if position is not None else None
        ),
        realized_pnl=order.realized_pnl,
        position_count=1,
        currency=account.currency.value,
    )


def build_trade_filled_event(
    order: VirtualOrder,
    account: VirtualAccount,
) -> TradeFilledEvent:
    """现货成交订单 → TradeFilledEvent(抽自 worker · bot 富回执 + 异步推送共用)。"""
    return TradeFilledEvent(
        symbol=order.symbol,
        market=order.market,
        side=order.side,  # type: ignore[arg-type]
        quantity=order.quantity,
        price=order.price or Decimal("0"),
        notional=order.notional or Decimal("0"),
        commission=order.commission or Decimal("0"),
        realized_pnl=order.realized_pnl,
        currency=account.currency.value,
    )
