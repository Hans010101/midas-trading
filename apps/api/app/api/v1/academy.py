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
from app.services.academy.exam_award import award_membership_if_first_pass
from app.services.academy.exam_results import get_exam_status, record_result
from app.services.academy.exams import (
    PASS_RATIO,
    exam_total,
    has_exam,
    pass_line,
    public_questions,
    score_exam,
)
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


# ===== 模块结业测验(刀2)· ★防作弊:答案只在后端,前端拿题不拿答案、提交选项后端判分 =====


class ExamQuestionPublic(BaseModel):
    stem: str
    options: list[str]  # ★ 不含 answer_index(防作弊)


class ExamQuestionsOut(BaseModel):
    stage: str
    questions: list[ExamQuestionPublic]
    total: int
    pass_line: int   # 及格题数(≥ 即达标)
    pass_ratio: float


class SubmitExamIn(BaseModel):
    stage: str = Field(min_length=1, max_length=16)
    # 每题选中的【原始】选项下标(前端洗牌后须映射回原序提交)· 缺答/越界按答错
    answers: list[int] = Field(default_factory=list)


class QuestionResultOut(BaseModel):
    question_index: int
    your_answer: int | None
    correct_answer: int       # 提交后才回传(供复盘)
    is_correct: bool
    explanation: str


class SubmitExamOut(BaseModel):
    stage: str
    score: int
    total: int
    pass_line: int
    passed: bool
    results: list[QuestionResultOut]
    # 刀3:首次达标发 1 周会员 · membership_awarded=True 仅首次达标(重考不重复发)
    membership_awarded: bool = False
    new_expires_at: datetime | None = None  # 本次发了会员才有(新会员到期日)


class ExamStatusItem(BaseModel):
    stage: str
    passed: bool       # 曾达标(任一次)
    best_score: int
    total: int
    attempts: int


class ExamResultsOut(BaseModel):
    results: list[ExamStatusItem]


def _require_valid_stage(raw: str) -> str:
    stage = raw.strip()
    if not has_exam(stage):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"未知模块或暂无结业测验: {stage}",
        )
    return stage


@router.get("/exam", response_model=ExamQuestionsOut)
async def get_exam(stage: Annotated[str, Query(min_length=1, max_length=16)]) -> ExamQuestionsOut:
    """取某模块结业测验题 · ★只下发题干+选项(无答案)· 公开可读(答题需登录)。"""
    s = _require_valid_stage(stage)
    total = exam_total(s)
    return ExamQuestionsOut(
        stage=s,
        questions=[
            ExamQuestionPublic(stem=q.stem, options=list(q.options))
            for q in public_questions(s)
        ],
        total=total,
        pass_line=pass_line(total),
        pass_ratio=PASS_RATIO,
    )


@router.post("/exam/submit", response_model=SubmitExamOut)
async def submit_exam(
    payload: SubmitExamIn, user: CurrentUserDep, db: DbDep,
) -> SubmitExamOut:
    """提交结业测验 · ★后端用 exams.py 答案重新判分(前端传的分数一律不信)· 记成绩(可重考)。"""
    s = _require_valid_stage(payload.stage)
    scored = score_exam(s, payload.answers)
    await record_result(
        db, user_id=user.id, stage=s,
        score=scored.score, total=scored.total, passed=scored.passed,
    )
    # 刀3:达标 → 首次发 1 周会员(★复用 extend_subscription · UNIQUE 原子幂等只发一次)·
    #   未达标不发;重考已达标不重复发。只碰发会员一处,不碰交易/支付。
    membership_awarded = False
    new_expires_at = None
    if scored.passed:
        membership_awarded, new_expires_at = await award_membership_if_first_pass(
            db, user_id=user.id, stage=s,
        )
    return SubmitExamOut(
        stage=s,
        score=scored.score,
        total=scored.total,
        pass_line=scored.pass_line,
        passed=scored.passed,
        results=[
            QuestionResultOut(
                question_index=r.question_index,
                your_answer=r.your_answer,
                correct_answer=r.correct_answer,
                is_correct=r.is_correct,
                explanation=r.explanation,
            )
            for r in scored.results
        ],
        membership_awarded=membership_awarded,
        new_expires_at=new_expires_at,
    )


@router.get("/exam/results", response_model=ExamResultsOut)
async def get_exam_results(user: OptionalCurrentUserDep, db: DbDep) -> ExamResultsOut:
    """当前用户各模块结业状态 · 未登录返回空(不 401)。"""
    if user is None:
        return ExamResultsOut(results=[])
    status_list = await get_exam_status(db, user_id=user.id)
    return ExamResultsOut(
        results=[
            ExamStatusItem(
                stage=s.stage,
                passed=s.passed,
                best_score=s.best_score,
                total=s.total,
                attempts=s.attempts,
            )
            for s in status_list
        ],
    )
