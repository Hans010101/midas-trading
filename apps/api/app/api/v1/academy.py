"""训练营学习进度 API · B 期刀1(纯增量 · 只读写 academy_progress)。

- POST   /academy/progress/complete   {article_slug}  · CurrentUserDep(强制登录)· 幂等标记学完
- DELETE /academy/progress/complete?article_slug=...   · CurrentUserDep · 取消标记(toggle 用 · 幂等)
- GET    /academy/progress             · OptionalCurrentUserDep(未登录返空进度,不 401)

🔴 红线:学习进度域纯增量 · 不 import / 不碰 交易(virtual/engine)/ 支付 / 会员(subscription/redeem)。
article_slug 用 catalog 校验(只接受已知文章 · 防乱传脏数据)· stage 服务端从目录派生(不信前端)。
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, OptionalCurrentUserDep
from app.core.database import get_db
from app.services.academy.catalog import STAGE_TOTALS, is_valid_slug
from app.services.academy.progress import get_progress, mark_complete, unmark_complete

router = APIRouter(prefix="/academy", tags=["academy"])

DbDep = Annotated[AsyncSession, Depends(get_db)]

_TOTAL_ARTICLES = sum(STAGE_TOTALS.values())


class CompleteIn(BaseModel):
    article_slug: str = Field(min_length=1, max_length=32)


class CompleteOut(BaseModel):
    article_slug: str
    stage: str
    completed_at: datetime
    newly_completed: bool  # True=本次新标 / False=之前已标(幂等)


class UncompleteOut(BaseModel):
    article_slug: str
    removed: bool  # True=删了一条 / False=本就没标(幂等)


class ProgressOut(BaseModel):
    completed_slugs: list[str]          # 已完成的文章 slug(前端据此画绿勾)
    by_stage: dict[str, int]            # 各阶已完成数(进度 X)
    stage_totals: dict[str, int]        # 各阶文章总数(进度 Y · 后端目录权威)
    total_completed: int
    total_articles: int


def _require_valid_slug(raw: str) -> str:
    slug = raw.strip()
    if not is_valid_slug(slug):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"未知文章 slug: {slug}",
        )
    return slug


@router.post("/progress/complete", response_model=CompleteOut)
async def complete_article(
    payload: CompleteIn, user: CurrentUserDep, db: DbDep,
) -> CompleteOut:
    """标记学完(幂等)· 强制登录。slug 非法 → 400。"""
    slug = _require_valid_slug(payload.article_slug)
    row, newly = await mark_complete(db, user_id=user.id, article_slug=slug)
    return CompleteOut(
        article_slug=row.article_slug,
        stage=row.stage,
        completed_at=row.completed_at,
        newly_completed=newly,
    )


@router.delete("/progress/complete", response_model=UncompleteOut)
async def uncomplete_article(
    user: CurrentUserDep,
    db: DbDep,
    article_slug: Annotated[str, Query(min_length=1, max_length=32)],
) -> UncompleteOut:
    """取消标记(幂等 · toggle 用)· 强制登录。slug 非法 → 400。"""
    slug = _require_valid_slug(article_slug)
    removed = await unmark_complete(db, user_id=user.id, article_slug=slug)
    return UncompleteOut(article_slug=slug, removed=removed)


@router.get("/progress", response_model=ProgressOut)
async def get_my_progress(user: OptionalCurrentUserDep, db: DbDep) -> ProgressOut:
    """当前用户学习进度 · 未登录返回空进度(不 401 · 不破坏游客浏览)。"""
    if user is None:
        return ProgressOut(
            completed_slugs=[], by_stage={}, stage_totals=dict(STAGE_TOTALS),
            total_completed=0, total_articles=_TOTAL_ARTICLES,
        )
    slugs, by_stage = await get_progress(db, user_id=user.id)
    return ProgressOut(
        completed_slugs=slugs,
        by_stage=by_stage,
        stage_totals=dict(STAGE_TOTALS),
        total_completed=len(slugs),
        total_articles=_TOTAL_ARTICLES,
    )
