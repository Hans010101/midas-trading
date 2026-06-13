"""Subscription SQLAlchemy model · 会员 Phase 1(刀1)。

设计(调研 P2 定稿):
- 无行 = free(lazy 先例:virtual_account / notification_config)——
  Phase 1 全员免费层零数据迁移零 server_default;Phase 2 支付成功才写行。
- plan / status 用 VARCHAR 不用 PG enum(currency/margin_mode 两次 enum→varchar 先例)。
- user 表零改动:role 是权限(用户管理刀1),plan 是商业权益,两概念分开。

字段语义:
- plan: 'pro'(Phase 2 可扩 · 'free' 不写行)
- status: 'active' 才有效;其他值(canceled/expired)按 free 解析
- expires_at: NULL = 不过期;< now 按 free 解析
- source: 'manual' / Phase 2 支付渠道标识(审计)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Subscription(Base):
    __tablename__ = "subscription"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # 一用户最多一行(当前订阅态 · 历史审计是 Phase 2 的事)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, unique=True,
    )
    plan: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )
