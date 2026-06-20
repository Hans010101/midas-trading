"""结业测验成绩落库 + 结业状态查询 · 训练营 B 期刀2。

🔴 纯增量:只读写 academy_exam_result · 不碰交易/支付/会员。
全历史(每次提交一行)→ 聚合出各模块「是否曾达标 + 最佳分 + 考试次数」。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academy_exam_result import AcademyExamResult


@dataclass(frozen=True)
class ExamStageStatus:
    stage: str
    passed: bool       # 曾达标(任一次)
    best_score: int
    total: int
    attempts: int


async def record_result(
    db: AsyncSession,
    *,
    user_id: UUID,
    stage: str,
    score: int,
    total: int,
    passed: bool,
) -> AcademyExamResult:
    """记一条成绩(可重考 → 每次提交都记)· score/passed 须由后端 score_exam 判定后传入。"""
    row = AcademyExamResult(
        user_id=user_id, stage=stage, score=score, total=total, passed=passed,
    )
    db.add(row)
    await db.commit()
    return row


async def get_exam_status(db: AsyncSession, *, user_id: UUID) -> list[ExamStageStatus]:
    """该用户各已考模块的结业态(类型化)。

    全历史聚合:passed = 任一次达标即 True(为刀3发会员幂等做准备);best_score = max(score)。
    """
    rows = (
        await db.execute(
            select(
                AcademyExamResult.stage,
                AcademyExamResult.score,
                AcademyExamResult.total,
                AcademyExamResult.passed,
            ).where(AcademyExamResult.user_id == user_id),
        )
    ).all()

    # 中间可变累加器
    acc: dict[str, dict[str, int | bool]] = {}
    for stage, score, total, passed in rows:
        st = acc.setdefault(
            stage, {"passed": False, "best_score": 0, "total": total, "attempts": 0},
        )
        st["attempts"] = int(st["attempts"]) + 1
        st["best_score"] = max(int(st["best_score"]), score)
        st["passed"] = bool(st["passed"]) or passed
        st["total"] = total  # 取最近一次题数(题库扩充时以最新为准)
    return [
        ExamStageStatus(
            stage=stage,
            passed=bool(st["passed"]),
            best_score=int(st["best_score"]),
            total=int(st["total"]),
            attempts=int(st["attempts"]),
        )
        for stage, st in acc.items()
    ]
