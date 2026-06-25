"""X 营销生成端点(阶段4a · PR-2)· AdminDep 403 矩阵 + enqueue happy。

★安全边界:POST /admin/x-tweets/generate 必须 admin(401 未登录 / 403 普通用户)。
happy path mock 掉 enqueue(不真连 Celery broker)· 验证返回 enqueued。
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth import issue_session
from tests.factories import make_user

_EP = "/api/v1/admin/x-tweets/generate"


async def _authed_headers(db: AsyncSession, *, role: str = "user") -> dict[str, str]:
    user = await make_user(db, role=role)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_generate_unauthenticated_401(client: AsyncClient) -> None:
    r = await client.post(_EP)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_generate_normal_user_403(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _authed_headers(db_session, role="user")
    r = await client.post(_EP, headers=headers)
    assert r.status_code == 403
    assert r.json()["detail"] == "Forbidden"


@pytest.mark.asyncio
async def test_generate_admin_enqueues(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    # mock enqueue(不真连 broker)· 验证 admin 触发返回 enqueued
    import app.api.v1.admin as admin_mod

    calls: list[object] = []
    monkeypatch.setattr(admin_mod, "enqueue_daily_generation", lambda uid: calls.append(uid))
    headers = await _authed_headers(db_session, role="admin")
    r = await client.post(_EP, headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "enqueued"
    assert len(calls) == 1  # ★确实 enqueue 了一次
