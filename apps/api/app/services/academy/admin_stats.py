"""训练营「答题赢会员」管理员统计聚合 · B 期刀4(纯只读)。

🔴 纯只读:只 SELECT 聚合 academy_progress / academy_exam_result / academy_exam_award 三表 ·
   绝不碰发放逻辑(发会员仍只在刀3 exam_award)/ 交易 / 支付 · 不改任何表。
日趋势按 CN 自然日聚合(对齐 admin 注册趋势:func.date(func.timezone("Asia/Shanghai", ts)))。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models.academy_exam_award import AcademyExamAward
from app.models.academy_exam_result import AcademyExamResult
from app.models.academy_progress import AcademyProgress
from app.services.academy.catalog import STAGE_ORDER
from app.services.academy.exam_award import ACADEMY_AWARD_DAYS
from app.services.visit_stats import CN_TZ, cn_today


@dataclass(frozen=True)
class StageStat:
    stage: str
    learners: int       # 学完(有进度)人数(distinct user)
    submissions: int    # 结业测验提交数(全历史)
    passers: int        # 达标人数(distinct user · 曾 passed)
    awards: int         # 发会员人次(=该模块奖励行数)


@dataclass(frozen=True)
class DayCount:
    date: str
    count: int


@dataclass(frozen=True)
class AcademyStats:
    range_days: int
    learner_count: int            # 有学习记录人数(distinct user · 全历史)
    total_awards: int             # 总发会员人次
    membership_days_granted: int  # 送出会员天数 = 总发会员人次 × 7
    total_submissions: int        # 结业测验总提交
    pass_rate: float              # 整体通过率 = passed / 总提交(0~1)
    by_stage: list[StageStat]     # 6 模块分布(STAGE_ORDER 顺序 · 缺数据补 0)
    award_trend: list[DayCount]   # 发会员每日趋势(近 N 天)
    submission_trend: list[DayCount]  # 测验提交每日趋势(近 N 天)


async def _daily_trend(
    db: AsyncSession,
    ts_col: InstrumentedAttribute[datetime],
    start_dt: datetime,
    start: date_type,
    days: int,
) -> list[DayCount]:
    """某时间列按 CN 日聚合(窗口内 · 零填充缺失天)。"""
    day_col = func.date(func.timezone("Asia/Shanghai", ts_col)).label("d")
    rows = (
        await db.execute(
            select(day_col, func.count().label("c"))
            .where(ts_col >= start_dt)
            .group_by(day_col)
            .order_by(day_col),
        )
    ).all()
    day_map = {
        (r.d.isoformat() if hasattr(r.d, "isoformat") else str(r.d)): int(r.c) for r in rows
    }
    return [
        DayCount(
            date=(start + timedelta(days=i)).isoformat(),
            count=day_map.get((start + timedelta(days=i)).isoformat(), 0),
        )
        for i in range(days)
    ]


async def get_academy_stats(db: AsyncSession, *, days: int) -> AcademyStats:
    """训练营统计聚合 · 总览(全历史)+ 各模块分布(全历史)+ 趋势(近 N 天)。"""
    today = cn_today()
    start = today - timedelta(days=days - 1)
    start_dt = datetime(start.year, start.month, start.day, tzinfo=CN_TZ)

    # ── 总览(全历史累计)──
    learner_count = int(
        (await db.execute(select(func.count(distinct(AcademyProgress.user_id))))).scalar() or 0,
    )
    total_awards = int(
        (await db.execute(select(func.count()).select_from(AcademyExamAward))).scalar() or 0,
    )
    total_submissions = int(
        (await db.execute(select(func.count()).select_from(AcademyExamResult))).scalar() or 0,
    )
    passed_count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(AcademyExamResult)
                .where(AcademyExamResult.passed.is_(True)),
            )
        ).scalar()
        or 0,
    )
    pass_rate = round(passed_count / total_submissions, 4) if total_submissions else 0.0

    # ── 各模块分布(group by stage · 全历史)──
    learners_map = {
        row[0]: int(row[1])
        for row in (
            await db.execute(
                select(AcademyProgress.stage, func.count(distinct(AcademyProgress.user_id)))
                .group_by(AcademyProgress.stage),
            )
        ).all()
    }
    subs_map = {
        row[0]: int(row[1])
        for row in (
            await db.execute(
                select(AcademyExamResult.stage, func.count()).group_by(AcademyExamResult.stage),
            )
        ).all()
    }
    passers_map = {
        row[0]: int(row[1])
        for row in (
            await db.execute(
                select(AcademyExamResult.stage, func.count(distinct(AcademyExamResult.user_id)))
                .where(AcademyExamResult.passed.is_(True))
                .group_by(AcademyExamResult.stage),
            )
        ).all()
    }
    awards_map = {
        row[0]: int(row[1])
        for row in (
            await db.execute(
                select(AcademyExamAward.stage, func.count()).group_by(AcademyExamAward.stage),
            )
        ).all()
    }
    by_stage = [
        StageStat(
            stage=st,
            learners=learners_map.get(st, 0),
            submissions=subs_map.get(st, 0),
            passers=passers_map.get(st, 0),
            awards=awards_map.get(st, 0),
        )
        for st in STAGE_ORDER
    ]

    # ── 趋势(近 N 天 · CN 日)──
    award_trend = await _daily_trend(db, AcademyExamAward.awarded_at, start_dt, start, days)
    submission_trend = await _daily_trend(db, AcademyExamResult.submitted_at, start_dt, start, days)

    return AcademyStats(
        range_days=days,
        learner_count=learner_count,
        total_awards=total_awards,
        membership_days_granted=total_awards * ACADEMY_AWARD_DAYS,
        total_submissions=total_submissions,
        pass_rate=pass_rate,
        by_stage=by_stage,
        award_trend=award_trend,
        submission_trend=submission_trend,
    )
