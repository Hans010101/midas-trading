"""虚拟交易 Pydantic 契约 · 0008 v2 三独立子账户。

所有金额字段原币种 Decimal · 不做 CNY 折算。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.virtual import Currency, OrderSide, OrderStatus, OrderType, PositionSide
from app.schemas.market import Market

# ===== Account =====


class AccountActivateIn(BaseModel):
    """PUT /accounts/{market} 入参 · 激活或重置子账户。"""

    model_config = ConfigDict(extra="forbid")

    initial_capital: Decimal = Field(
        gt=0,
        le=Decimal("999999999"),
        description="初始资金(原币种 · 上限 9.99 亿,避免误填天文数字)",
    )


class AccountResponse(BaseModel):
    """子账户响应 · 单市场。"""

    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    id: int
    market: Market
    currency: Currency
    initial_capital: Decimal
    cash_balance: Decimal
    realized_pnl: Decimal
    activated_at: AwareDatetime


# ===== Position =====


class PositionResponse(BaseModel):
    """持仓响应(活仓 + 历史共用)· 含实时浮盈(activate 时)。"""

    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    id: int
    symbol: str
    market: Market
    position_side: PositionSide
    quantity: Decimal
    avg_entry_price: Decimal
    realized_pnl: Decimal | None
    opened_at: AwareDatetime
    closed_at: AwareDatetime | None  # NULL = 活仓


class PositionWithQuoteResponse(BaseModel):
    """持仓 + 实时价 + 浮盈(给 /portfolio 用)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    symbol: str
    market: Market
    position_side: PositionSide
    quantity: Decimal
    avg_entry_price: Decimal
    current_price: Decimal | None
    unrealized_pnl: Decimal | None
    value: Decimal | None  # long: quantity × current_price · short: 担保 + 浮盈


# ===== Portfolio =====


class AccountSummaryResponse(BaseModel):
    """单市场账户全貌:account + 活仓 + 实时估值。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: int
    market: Market
    currency: Currency
    initial_capital: Decimal
    cash_balance: Decimal
    realized_pnl: Decimal
    positions: list[PositionWithQuoteResponse]
    positions_value: Decimal
    total_equity: Decimal


# ===== Order =====


class OrderPlaceIn(BaseModel):
    """POST /orders 入参 · 市价单。"""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=64)
    market: Market
    side: OrderSide
    # 3.4 · 默认 LONG(做多 · A股/加密/美股做多)· SHORT 仅美股卖空(SELL=开空 / BUY=平空)
    position_side: PositionSide = PositionSide.LONG
    quantity: Decimal = Field(gt=0)


class OrderResponse(BaseModel):
    """订单流水响应(filled / rejected)。"""

    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    id: int | None  # 未激活市场拒单时为 None(临时对象,未持久化)
    account_id: int | None
    symbol: str
    market: Market
    side: OrderSide
    order_type: OrderType
    position_side: PositionSide
    quantity: Decimal
    price: Decimal | None
    notional: Decimal | None
    commission: Decimal | None
    slippage_cost: Decimal | None
    realized_pnl: Decimal | None
    status: OrderStatus
    reject_reason: str | None
    placed_at: AwareDatetime | None
    filled_at: AwareDatetime | None


class HkBoardLotResponse(BaseModel):
    """港股每手股数(board lot)· 前端下单按手取整 / UI 提示用 · 只读。

    lot 来自 hk_pool(策展 18 只 · 已逐一核港交所官方)· 不在池内 → 404。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    board_lot: int


# ===== AI 模拟下单(0036 批次甲)=====


class AiOrderRequest(BaseModel):
    """POST /virtual/ai-order 入参 · AI 建议一键模拟下单。

    ★ 红线:只走现有虚拟撮合引擎(execute → place_market_order / route_open/close_perp),
      绝不接真实交易。direction 来自 AI 决策卡 actionable 建议(hold/close 不经此端点)。
    仓位不传:由 execute 内部按用户 BotOrderPreset 派生(拍板③)。
    """

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=64)
    market: Market
    # 仅 4 个可下单方向 · cn/us 用 buy/sell · crypto 用 open_long/open_short(合约)
    direction: Literal["buy", "sell", "open_long", "open_short"]


class AiOrderResponse(BaseModel):
    """AI 模拟下单结果 · 与手动下单同一虚拟引擎成交 · 标 source=ai_signal。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    filled: bool
    title: str
    detail: str
    source: str = "ai_signal"


# ===== Equity curve =====


class EquitySnapshotResponse(BaseModel):
    """权益曲线点。"""

    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    cash: Decimal
    positions_value: Decimal
    equity: Decimal
    realized_pnl_cumulative: Decimal
    snapshot_at: AwareDatetime


class EquityCurvesResponse(BaseModel):
    """多市场曲线 · 按 market 分组。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    curves: dict[str, list[EquitySnapshotResponse]]
