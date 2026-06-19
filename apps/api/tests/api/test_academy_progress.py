"""训练营学习进度 API pytest · B 期刀1(真 PG · CI 测试闸跑)。

🔴 覆盖:标记学完 + GET 返回 · ★幂等(同 user 同 slug 标两次只一条)· 取消标记 ·
未登录 GET 返空(不 401)· 非法 slug 拒绝(400)· 按 stage 汇总正确 · 未登录 POST 401。
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academy_progress import AcademyProgress
from app.services.auth import issue_session
from tests.factories import make_user


async def _authed(db: AsyncSession) -> tuple[Any, dict[str, str]]:
    user = await make_user(db)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return user, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_mark_complete_then_get(client: AsyncClient, db_session: AsyncSession) -> None:
    _user, headers = await _authed(db_session)
    r = await client.post(
        "/api/v1/academy/progress/complete", headers=headers, json={"article_slug": "A2"},
    )
    assert r.status_code == 200  # noqa: PLR2004
    body = r.json()
    assert body["article_slug"] == "A2"
    assert body["stage"] == "basics"          # ★ stage 服务端派生
    assert body["newly_completed"] is True

    g = await client.get("/api/v1/academy/progress", headers=headers)
    assert g.status_code == 200  # noqa: PLR2004
    gb = g.json()
    assert "A2" in gb["completed_slugs"]
    assert gb["by_stage"]["basics"] == 1
    assert gb["total_completed"] == 1
    assert gb["total_articles"] == 117  # noqa: PLR2004
    assert gb["stage_totals"]["basics"] == 11  # noqa: PLR2004


@pytest.mark.asyncio
async def test_mark_complete_idempotent(client: AsyncClient, db_session: AsyncSession) -> None:
    """★同 user 同 slug 标两次 → DB 只一条,第二次 newly_completed=False。"""
    user, headers = await _authed(db_session)
    r1 = await client.post(
        "/api/v1/academy/progress/complete", headers=headers, json={"article_slug": "B1"},
    )
    r2 = await client.post(
        "/api/v1/academy/progress/complete", headers=headers, json={"article_slug": "B1"},
    )
    assert r1.json()["newly_completed"] is True
    assert r2.status_code == 200  # noqa: PLR2004
    assert r2.json()["newly_completed"] is False   # 幂等:第二次不新建
    # DB 实证:只一条
    count = await db_session.scalar(
        select(func.count()).select_from(AcademyProgress).where(
            AcademyProgress.user_id == user.id, AcademyProgress.article_slug == "B1",
        ),
    )
    assert count == 1


@pytest.mark.asyncio
async def test_unmark_complete(client: AsyncClient, db_session: AsyncSession) -> None:
    _user, headers = await _authed(db_session)
    await client.post(
        "/api/v1/academy/progress/complete", headers=headers, json={"article_slug": "C7"},
    )
    d = await client.delete(
        "/api/v1/academy/progress/complete?article_slug=C7", headers=headers,
    )
    assert d.status_code == 200  # noqa: PLR2004
    assert d.json()["removed"] is True
    g = await client.get("/api/v1/academy/progress", headers=headers)
    assert "C7" not in g.json()["completed_slugs"]
    # 再删一次幂等:本就没有 → removed=False 不报错
    d2 = await client.delete(
        "/api/v1/academy/progress/complete?article_slug=C7", headers=headers,
    )
    assert d2.status_code == 200  # noqa: PLR2004
    assert d2.json()["removed"] is False


@pytest.mark.asyncio
async def test_get_unauthenticated_empty(client: AsyncClient) -> None:
    """★未登录 GET → 200 空进度(不 401,不破坏游客浏览)。"""
    g = await client.get("/api/v1/academy/progress")
    assert g.status_code == 200  # noqa: PLR2004
    gb = g.json()
    assert gb["completed_slugs"] == []
    assert gb["by_stage"] == {}
    assert gb["total_completed"] == 0
    assert gb["total_articles"] == 117  # noqa: PLR2004  # 总数仍返回(给游客看课程量)


@pytest.mark.asyncio
async def test_post_unauthenticated_401(client: AsyncClient) -> None:
    """未登录标记学完 → 401(强制登录)。"""
    r = await client.post(
        "/api/v1/academy/progress/complete", json={"article_slug": "A2"},
    )
    assert r.status_code == 401  # noqa: PLR2004


@pytest.mark.asyncio
async def test_invalid_slug_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    """★非法 slug → 400(防乱传脏数据)· DB 不落任何行。"""
    user, headers = await _authed(db_session)
    r = await client.post(
        "/api/v1/academy/progress/complete", headers=headers,
        json={"article_slug": "HACK999"},
    )
    assert r.status_code == 400  # noqa: PLR2004
    count = await db_session.scalar(
        select(func.count()).select_from(AcademyProgress).where(
            AcademyProgress.user_id == user.id,
        ),
    )
    assert count == 0


@pytest.mark.asyncio
async def test_by_stage_aggregation(client: AsyncClient, db_session: AsyncSession) -> None:
    """多篇跨阶 → by_stage 各阶完成数正确。"""
    _user, headers = await _authed(db_session)
    for slug in ("A2", "A3", "B1"):  # basics×2 + technical×1
        await client.post(
            "/api/v1/academy/progress/complete", headers=headers,
            json={"article_slug": slug},
        )
    gb = (await client.get("/api/v1/academy/progress", headers=headers)).json()
    assert gb["by_stage"]["basics"] == 2
    assert gb["by_stage"]["technical"] == 1
    assert gb["total_completed"] == 3
