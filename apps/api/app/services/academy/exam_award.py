"""结业测验达标 → 发 1 周会员 · 训练营 B 期刀3。

🔴 会员=钱 · 只发一次(幂等):academy_exam_award 的 (user_id, stage) UNIQUE 是硬保证。
   首次达标 ON CONFLICT DO NOTHING 原子抢占 → 只有赢者调 extend_subscription 发会员;
   重考/并发再达标 → 抢占失败(返回空)→ 绝不重复发。

🔴 红线:发会员【复用现成 growth.extend_subscription(已被 trial/invite/paid/admin 四源验证)】,
   不新造发放逻辑;extend_subscription 本就与交易引擎物理隔离。source="academy"(第 6 个来源标识)。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academy_exam_award import AcademyExamAward
from app.services.growth import extend_subscription

# 结业达标奖励 = 1 周会员(系统按天累加)
ACADEMY_AWARD_DAYS = 7
ACADEMY_AWARD_SOURCE = "academy"


async def award_membership_if_first_pass(
    db: AsyncSession, *, user_id: UUID, stage: str,
) -> tuple[bool, datetime | None]:
    """首次达标该模块 → 发 1 周会员;重考/已发 → 不重复发。

    幂等:(user_id, stage) UNIQUE + ON CONFLICT DO NOTHING 原子抢占 ——
    无论重考/并发多少次,只有第一次插入成功者发会员。
    返回 (本次是否新发会员, 新会员到期日 / None)。
    """
    claimed = (
        await db.execute(
            pg_insert(AcademyExamAward)
            .values(user_id=user_id, stage=stage)
            .on_conflict_do_nothing(index_elements=["user_id", "stage"])
            .returning(AcademyExamAward.id),
        )
    ).scalar_one_or_none()

    if claimed is None:
        return False, None  # 已发过(重考)或并发抢占失败 → 不重复发

    # ★ 赢者发会员:复用现成引擎(加 7 天)· 奖励记录 + 会员延长同事务提交
    new_expires_at = await extend_subscription(
        db, user_id, ACADEMY_AWARD_DAYS, ACADEMY_AWARD_SOURCE,
    )
    await db.commit()
    return True, new_expires_at
