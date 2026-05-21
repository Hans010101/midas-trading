"""User SQLAlchemy model · 0006 鉴权策略 + M1 第三波 Google OAuth。

字段:
- id: UUID 主键
- email: unique
- password_hash: argon2id(via passlib)· **OAuth-only 用户可空**
- google_sub: Google `sub` claim · OAuth 登录唯一标识 · unique 可空
- email_verified_at: NULL 表示未验证 · OAuth 登录创建时自动写当下时间
                     (Google 已经替我们验证了邮箱)
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
    # OAuth-only 用户 password_hash 可空(Google 登录无密码)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Google OAuth sub claim · 同一 Google 账号 → 同一 user · 一个用户一辈子一个值
    google_sub: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True,
    )
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
