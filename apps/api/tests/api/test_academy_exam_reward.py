"""结业达标发会员 pytest · B 期刀3(真 PG · ★会员=钱 · spy 钉死只发一次)。

🔴 覆盖(关键):首次达标 → extend_subscription 调 1 次(+7天 source=academy)·membership_awarded=true·
返 new_expires_at;重考达标 → 不调·awarded=false;未达标 → 不调;★幂等多次重考总共只调 1 次。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.academy.exam_award as award_mod
from app.services.academy.exams import EXAMS
from app.services.auth import issue_session
from tests.factories import make_user

_STAGE = "basics"


def _correct(stage: str) -> list[int]:
    return [q.answer_index for q in EXAMS[stage]]


def _wrong(stage: str) -> list[int]:
    return [(q.answer_index + 1) % 4 for q in EXAMS[stage]]


async def _authed(db: AsyncSession) -> tuple[Any, dict[str, str]]:
    user = await make_user(db)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return user, {"Authorization": f"Bearer {token}"}


def _spy_extend(monkeypatch: pytest.MonkeyPatch) -> list[tuple[UUID, int, str]]:
    """spy extend_subscription:记录每次调用 (user_id, days, source) 并委托真实实现(真发会员)。"""
    real = award_mod.extend_subscription
    calls: list[tuple[UUID, int, str]] = []

    async def spy(
        db: AsyncSession, user_id: UUID, days: int, source: str, **kw: Any,
    ) -> Any:
        calls.append((user_id, days, source))
        return await real(db, user_id, days, source, **kw)

    monkeypatch.setattr(award_mod, "extend_subscription", spy)
    return calls


async def _submit(
    client: AsyncClient, headers: dict[str, str], answers: list[int],
) -> dict[str, Any]:
    r = await client.post(
        "/api/v1/academy/exam/submit", headers=headers,
        json={"stage": _STAGE, "answers": answers},
    )
    assert r.status_code == 200  # noqa: PLR2004
    return r.json()


@pytest.mark.asyncio
async def test_first_pass_awards_one_week(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首次达标 → extend_subscription 调 1 次(+7天 academy)· awarded=true · 有 new_expires_at。"""
    _user, headers = await _authed(db_session)
    calls = _spy_extend(monkeypatch)

    body = await _submit(client, headers, _correct(_STAGE))
    assert body["passed"] is True
    assert body["membership_awarded"] is True
    assert body["new_expires_at"] is not None
    assert len(calls) == 1
    assert calls[0][1] == 7  # noqa: PLR2004 — 加 7 天
    assert calls[0][2] == "academy"  # source


@pytest.mark.asyncio
async def test_retake_pass_no_repeat_award(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★重考再达标 → extend_subscription 不再调 · awarded=false · 不重复发会员。"""
    _user, headers = await _authed(db_session)
    calls = _spy_extend(monkeypatch)

    first = await _submit(client, headers, _correct(_STAGE))
    assert first["membership_awarded"] is True
    assert len(calls) == 1

    retake = await _submit(client, headers, _correct(_STAGE))
    assert retake["passed"] is True
    assert retake["membership_awarded"] is False  # ★ 不重复发
    assert retake["new_expires_at"] is None
    assert len(calls) == 1  # ★ 仍只 1 次


@pytest.mark.asyncio
async def test_fail_no_award(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未达标 → 不发会员 · extend_subscription 不调。"""
    _user, headers = await _authed(db_session)
    calls = _spy_extend(monkeypatch)

    body = await _submit(client, headers, _wrong(_STAGE))
    assert body["passed"] is False
    assert body["membership_awarded"] is False
    assert len(calls) == 0


@pytest.mark.asyncio
async def test_idempotent_many_retakes_award_once(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★会员=钱 · 幂等:同 user 同 stage 连考 5 次达标 → extend_subscription 总共只调 1 次。"""
    _user, headers = await _authed(db_session)
    calls = _spy_extend(monkeypatch)

    awarded_count = 0
    for _ in range(5):
        body = await _submit(client, headers, _correct(_STAGE))
        if body["membership_awarded"]:
            awarded_count += 1
    assert awarded_count == 1  # 只有第一次 awarded
    assert len(calls) == 1  # ★ extend_subscription 只调 1 次


@pytest.mark.asyncio
async def test_award_uses_growth_engine() -> None:
    """★发会员复用现成 growth.extend_subscription(不新造)· source/天数常量正确。"""
    from app.services.academy.exam_award import (
        ACADEMY_AWARD_DAYS,
        ACADEMY_AWARD_SOURCE,
        award_membership_if_first_pass,
    )
    from app.services.growth import extend_subscription as growth_extend

    assert ACADEMY_AWARD_DAYS == 7  # noqa: PLR2004
    assert ACADEMY_AWARD_SOURCE == "academy"
    # award 服务里调的就是 growth 的 extend_subscription(同一函数对象)
    assert award_mod.extend_subscription is growth_extend
    assert callable(award_membership_if_first_pass)
