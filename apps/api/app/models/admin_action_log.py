"""AdminActionLog · 管理员操作审计(用户管理刀3b · 通用审计表)。

每次管理员对用户的写操作记一条(grant_pro / 3b-2 封禁等,action 区分)。
- operator_id: 操作的管理员(从 AdminDep 取 · 绝不信前端传入)
- target_user_id: 被操作用户
- action: 'grant_pro' | (3b-2)'ban'/'unban' …
- detail: JSONB(如 {days:365, period:'year', note:'...'})
- operator/target ondelete SET NULL → 账号删了审计仍留痕(可追溯)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AdminActionLog(Base):
    __tablename__ = "admin_action_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operator_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    target_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
