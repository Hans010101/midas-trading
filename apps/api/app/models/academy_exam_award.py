"""结业测验会员奖励记录 · 训练营 B 期刀3。

🔴 会员=钱 · 只发一次:(user_id, stage) UNIQUE —— 一个用户一个模块的结业会员奖励,
   无论重考多少次只发一次。首次达标用 ON CONFLICT DO NOTHING 原子抢占(并发也只一个赢),
   赢者才调 extend_subscription 发 1 周会员;此表即「已发会员」的权威记录(幂等防护)。

设计:与 academy_exam_result(全历史成绩)分离——成绩可多条、奖励只一条;
   分离让幂等判定不依赖全历史查询的 TOCTOU(UNIQUE 约束是硬保证)。

🔴 红线:本表只记奖励发放事实 · 发放走现成 growth.extend_subscription · 不碰交易/支付。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AcademyExamAward(Base):
    __tablename__ = "academy_exam_award"
    __table_args__ = (
        # ★ 一个用户一个模块只发一次会员(原子幂等的硬保证)
        UniqueConstraint("user_id", "stage", name="uq_academy_exam_award_user_stage"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
    )
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    awarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
