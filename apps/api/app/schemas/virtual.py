"""虚拟交易 Pydantic 契约 · 0008 v2 三独立子账户。

所有金额字段原币种 Decimal · 不做 CNY 折算。
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.models.virtual import Currency, OrderSide, OrderStatus, OrderType
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
    quantity: Decimal
    avg_entry_price: Decimal
    current_price: Decimal | None
    unrealized_pnl: Decimal | None
    value: Decimal | None  # quantity × current_price


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
