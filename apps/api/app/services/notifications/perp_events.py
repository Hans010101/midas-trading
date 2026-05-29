"""永续合约订单 → 通知事件 的纯函数 builder(#296)。

放在 notifications 层(而非 worker)以便 apps/api 单测直接导入验证。
worker task(send_perp_order_notification)读 DB 后调用这里的 builder。

纯函数:入参是已读好的 ORM 对象,出参是 frozen 事件 · 无 DB / IO · 可单测。
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, cast

from app.models.perp import PerpAction
from app.services.notifications.events import LiquidationEvent, PerpFilledEvent

if TYPE_CHECKING:
    from app.models.perp import VirtualPerpOrder, VirtualPerpPosition
    from app.models.virtual import VirtualAccount

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
