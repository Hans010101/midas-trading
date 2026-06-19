"""学习进度 service · 训练营 B 期刀1。

🔴 纯增量:只读写 academy_progress 表 · 不 import 交易/支付/会员。
幂等:标记学完走 PG ON CONFLICT DO NOTHING(user_id, article_slug)→ 重复标记不报错、不重复记、
   completed_at 保持首次标记时间。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academy_progress import AcademyProgress
from app.services.academy.catalog import stage_of


async def mark_complete(
    db: AsyncSession, *, user_id: UUID, article_slug: str,
) -> tuple[AcademyProgress, bool]:
    """标记某用户学完某篇 · 幂等。返回 (进度行, 本次是否新建)。

    调用方须先 catalog.is_valid_slug 校验;此处 stage 从 catalog 派生(不信前端)。
    ON CONFLICT DO NOTHING:并发/重复标记恰好一条,completed_at 保持首次时间。
    """
    stage = stage_of(article_slug) or ""
    stmt = (
        pg_insert(AcademyProgress)
        .values(user_id=user_id, article_slug=article_slug, stage=stage)
        .on_conflict_do_nothing(index_elements=["user_id", "article_slug"])
        .returning(AcademyProgress.id)  # 新插返 id;冲突(已存在)返空 → 判幂等
    )
    new_id = (await db.execute(stmt)).scalar_one_or_none()
    await db.commit()
    row = await db.scalar(
        select(AcademyProgress).where(
            AcademyProgress.user_id == user_id,
            AcademyProgress.article_slug == article_slug,
        ),
    )
    assert row is not None  # 刚 upsert 过必存在  # noqa: S101
    return row, new_id is not None


async def unmark_complete(
    db: AsyncSession, *, user_id: UUID, article_slug: str,
) -> bool:
    """取消标记(可选 · 给前端 toggle 用)· 返回是否删了一行(幂等:本就没有也不报错)。"""
    deleted_id = (
        await db.execute(
            delete(AcademyProgress)
            .where(
                AcademyProgress.user_id == user_id,
                AcademyProgress.article_slug == article_slug,
            )
            .returning(AcademyProgress.id),
        )
    ).scalar_one_or_none()
    await db.commit()
    return deleted_id is not None


async def get_progress(
    db: AsyncSession, *, user_id: UUID,
) -> tuple[list[str], dict[str, int]]:
    """该用户已完成的 (article_slug 列表, 各阶完成数)。"""
    rows = (
        await db.execute(
            select(AcademyProgress.article_slug, AcademyProgress.stage).where(
                AcademyProgress.user_id == user_id,
            ),
        )
    ).all()
    slugs = [r[0] for r in rows]
    by_stage: dict[str, int] = {}
    for _slug, stage in rows:
        by_stage[stage] = by_stage.get(stage, 0) + 1
    return slugs, by_stage
