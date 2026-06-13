"""条件单挂单簿(ADR 0041 刀1)· 限价 / 止损 / 止盈 三类共表。

🔴 红线(ADR 0041):条件单只是「延迟触发器」—— 本表不参与任何撮合;触发那一刻(刀2 扫描器)
   构造 PlaceOrderRequest 调 place_market_order 完成真实成交,engine 零改。
   VirtualOrder 保持 FILLED/REJECTED 二元终态(决策一:独立表,非 PENDING)。

资金语义(决策二):挂单不冻结资金;触发时由 place_market_order 现有余额校验把关。
user_id 软引用(无 FK):挂单时账户可未激活,触发时才 resolve account。

★ 触发方向推导矩阵(刀2 实现 · 刀1 先落档;不存方向列,由 (order_kind, side, position_side)
  推导,防「方向与单型矛盾」脏数据;全矩阵由刀2 单测锁):

  | order_kind   | side/仓向            | 触发条件(最新价 P vs trigger_price T) |
  |--------------|----------------------|----------------------------------------|
  | LIMIT        | BUY(低吸)          | P ≤ T 触发买入                          |
  | LIMIT        | SELL(高抛)         | P ≥ T 触发卖出                          |
  | STOP_LOSS    | 平多(position LONG) | P ≤ T 触发平仓(跌破止损)              |
  | STOP_LOSS    | 平空(position SHORT)| P ≥ T 触发平仓(涨破止损)              |
  | TAKE_PROFIT  | 平多(position LONG) | P ≥ T 触发平仓(到价止盈)              |
  | TAKE_PROFIT  | 平空(position SHORT)| P ≤ T 触发平仓                          |

quantity:LIMIT 必填(应用层校验);STOP_LOSS / TAKE_PROFIT 允许 NULL = 触发时平全仓
(对齐 perp route_close close_all 语义)。
"""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Enum, Index, Integer, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.virtual import OrderSide, PositionSide


class ConditionalKind(enum.StrEnum):
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class ConditionalStatus(enum.StrEnum):
    ACTIVE = "active"          # 挂着 · 等刀2 触发器
    TRIGGERED = "triggered"    # 已触发并成交(triggered_order_id 回填)
    CANCELLED = "cancelled"    # 用户撤单
    EXPIRED = "expired"        # 触发时校验失败(余额不足 / 无可平持仓 · note 落原因)


class ConditionalOrder(Base):
    """一张条件单 · 状态机 active → triggered / cancelled / expired(ADR 0041 决策一)。"""

    __tablename__ = "conditional_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 软引用 user(无 FK)· 挂单时不绑 account(触发时才 resolve · 决策二配套)
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)

    order_kind: Mapped[ConditionalKind] = mapped_column(
        Enum(ConditionalKind, name="conditional_kind"), nullable=False,
    )
    # 复用现有 PG enum 类型(order_side / position_side · 迁移用 create_type=False 引用)
    side: Mapped[OrderSide] = mapped_column(
        Enum(OrderSide, name="order_side"), nullable=False,
    )
    position_side: Mapped[PositionSide] = mapped_column(
        Enum(PositionSide, name="position_side"), nullable=False,
        server_default=PositionSide.LONG.name,
    )

    trigger_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # LIMIT 必填(应用层校验)· SL/TP NULL = 平全仓
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))

    # ── 二期刀1:perp 限价开仓字段(仅 market=crypto & kind=LIMIT 用 · 其余 NULL)──
    # ⛔ 刀1 只落字段 + 端点放开挂单;触发→开仓(走 route_open_perp)留刀2,
    #    本刀触发器对 perp LIMIT 仍走现有 EXPIRED 防御(半成品不真触发)。
    leverage: Mapped[int | None] = mapped_column(Integer)  # 1..125(perp 口径)
    margin: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))  # >0
    margin_mode: Mapped[str | None] = mapped_column(String(16))  # cross | isolated
    # 限价单挂单过期(Hans:默认 NULL=长期有效 · 过期扫描逻辑留后续)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[ConditionalStatus] = mapped_column(
        Enum(ConditionalStatus, name="conditional_status"), nullable=False,
        # 照 VirtualOrder 范式:Enum 按 .name 存 → server_default 用成员名
        server_default=ConditionalStatus.ACTIVE.name,
    )
    # 触发成交后回填(软引用:spot 指向 virtual_order.id · perp 指向 perp 订单 id · 不加 FK)
    triggered_order_id: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(128))  # expired 原因 / 审计备注

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        # 给刀2 触发器用 —— 扫 ACTIVE 单并按市场分组取价
        Index("ix_conditional_orders_status_market", "status", "market"),
        # 给「我的挂单」列表用 —— 本人倒序
        Index("ix_conditional_orders_user_created", "user_id", "created_at"),
    )
