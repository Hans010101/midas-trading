"""结业测验成绩 SQLAlchemy model · 训练营 B 期刀2。

设计(对齐项目规范 · 纯增量新表 · 不碰任何现有表):
- ★全历史:每次提交记一条(支持可重考 + 完整审计 + 进步轨迹)· 不做 (user_id,stage) unique。
- 「该用户该模块是否已达标」= 存在 passed=True 的行(为刀3发会员幂等做准备);
  「最佳分」= 该 user+stage 的 max(score)。
- passed/score 由后端 exams.score_exam 判定后落库(★前端传的分数不信)。
- VARCHAR 不用 enum;时区 aware datetime;正式 Alembic 迁移建表。

🔴 红线:结业测验域纯增量 · 与交易/支付/会员零关系(本刀只发荣誉不发会员)。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AcademyExamResult(Base):
    __tablename__ = "academy_exam_result"
    __table_args__ = (
        # 按 user+stage 查结业状态/最佳分(全历史多行)
        Index("ix_academy_exam_result_user_stage", "user_id", "stage"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
    )
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)   # 答对题数
    total: Mapped[int] = mapped_column(Integer, nullable=False)   # 总题数
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
