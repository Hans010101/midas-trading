"""加密永续合约虚拟交易 SQLAlchemy models · ADR-0019 v2 · M2-C.1。

═══════════════════════════════════════════════════════════════════════════
🔴 红线(贯穿本模块 + perp_engine + perp 路由 + 强平 worker):
   全程【虚拟资金】,绝不接任何真实交易 / 下单 / 转账通道。
   开仓 / 平仓 / 反手 / 强平全部走点金自己的虚拟撮合(perp_engine),
   ccxt / Binance API 只用于【读行情】,绝不 create_order。
   杠杆 / 做空 / 强平只是虚拟教学,不是真钱。
═══════════════════════════════════════════════════════════════════════════

与 0008 现货虚拟交易(virtual.py)的关系(ADR-0019 §2):
- 复用 VirtualAccount(crypto 子账户 = USDT 钱包)· 不在本文件,见 virtual.py。
- 复用 OrderStatus enum(filled / rejected)· 从 virtual.py import。
- 新增本文件两张 perp 专用表,【不动】0008 现货 VirtualPosition / VirtualOrder。

两张表:
- VirtualPerpPosition · 合约持仓 · 单向净持仓(D6)· 软删 closed_at
- VirtualPerpOrder     · 合约订单流水 · 不可变

量纲约定(对齐 0008 + 共用 USDT 钱包 cash_balance 的 Numeric(20,4)):
- 数量 / 价格 / 强平价 = Numeric(20,8)
- USDT 金额(保证金 / 盈亏 / 手续费 / 名义额)= Numeric(20,4) · 与 cash_balance 同精度,零漂移
- 金额永不折算 · 全 USDT 本位线性合约。
"""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# 0008 复用:订单成交 / 拒单状态(filled / rejected),不重复定义
from app.models.virtual import OrderStatus

# ===== Enum =====


class PerpSide(enum.StrEnum):
    """持仓 / 开仓方向。"""

    LONG = "long"
    SHORT = "short"


class MarginMode(enum.StrEnum):
    """保证金模式 · 逐仓 / 全仓(ADR-0027)。

    🔴 MC-1 阶段:CROSS 仅【预定义】,本期任何代码路径都不得实际使用
       (全仓开仓/计算/强平在 MC-2/MC-3/MC-4 才落地)。本期所有写入仍为 ISOLATED。
    StrEnum 是 str 子类,赋给 String 列存储其 .value('isolated'/'cross')。
    """

    ISOLATED = "isolated"
    CROSS = "cross"  # MC-1 预定义占位 · 本期不进任何代码路径(MC-2/3/4 才用)


class PerpAction(enum.StrEnum):
    """订单动作(写进流水)· 由请求 + 当前持仓在成交时推导出最终四值之一。"""

    OPEN_LONG = "open_long"
    OPEN_SHORT = "open_short"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"


class PerpCloseReason(enum.StrEnum):
    """活仓被关闭的原因(软删时写)。"""

    MANUAL = "manual"  # 用户手动平
    LIQUIDATED = "liquidated"  # 强平(mark 触及强平价)
    RESET = "reset"  # 账户重置清仓


# ===== Tables =====


class VirtualPerpPosition(Base):
    """合约持仓 · 单向净持仓(同账户同 symbol 最多一个活仓)· 逐仓。

    - quantity:持仓量(币)· 净持仓 · 部分平仓递减 · 全平归 0 + 软删。
    - side:long / short(单向,所以由活仓唯一决定)。
    - liquidation_price 入库(强平 worker 要 O(活仓) 快速比对 mark);
      unrealized_pnl / 保证金率 / 强平距离 不入库,读时按 mark 现算。
    - 红线:这里所有数字都是虚拟撮合产物,绝不对应任何真实持仓。
    """

    __tablename__ = "virtual_perp_position"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("virtual_account.id", ondelete="CASCADE"), nullable=False,
    )
    # Binance 风格 'BTCUSDT'(与采集表 / futures/info / 详情页 futuresSymbol 一致)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[PerpSide] = mapped_column(
        Enum(PerpSide, name="perp_side"), nullable=False,
    )
    # MC-1(ADR-0027 DP-5):由 PG Enum 改 VARCHAR(16),为全仓 'cross' 扩容,
    # 免去 ALTER TYPE ADD VALUE 的不可逆与锁表风险。现网行只存 'isolated'。
    # StrEnum 是 str 子类,写入时引擎赋 MarginMode.ISOLATED 即存其 .value 'isolated'。
    margin_mode: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text("'isolated'"),
    )
    leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # 已冻结保证金(USDT)· 加仓累加 · 部分平按比例释放
    initial_margin: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    # MMR 快照(开仓时记 · 默认 0.005)· 强平价用
    maintenance_margin_rate: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False,
    )
    # 强平价(每次开/加/反手后重算 · 入库供强平 worker 比对)
    liquidation_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # 已实现盈亏(平仓累计 · USDT)· 活仓期可为 0
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, server_default=text("0"),
    )
    fee_paid: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, server_default=text("0"),
    )
    # M2-C.2 才写入(资金费结算 · 按币种各自周期)· 一期恒 0
    funding_paid: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, server_default=text("0"),
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[PerpCloseReason | None] = mapped_column(
        Enum(PerpCloseReason, name="perp_close_reason"),
    )

    __table_args__ = (
        # 单向净持仓(D6):同账户同 symbol 最多一个活仓 · partial unique
        Index(
            "uq_perp_position_active",
            "account_id", "symbol",
            unique=True,
            postgresql_where=text("closed_at IS NULL"),
        ),
        Index("ix_perp_position_account_closed", "account_id", "closed_at"),
        # 强平 worker:扫所有活仓(closed_at IS NULL)· 按 symbol 取 mark 比对
        Index("ix_perp_position_active_symbol", "symbol", "closed_at"),
    )


class VirtualPerpOrder(Base):
    """合约订单流水 · 不可变 · status: filled / rejected(复用 0008 enum)。"""

    __tablename__ = "virtual_perp_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("virtual_account.id", ondelete="CASCADE"), nullable=False,
    )
    # 关联持仓 · rejected / 未激活时可空
    position_id: Mapped[int | None] = mapped_column(Integer)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[PerpAction] = mapped_column(
        Enum(PerpAction, name="perp_action"), nullable=False,
    )
    leverage: Mapped[int | None] = mapped_column(Integer)  # 仅 open 填
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # 成交价(mark + 滑点)· 名义额 · 本笔冻结/释放保证金 · 手续费 · rejected 时全 NULL
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    notional: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    margin_delta: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    fee: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    # 仅平仓笔填(本笔贡献的已实现 · USDT · 已扣本笔手续费)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status"), nullable=False,
    )
    reject_reason: Mapped[str | None] = mapped_column(String(128))
    # 是否强平触发(区分手动平 vs 强平 · 前端 toast / 流水标注)
    is_liquidation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_perp_order_account_placed", "account_id", "placed_at"),
    )


class VirtualPerpFunding(Base):
    """资金费结算流水 · ADR-0020 E5 · M2-C.2.2。

    每条 = 某活仓在某结算整点被收 / 付的一次资金费(可复盘 · 账户/详情页可展示)。
    结算服务(perp_funding.settle_funding)写:cash_balance -= payment · position.funding_paid
    += payment · 并 add 一行本表。E4=A:只扣虚拟现金,不联动强平。

    payment 符号约定(与 position.funding_paid 同号):
      正 = 该仓本次【付出】(现金减少);负 = 【收到】(现金增加)。
      标准永续:rate>0 → 多头付、空头收。

    幂等:(position_id, funding_ts) 唯一 —— funding_ts 是对齐到整点的结算时刻,
    同一结算点重复跑(beat 重触发 / 手动重试)不会重复扣费。

    🔴 红线:全程虚拟资金,worker 只读行情结算,绝不接真实资金费 / 转账。
    """

    __tablename__ = "virtual_perp_funding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("virtual_account.id", ondelete="CASCADE"), nullable=False,
    )
    position_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("virtual_perp_position.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[PerpSide] = mapped_column(
        Enum(PerpSide, name="perp_side"), nullable=False,
    )
    # 结算时该币资金费率(decimal · 0.0001 = 0.01%)
    funding_rate: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # 结算时标记价(计 notional 用)
    mark_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # 结算时持仓量 · 币
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # 支付额 · USDT · 正为付出令现金减少 · 负为收到令现金增加
    payment: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    # 对齐到整点的结算时刻(幂等键 · 防重复结算)
    funding_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    # 实际执行结算的时间
    settled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        # 幂等 · 同一活仓同一结算整点只结算一次
        Index(
            "uq_perp_funding_position_ts",
            "position_id", "funding_ts",
            unique=True,
        ),
        Index("ix_perp_funding_account_settled", "account_id", "settled_at"),
    )
