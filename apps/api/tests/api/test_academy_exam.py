"""模块结业测验 API + 判分 pytest · B 期刀2(真 PG · CI 测试闸跑)。

🔴 覆盖:后端判分正确 · ≥80% 达标线 · ★防作弊(GET 不下发答案 + 提交按后端答案判) ·
未登录 submit 401 / GET results 空 · 可重考(多次提交聚合最佳+曾达标)· 非法 stage 拒。
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academy_exam_result import AcademyExamResult
from app.services.academy.exams import EXAMS, PASS_RATIO, pass_line, score_exam
from app.services.auth import issue_session
from tests.factories import make_user

_STAGE = "basics"


def _correct_answers(stage: str) -> list[int]:
    return [q.answer_index for q in EXAMS[stage]]


def _all_wrong_answers(stage: str) -> list[int]:
    # 每题选一个 != 正确的下标 → 保证 0 分
    return [(q.answer_index + 1) % len(q.options) for q in EXAMS[stage]]


async def _authed(db: AsyncSession) -> tuple[Any, dict[str, str]]:
    user = await make_user(db)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return user, {"Authorization": f"Bearer {token}"}


# ===== 纯判分逻辑(无 DB)=====


def test_pass_line_80pct() -> None:
    assert pass_line(5) == math.ceil(5 * PASS_RATIO)  # 5→4
    assert pass_line(10) == 8
    assert pass_line(0) == 0


def test_score_all_correct_passes() -> None:
    s = score_exam(_STAGE, _correct_answers(_STAGE))
    assert s.score == s.total
    assert s.passed is True


def test_score_all_wrong_fails() -> None:
    s = score_exam(_STAGE, _all_wrong_answers(_STAGE))
    assert s.score == 0
    assert s.passed is False


def test_score_missing_answers_treated_wrong() -> None:
    s = score_exam(_STAGE, [])  # 没答 → 全错
    assert s.score == 0
    assert s.passed is False


# ===== 端点:防作弊 GET 不下发答案 =====


@pytest.mark.asyncio
async def test_get_exam_hides_answers(client: AsyncClient) -> None:
    """★GET 只下发 stem+options · 响应体绝不含 answer_index / correct / 正确答案。"""
    r = await client.get(f"/api/v1/academy/exam?stage={_STAGE}")
    assert r.status_code == 200  # noqa: PLR2004
    body = r.json()
    assert body["total"] == len(EXAMS[_STAGE])
    assert body["pass_line"] == pass_line(len(EXAMS[_STAGE]))
    for q in body["questions"]:
        assert set(q.keys()) == {"stem", "options"}  # ★ 无 answer_index/explanation
    assert "answer_index" not in r.text
    assert "correct_answer" not in r.text


@pytest.mark.asyncio
async def test_get_exam_invalid_stage_400(client: AsyncClient) -> None:
    r = await client.get("/api/v1/academy/exam?stage=不存在")
    assert r.status_code == 400  # noqa: PLR2004


# ===== 端点:提交判分(★后端判,前端无法谎报分)=====


@pytest.mark.asyncio
async def test_submit_correct_passes_and_records(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    user, headers = await _authed(db_session)
    r = await client.post(
        "/api/v1/academy/exam/submit", headers=headers,
        json={"stage": _STAGE, "answers": _correct_answers(_STAGE)},
    )
    assert r.status_code == 200  # noqa: PLR2004
    body = r.json()
    assert body["passed"] is True
    assert body["score"] == body["total"]
    assert len(body["results"]) == body["total"]  # 复盘:每题回传正确答案+解析
    # 落库一条
    cnt = await db_session.scalar(
        select(func.count()).select_from(AcademyExamResult).where(
            AcademyExamResult.user_id == user.id, AcademyExamResult.stage == _STAGE,
        ),
    )
    assert cnt == 1


@pytest.mark.asyncio
async def test_submit_wrong_fails(client: AsyncClient, db_session: AsyncSession) -> None:
    """★防作弊:即使前端选错答案,后端按自己的答案判 → 不及格(分数不由前端定)。"""
    _user, headers = await _authed(db_session)
    r = await client.post(
        "/api/v1/academy/exam/submit", headers=headers,
        json={"stage": _STAGE, "answers": _all_wrong_answers(_STAGE)},
    )
    assert r.status_code == 200  # noqa: PLR2004
    assert r.json()["passed"] is False
    assert r.json()["score"] == 0


@pytest.mark.asyncio
async def test_submit_unauthenticated_401(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/academy/exam/submit",
        json={"stage": _STAGE, "answers": _correct_answers(_STAGE)},
    )
    assert r.status_code == 401  # noqa: PLR2004


# ===== 可重考 + 结业状态聚合 =====


@pytest.mark.asyncio
async def test_retake_aggregates_best_and_passed(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """★可重考:先挂后过 → 两条记录;结业状态 passed=True(曾达标)+ best_score=最高。"""
    _user, headers = await _authed(db_session)
    # 第一次:全错(挂)
    await client.post(
        "/api/v1/academy/exam/submit", headers=headers,
        json={"stage": _STAGE, "answers": _all_wrong_answers(_STAGE)},
    )
    # 第二次:全对(过)
    await client.post(
        "/api/v1/academy/exam/submit", headers=headers,
        json={"stage": _STAGE, "answers": _correct_answers(_STAGE)},
    )
    res = await client.get("/api/v1/academy/exam/results", headers=headers)
    assert res.status_code == 200  # noqa: PLR2004
    items = {it["stage"]: it for it in res.json()["results"]}
    assert _STAGE in items
    assert items[_STAGE]["passed"] is True             # 曾达标
    assert items[_STAGE]["best_score"] == len(EXAMS[_STAGE])  # 最佳=满分
    assert items[_STAGE]["attempts"] == 2              # 两次考试


@pytest.mark.asyncio
async def test_results_unauthenticated_empty(client: AsyncClient) -> None:
    res = await client.get("/api/v1/academy/exam/results")
    assert res.status_code == 200  # noqa: PLR2004
    assert res.json()["results"] == []
