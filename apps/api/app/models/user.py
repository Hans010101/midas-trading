"""User SQLAlchemy model · 0006 鉴权策略。

字段:
- id: UUID 主键
- email: unique
- password_hash: argon2id(via passlib)
- email_verified_at: NULL 表示未验证(0006 强制策略,未验证不让登录)
- age_confirmed: 注册时 18+ 勾选(合规要求)
- created_at / updated_at: tz-aware UTC,server-side default
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "user"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    age_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 0007 watchlist:首次 GET /watchlist 触发 demo 预填后翻为 True,
    # 用户主动清空 watchlist 不会再触发(防止「删光 → 又被填回来」UX 怪圈)
    demo_prefilled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
