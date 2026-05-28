"""加密永续合约虚拟交易 Pydantic 契约 · ADR-0019 v2 · M2-C.1。

🔴 红线:全程虚拟资金 · 字段都是虚拟撮合产物。
金额 USDT 本位 Decimal · 不折算。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.models.perp import PerpAction, PerpCloseReason, PerpSide
from app.models.virtual import OrderStatus


class PerpOrderPlaceIn(BaseModel):
    """POST /virtual/perp/orders 入参 · 市价 · 开多/开空/平仓。"""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=3, max_length=64, examples=["BTCUSDT"])
    intent: Literal["open_long", "open_short", "close"]
    # 开仓:leverage 必填(1–20)+ margin 或 quantity 二选一
    leverage: int | None = Field(default=None, ge=1, le=20)
    margin: Decimal | None = Field(default=None, gt=0, le=Decimal("999999999"))
    quantity: Decimal | None = Field(default=None, gt=0)
    # 平仓:close_all 或 quantity
    close_all: bool = False
    # MC-4 接入:保证金模式 · 默认 isolated(老调用不传 → 行为完全等同 MC-3 之前)
    margin_mode: Literal["isolated", "cross"] = "isolated"

    @model_validator(mode="after")
    def _check(self) -> PerpOrderPlaceIn:
        if self.intent in ("open_long", "open_short"):
            if self.leverage is None:
                msg = "开仓需指定 leverage(1–20)"
                raise ValueError(msg)
            if self.margin is None and self.quantity is None:
                msg = "开仓需指定 margin 或 quantity"
                raise ValueError(msg)
            if self.margin is not None and self.quantity is not None:
                msg = "margin 与 quantity 二选一"
                raise ValueError(msg)
        elif not self.close_all and self.quantity is None:
            msg = "平仓需指定 quantity 或 close_all=true"
            raise ValueError(msg)
        return self


class PerpOrderResponse(BaseModel):
    """合约订单流水响应(filled / rejected)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int | None  # 未激活拒单 sentinel 为 None
    account_id: int | None
    position_id: int | None
    symbol: str
    action: PerpAction
    leverage: int | None
    quantity: Decimal
    price: Decimal | None
    notional: Decimal | None
    margin_delta: Decimal | None
    fee: Decimal | None
    realized_pnl: Decimal | None
    status: OrderStatus
    reject_reason: str | None
    is_liquidation: bool
    placed_at: AwareDatetime | None
    filled_at: AwareDatetime | None


class PerpPositionResponse(BaseModel):
    """合约持仓响应 · 含实时浮盈 / 强平距离(读时按 mark 现算)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    symbol: str
    side: PerpSide
    leverage: int
    # MC-4 起对外暴露:'isolated' / 'cross'(前端确认页与活仓卡用,平仓自动按此分流)
    margin_mode: Literal["isolated", "cross"]
    quantity: Decimal
    entry_price: Decimal
    initial_margin: Decimal
    liquidation_price: Decimal
    realized_pnl: Decimal
    fee_paid: Decimal
    # 累计资金费(M2-C.2.2)· 正=净付出(现金减少),负=净收到 · 活仓期随结算累加
    funding_paid: Decimal
    opened_at: AwareDatetime
    closed_at: AwareDatetime | None
    close_reason: PerpCloseReason | None
    # ── 实时(活仓且有 mark 时填,否则 None)──
    mark_price: Decimal | None
    unrealized_pnl: Decimal | None
    liquidation_distance_pct: Decimal | None
    roe_pct: Decimal | None  # 浮盈 / 保证金 × 100(杠杆放大收益率)


class PerpFundingResponse(BaseModel):
    """资金费结算流水行(M2-C.2.2 · ADR-0020 E5)· 账户页展示。

    payment 符号:正 = 该仓本次【付出】(现金减少),负 = 【收到】(现金增加)。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    symbol: str
    side: PerpSide
    funding_rate: Decimal  # decimal · 0.0001 = 0.01%
    mark_price: Decimal
    quantity: Decimal
    payment: Decimal  # USDT · 正=付出 / 负=收到
    funding_ts: AwareDatetime  # 对齐的结算整点
    settled_at: AwareDatetime
