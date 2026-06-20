"""训练营管理员统计 pytest · B 期刀4(真 PG)。

🔴 覆盖:★AdminDep 403 矩阵(未登录 401 / 普通用户 403 / admin 200)+ 聚合正确性
(count distinct 学习人数 / group by stage 各模块 / 发会员人次 / 送出天数=次数×7 / 通过率)。
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academy_exam_award import AcademyExamAward
from app.models.academy_exam_result import AcademyExamResult
from app.models.academy_progress import AcademyProgress
from app.services.auth import issue_session
from tests.factories import make_user

_ENDPOINT = "/api/v1/admin/academy-stats"


async def _headers(db: AsyncSession, *, role: str = "user") -> dict[str, str]:
    user = await make_user(db, role=role)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


# ===== ★ 403 矩阵 =====


@pytest.mark.asyncio
async def test_unauthenticated_401(client: AsyncClient) -> None:
    r = await client.get(_ENDPOINT)
    assert r.status_code == 401  # noqa: PLR2004


@pytest.mark.asyncio
async def test_normal_user_403(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _headers(db_session, role="user")
    r = await client.get(_ENDPOINT, headers=headers)
    assert r.status_code == 403  # noqa: PLR2004
    assert "admin" not in r.json()["detail"].lower()  # 不泄露需要 admin 语义


@pytest.mark.asyncio
async def test_admin_200(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _headers(db_session, role="admin")
    r = await client.get(_ENDPOINT, headers=headers)
    assert r.status_code == 200  # noqa: PLR2004


# ===== 聚合正确性 =====


@pytest.mark.asyncio
async def test_aggregation_counts(client: AsyncClient, db_session: AsyncSession) -> None:
    """造数据验:学习人数(distinct)/各模块/发会员人次/送出天数=×7/通过率。"""
    admin = await make_user(db_session, role="admin")
    admin_token = await issue_session(db_session, user_id=admin.id)
    u1 = await make_user(db_session)
    u2 = await make_user(db_session)
    await db_session.commit()

    # 学习进度:u1 学 basics 2 篇;u2 学 basics 1 篇 + technical 1 篇 → 学习人数=2
    db_session.add_all([
        AcademyProgress(user_id=u1.id, article_slug="A2", stage="basics"),
        AcademyProgress(user_id=u1.id, article_slug="A3", stage="basics"),
        AcademyProgress(user_id=u2.id, article_slug="A2", stage="basics"),
        AcademyProgress(user_id=u2.id, article_slug="B1", stage="technical"),
    ])
    # 测验成绩:u1 basics 达标;u2 basics 未达标 → 提交2 通过1 通过率0.5
    db_session.add_all([
        AcademyExamResult(user_id=u1.id, stage="basics", score=12, total=12, passed=True),
        AcademyExamResult(user_id=u2.id, stage="basics", score=5, total=12, passed=False),
    ])
    # 发会员:u1 basics 1 次 → 总1次 送出7天
    db_session.add(AcademyExamAward(user_id=u1.id, stage="basics"))
    await db_session.commit()

    r = await client.get(
        f"{_ENDPOINT}?days=30", headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200  # noqa: PLR2004
    d: dict[str, Any] = r.json()

    assert d["learner_count"] == 2  # ★ distinct 学习人数  # noqa: PLR2004
    assert d["total_submissions"] == 2  # noqa: PLR2004
    assert d["total_awards"] == 1
    assert d["membership_days_granted"] == 7  # ★ 1 次 × 7 天  # noqa: PLR2004
    assert d["pass_rate"] == 0.5  # 1/2  # noqa: PLR2004

    by_stage = {s["stage"]: s for s in d["by_stage"]}
    assert by_stage["basics"]["learners"] == 2  # u1+u2  # noqa: PLR2004
    assert by_stage["basics"]["submissions"] == 2  # noqa: PLR2004
    assert by_stage["basics"]["passers"] == 1  # 仅 u1 达标
    assert by_stage["basics"]["awards"] == 1
    assert by_stage["technical"]["learners"] == 1  # 仅 u2
    assert by_stage["technical"]["awards"] == 0
    # 6 模块都在(STAGE_ORDER · 缺数据补 0)
    assert len(d["by_stage"]) == 6  # noqa: PLR2004

    # 趋势:窗口含今日 · 今日造的奖励/提交都落点 → 趋势求和=总数
    assert sum(p["count"] for p in d["award_trend"]) == 1
    assert sum(p["count"] for p in d["submission_trend"]) == 2  # noqa: PLR2004
    assert len(d["award_trend"]) == 30  # days  # noqa: PLR2004
