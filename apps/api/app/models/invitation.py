"""Invitation SQLAlchemy model · Phase 1.5 刀A(邀请归因/兑现)。

一行 = 一次归因(注册带有效 ref 即写 · pending 态);rewarded_at 写入 = 已兑现。
- invitee_id unique:一人终身只能被兑现一次(防同人重复)
- rewarded_at NULL = 待邮箱验证(防刷底线:受邀方验证后才兑现)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Invitation(Base):
    __tablename__ = "invitation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inviter_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    invitee_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, unique=True,
    )
    code: Mapped[str] = mapped_column(String(12), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    rewarded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
