"""虚拟合约交易模型(0017 ADR · M2-A · M2-C 实装撮合)。

跟 models/virtual.py(spot)同模式 · 但加杠杆 / 保证金 / 强平 / 资金费率结算
四个 perp 专属概念。

M2-A 范围:只建表 schema · 不实装撮合逻辑。
M2-C 范围:补撮合 / 资金费率结算 worker / 强平。

红线:本表所有交易都是**虚拟资金** · 跟 Binance 真实合约账户无关。
"""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# ============================================================================
# 枚举
# ============================================================================


class FuturesMarginMode(enum.StrEnum):
    """保证金模式 · cross 全仓 · isolated 逐仓。"""

    CROSS = "cross"
    ISOLATED = "isolated"


class FuturesPositionDirection(enum.StrEnum):
    """持仓方向 · 跟 spot 的 buy/sell 不同 · perp 用 long/short。"""

    LONG = "long"
    SHORT = "short"


class FuturesOrderSide(enum.StrEnum):
    """合约下单方向(配合 reduce_only 区分开仓 / 平仓):

    BUY  + reduce_only=False = 开多 / 加多
    SELL + reduce_only=False = 开空 / 加空
    BUY  + reduce_only=True  = 平空
    SELL + reduce_only=True  = 平多
    """

    BUY = "buy"
    SELL = "sell"


class FuturesOrderType(enum.StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"
    TAKE_PROFIT_MARKET = "take_profit_market"
    TAKE_PROFIT_LIMIT = "take_profit_limit"


class FuturesOrderStatus(enum.StrEnum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


# ============================================================================
# 1 · 合约账户(子账户 · 跟 spot 的 VirtualAccount 同级 · per user 一个)
# ============================================================================


class VirtualFuturesAccount(Base):
    """合约虚拟账户 · 一个 user 一个 USDT-M 合约子账户。

    跟 spot 的 VirtualAccount 是平行关系 · 不共享余额。
    USDT 计价 · 简化处理(M2-C 之前不支持 Coin-M)。

    余额体系:
    - wallet_balance      = USDT 总余额
    - position_initial_margin  = 已开仓位占用的初始保证金
    - position_maintenance_margin = 维持保证金(只读统计 · 强平判断用)
    - unrealized_pnl      = 所有持仓的未实现盈亏
    - margin_balance      = wallet_balance + unrealized_pnl(权益)
    - available_balance   = margin_balance - position_initial_margin
                           (能用于新开仓的)

    强平规则:margin_balance < position_maintenance_margin → 强平所有仓
    """

    __tablename__ = "virtual_futures_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # per user 一个合约账户
        index=True,
    )

    # 资金(USDT 计 · 精度 4 位)
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    wallet_balance: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)

    # 累计已实现盈亏(资金费率累计 + 平仓 PnL)
    cumulative_realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, server_default="0",
    )
    # 累计资金费率支付(正 = 收入 · 负 = 支出)
    cumulative_funding_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, server_default="0",
    )

    # 默认保证金模式(单仓位 · M2-A 简化 · 全账户统一)
    margin_mode: Mapped[FuturesMarginMode] = mapped_column(
        SAEnum(FuturesMarginMode, name="futures_margin_mode_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False, server_default=FuturesMarginMode.CROSS.value,
    )

    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )


# ============================================================================
# 2 · 合约持仓
# ============================================================================


class VirtualFuturesPosition(Base):
    """合约持仓 · per (account, symbol, direction) 一行。

    M2-C 实装:
    - mark_price 由 mark_price worker 定期写入(从 Binance /fapi/v1/premiumIndex)
    - unrealized_pnl = (mark_price - entry_price) × qty × (long ? +1 : -1)
    - liq_price 计算见 0017 ADR § 7.2(M2-C 设计)
    """

    __tablename__ = "virtual_futures_position"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("virtual_futures_account.id", ondelete="CASCADE"), nullable=False,
    )

    symbol: Mapped[str] = mapped_column(String(64), nullable=False)  # "BTCUSDT"
    direction: Mapped[FuturesPositionDirection] = mapped_column(
        SAEnum(FuturesPositionDirection, name="futures_position_direction_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    leverage: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-125
    margin_mode: Mapped[FuturesMarginMode] = mapped_column(
        SAEnum(FuturesMarginMode, name="futures_margin_mode_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False, server_default=FuturesMarginMode.CROSS.value,
    )

    # 持仓量 · 用 base 币种计(BTC etc.)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)

    # 保证金(margin_mode=isolated 时是独立 · cross 时是占用全账户)
    initial_margin: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    maintenance_margin: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)

    # 这些字段由 M2-C mark_price worker 定期 update
    mark_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    unrealized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    liq_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))

    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_futures_position_account_symbol_dir", "account_id", "symbol", "direction"),
    )


# ============================================================================
# 3 · 合约订单
# ============================================================================


class VirtualFuturesOrder(Base):
    """合约订单 · 包括开仓 / 平仓 / 加减仓 / 止损止盈。"""

    __tablename__ = "virtual_futures_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("virtual_futures_account.id", ondelete="CASCADE"), nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)

    side: Mapped[FuturesOrderSide] = mapped_column(
        SAEnum(FuturesOrderSide, name="futures_order_side_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    order_type: Mapped[FuturesOrderType] = mapped_column(
        SAEnum(FuturesOrderType, name="futures_order_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    reduce_only: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))  # 限价单
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))  # 止损止盈触发

    # 成交后填
    filled_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, server_default="0",
    )
    avg_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    commission: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))

    status: Mapped[FuturesOrderStatus] = mapped_column(
        SAEnum(FuturesOrderStatus, name="futures_order_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False, server_default=FuturesOrderStatus.NEW.value,
    )
    reject_reason: Mapped[str | None] = mapped_column(String(128))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_futures_order_account_status", "account_id", "status"),
        Index("ix_futures_order_account_symbol_created", "account_id", "symbol", "created_at"),
    )


# ============================================================================
# 4 · 资金费率结算流水
# ============================================================================


class VirtualFuturesFundingSettlement(Base):
    """资金费率结算流水 · 每 8h 触发 · 跟据当时持仓 × funding_rate 结算到账户。

    M2-C 实装:Celery 任务每 8h(00:00 / 08:00 / 16:00 UTC)扫所有持仓 ·
    funding_pnl = position.qty × funding_rate × mark_price × direction_sign
    direction_sign:long 时持仓方付资金费 = -1 · short 时反之 = +1
    """

    __tablename__ = "virtual_futures_funding_settlement"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("virtual_futures_account.id", ondelete="CASCADE"), nullable=False,
    )
    position_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("virtual_futures_position.id", ondelete="CASCADE"), nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)

    funding_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    funding_rate: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)  # decimal 0.0001
    mark_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    position_qty: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    direction: Mapped[FuturesPositionDirection] = mapped_column(
        SAEnum(FuturesPositionDirection, name="futures_position_direction_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    funding_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_funding_settlement_account_ts", "account_id", "funding_ts"),
    )
