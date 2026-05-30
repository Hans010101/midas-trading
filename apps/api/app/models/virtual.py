"""虚拟交易 SQLAlchemy models · 0008 v2 三独立子账户方案。

四张表:
- VirtualAccount    · 每用户每市场一行(lazy create · 不存在=未激活)
- VirtualPosition   · 持仓 · 软删 closed_at + realized_pnl 写 row
- VirtualOrder      · 订单流水 · 不可变
- VirtualEquitySnapshot · 权益曲线点 · 每次成交 + 每日定时

金额原币种 Numeric(20,4) · 数量 Numeric(20,8) · 永不折算 CNY。
"""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# ===== Enum =====


class Currency(enum.StrEnum):
    CNY = "CNY"
    USD = "USD"
    USDT = "USDT"
    HKD = "HKD"  # 港股(阶段一接入 · 数据/下单待 P1-3+)


class OrderSide(enum.StrEnum):
    BUY = "buy"
    SELL = "sell"


class PositionSide(enum.StrEnum):
    """持仓方向(0023 阶段③ · 3.4)。

    LONG = 做多(0008 现货原有 · 存量行 backfill 为 LONG)· BUY 开/加,SELL 平。
    SHORT = 卖空(美股专用 · 无杠杆 1:1 锁现金)· SELL 开空,BUY 平空(买回)。
    A股 / 加密现货只用 LONG;美股两者皆可(但同标的同时仅一个方向活仓)。
    """

    LONG = "long"
    SHORT = "short"


class OrderType(enum.StrEnum):
    MARKET = "market"
    # 未来扩展位:LIMIT 等订单类型在 0008 Task 5+ M1 实装,留 enum 增量空间


class OrderStatus(enum.StrEnum):
    FILLED = "filled"
    REJECTED = "rejected"


class SnapshotTrigger(enum.StrEnum):
    ORDER_FILLED = "order_filled"
    DAILY = "daily"


# Market(str) → Currency 映射:在 service 层用,不在 model 层强约束
# 但写入时由 service 校验 currency 跟 market 一致
MARKET_CURRENCY: dict[str, Currency] = {
    "cn": Currency.CNY,
    "us": Currency.USD,
    "crypto": Currency.USDT,
    "hk": Currency.HKD,
}


# ===== Tables =====


class VirtualAccount(Base):
    """用户 × 市场 一行 · lazy create(用户在设置页填金额时才 INSERT)。

    存在 = 已激活;不存在 = 未激活(对应市场按钮 disabled)。
    """

    __tablename__ = "virtual_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
    )
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    currency: Mapped[Currency] = mapped_column(
        Enum(Currency, name="currency"), nullable=False,
    )
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, server_default=text("0"),
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "market", name="uq_virtual_account_user_market"),
        Index("ix_virtual_account_user", "user_id"),
    )


class VirtualPosition(Base):
    """持仓 · 软删 · closed_at IS NULL 为活仓,NOT NULL 为历史。

    清仓时写入 closed_at + realized_pnl,不删除 row(复盘价值)。
    """

    __tablename__ = "virtual_position"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("virtual_account.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    # 持仓方向(3.4)· LONG=现货做多(原有 · 存量 backfill 为 LONG)。
    # SHORT=卖空(美股 · 无杠杆 1:1 锁现金担保)· 现货做多路径零改动。
    position_side: Mapped[PositionSide] = mapped_column(
        Enum(PositionSide, name="position_side"), nullable=False,
        server_default=PositionSide.LONG.name,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # 同账户同标的最多一个活仓(closed_at IS NULL)· partial unique
        Index(
            "uq_virtual_position_active",
            "account_id", "symbol",
            unique=True,
            postgresql_where=text("closed_at IS NULL"),
        ),
        Index("ix_virtual_position_account_closed", "account_id", "closed_at"),
    )


class VirtualOrder(Base):
    """订单流水 · 不可变 · status: filled / rejected。"""

    __tablename__ = "virtual_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("virtual_account.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[OrderSide] = mapped_column(
        Enum(OrderSide, name="order_side"), nullable=False,
    )
    # 持仓方向(3.4)· LONG=现货做多(原有 · 存量 backfill);SHORT=卖空(美股)。
    # side=SELL+SHORT=开空,side=BUY+SHORT=平空(买回);LONG 时 side 即买/卖。
    position_side: Mapped[PositionSide] = mapped_column(
        Enum(PositionSide, name="position_side"), nullable=False,
        server_default=PositionSide.LONG.name,
    )
    order_type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, name="order_type"), nullable=False,
        # SQLAlchemy Enum 默认按 .name 存(跟 verification_token TokenPurpose 一致),
        # 所以 server_default 用 enum 成员名 "MARKET" 而不是 value "market"
        server_default=OrderType.MARKET.name,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # 成交价 / 名义金额 / 手续费 / 滑点成本 · 拒单时全 NULL
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    notional: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    commission: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    slippage_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    # 仅 sell 填(本笔贡献的已实现 in market currency)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status"), nullable=False,
    )
    reject_reason: Mapped[str | None] = mapped_column(String(128))
    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_virtual_order_account_placed", "account_id", "placed_at"),
    )


class VirtualEquitySnapshot(Base):
    """权益快照 · 每市场一条曲线。"""

    __tablename__ = "virtual_equity_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("virtual_account.id", ondelete="CASCADE"),
        nullable=False,
    )
    market: Mapped[str] = mapped_column(String(16), nullable=False)  # 冗余,加速查询
    cash: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    positions_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    realized_pnl_cumulative: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False,
    )
    trigger_kind: Mapped[SnapshotTrigger] = mapped_column(
        Enum(SnapshotTrigger, name="snapshot_trigger"), nullable=False,
    )
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_virtual_equity_account_at", "account_id", "snapshot_at"),
    )
