"""学习进度 SQLAlchemy model · 训练营 B 期刀1(学习进度追踪)。

设计(对齐项目表规范 · 纯增量新表 · 不碰任何现有表):
- 一行 = 某用户标记学完某篇文章;(user_id, article_slug) 唯一 → 重复标记幂等。
- article_slug 对应 manifest 文章 slug(如 "C7"/"E4"/"C1-1")· 合法性由
  services/academy/catalog.py 在端点层校验(本表不存外键到文章,文章是前端内容非 DB 实体)。
- stage 冗余存(catalog 派生 · 不信前端传)· 方便按阶统计「各阶完成数」不回查目录。
- VARCHAR 不用 PG enum(项目先例);时区 aware datetime;正式 Alembic 迁移建表。

🔴 红线:学习进度域纯增量 · 与交易/支付/会员零关系。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AcademyProgress(Base):
    __tablename__ = "academy_progress"
    __table_args__ = (
        # 同一用户同一篇只一条 → 重复标记幂等(端点先查后插 / 冲突静默)
        UniqueConstraint("user_id", "article_slug", name="uq_academy_progress_user_article"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    # 文章 slug(manifest 口径 · 如 "C7" / "C1-1")· 合法性端点层用 catalog 校验
    article_slug: Mapped[str] = mapped_column(String(32), nullable=False)
    # 所属阶(catalog 派生冗余 · 按阶统计用)· VARCHAR 不用 enum
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
