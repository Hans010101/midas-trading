"""Session SQLAlchemy model · 0006 ADR 回归(JWT → DB session)。

设计要点(2026-05-21 产品负责人指令):
- 7 天滚动 TTL(每次 verify_session 都续 7 天)
- 单用户最多 5 设备(`issue_session` 时若已有 5 个,evict 最旧的)
- 现有 JWT 用户强制重登 · JWT 不在本表 · deps.py 改成查本表 · 自然失效
- 存 token_hash 而不是 token 明文 · 即使 DB 泄露也无法重放

字段:
- id: int 自增主键
- token_hash: sha256 hex(64 字符)· unique · 唯一查询入口
- user_id: FK user.id ondelete=CASCADE
- user_agent: 浏览器 UA(只用于设备区分,不用于安全)
- ip_address: 登录时 IP(只用于审计 · M2+ 安全检测用)
- created_at / last_used_at / expires_at
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Session(Base):
    """登录会话 · 滚动 TTL · 单用户上限 5 设备。"""

    __tablename__ = "session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # sha256(token) hex · 64 char · 查询入口
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True,
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
    )

    # 设备区分(只用于「我的设备」展示 · 不参与 auth 决策)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )

    __table_args__ = (
        Index("ix_session_user_last_used", "user_id", "last_used_at"),
        Index("ix_session_expires", "expires_at"),
    )
