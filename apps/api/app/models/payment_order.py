"""会员订阅支付订单(Phase 2a · OxaPay USDT 多链托管收款)。

🔴 红线:本表只记会员订阅【订单】—— 收的是订阅费,非交易;支付域不碰 virtual_trading/engine。
external_id 不可猜(secrets · 给 OxaPay 作 order_id + 回调匹配键);凭证不入表。
表结构沿用初版实现(早于现网关):pay_address 存 payment_url,gateway_txid 存 track_id。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PaymentOrder(Base):
    """会员订阅支付订单 · pending → paid(回调核验后)/ expired(超时未付)。"""

    __tablename__ = "payment_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 不可猜订单号(secrets.token_urlsafe)· 给 OxaPay order_id + 回调匹配键 · unique
    external_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
    )
    plan: Mapped[str] = mapped_column(String(16), nullable=False)  # 'pro'
    period: Mapped[str] = mapped_column(String(16), nullable=False)  # month|quarter|year
    amount_usdt: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)  # 应付额
    # chain · OxaPay 托管页多链(建单写 "multi")· server_default 沿用旧值(不改 schema)
    chain: Mapped[str] = mapped_column(String(16), nullable=False, server_default="binance")
    pay_address: Mapped[str | None] = mapped_column(String(128))  # OxaPay payment_url(建单后回填)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending",  # pending|paid|expired
    )
    gateway_txid: Mapped[str | None] = mapped_column(String(128))  # OxaPay track_id(建单时即回填)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 索引支撑「用户查自己订单(按时间倒序)」的列表查询
    __table_args__ = (Index("ix_payment_order_user_created", "user_id", "created_at"),)
