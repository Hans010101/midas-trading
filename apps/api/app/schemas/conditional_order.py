"""条件单 Pydantic 契约(ADR 0041 刀1)。

🔴 红线:挂单簿管理 API(挂/撤/列)—— 本层不撮合不成交;触发成交是刀2 扫描器,
   届时仍走 place_market_order 唯一入口。本刀条件单【不会触发】(有意分界)。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.conditional_order import ConditionalKind, ConditionalStatus
from app.models.virtual import OrderSide, PositionSide
from app.schemas.market import Market


class ConditionalOrderCreate(BaseModel):
    """POST /virtual/conditional-orders 入参。

    - LIMIT:quantity 必填(端点校验);side=BUY 低吸 / SELL 高抛。
    - STOP_LOSS / TAKE_PROFIT:持仓后独立挂(ADR 未决②定型为 (a))· quantity 可空=平全仓 ·
      side 必须是该仓向的平仓方向(LONG→SELL / SHORT→BUY,端点校验防脏数据)。
    - crypto 语义=perp(symbol 用 Binance 风格 BTCUSDT);spot 各市场用现有符号形态。
    """

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=64)
    market: Market
    order_kind: ConditionalKind
    side: OrderSide
    position_side: PositionSide = PositionSide.LONG
    trigger_price: Decimal = Field(gt=0)
    quantity: Decimal | None = Field(default=None, gt=0)


class ConditionalOrderResponse(BaseModel):
    """单张条件单(列表项与详情同型 · 字段轻,无需精简版)。"""

    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    id: int
    symbol: str
    market: str
    order_kind: ConditionalKind
    side: OrderSide
    position_side: PositionSide
    trigger_price: Decimal
    quantity: Decimal | None
    status: ConditionalStatus
    triggered_order_id: int | None
    note: str | None
    created_at: datetime
    updated_at: datetime
