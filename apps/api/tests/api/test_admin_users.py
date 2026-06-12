"""管理员用户列表 API pytest(用户管理刀1)。

★ 403 矩阵是本刀重点:AdminDep 是 admin 端点唯一安全边界,
  未登录 401 / 普通用户 403 / admin 200 三态钉死,一个不漏。
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth import issue_session
from tests.factories import make_user

# ===== helpers =====


async def _authed_headers(db: AsyncSession, *, role: str = "user") -> dict[str, str]:
    user = await make_user(db, role=role)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


# ===== ★ 403 矩阵(未登录 401 / 普通用户 403 / admin 200)=====


@pytest.mark.asyncio
async def test_admin_users_unauthenticated_401(client: AsyncClient):
    r = await client.get("/api/v1/admin/users")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_admin_users_normal_user_403(client: AsyncClient, db_session: AsyncSession):
    headers = await _authed_headers(db_session, role="user")
    r = await client.get("/api/v1/admin/users", headers=headers)
    assert r.status_code == 403
    # detail 用通用 Forbidden · 不泄露「需要 admin」语义
    assert r.json()["detail"] == "Forbidden"
    assert "admin" not in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_admin_users_admin_200(client: AsyncClient, db_session: AsyncSession):
    headers = await _authed_headers(db_session, role="admin")
    r = await client.get("/api/v1/admin/users", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert body["page"] == 1
    assert body["page_size"] == 20


# ===== 默认 role / me 带 role =====


@pytest.mark.asyncio
async def test_default_role_is_user(client: AsyncClient, db_session: AsyncSession):
    user = await make_user(db_session)
    assert user.role == "user"

    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()
    r = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "user"


@pytest.mark.asyncio
async def test_me_returns_admin_role(client: AsyncClient, db_session: AsyncSession):
    admin = await make_user(db_session, role="admin")
    token = await issue_session(db_session, user_id=admin.id)
    await db_session.commit()
    r = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    assert r.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_login_returns_role(client: AsyncClient, db_session: AsyncSession):
    admin = await make_user(db_session, role="admin", password="adminpass1234")
    await db_session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": admin.email, "password": "adminpass1234"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


# ===== 列表行为:分页 / 注册方式推导 / last_active =====


@pytest.mark.asyncio
async def test_pagination_and_total(client: AsyncClient, db_session: AsyncSession):
    headers = await _authed_headers(db_session, role="admin")  # 含 admin 自己 = 1 人
    for _ in range(3):
        await make_user(db_session)
    await db_session.commit()

    r1 = await client.get(
        "/api/v1/admin/users", headers=headers, params={"page": 1, "page_size": 2},
    )
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["total"] == 4
    assert len(b1["items"]) == 2
    r2 = await client.get(
        "/api/v1/admin/users", headers=headers, params={"page": 2, "page_size": 2},
    )
    assert len(r2.json()["items"]) == 2

    # page_size 上限 100(防全表 dump)· 越界 422
    r_bad = await client.get(
        "/api/v1/admin/users", headers=headers, params={"page_size": 101},
    )
    assert r_bad.status_code == 422


@pytest.mark.asyncio
async def test_register_method_derivation(client: AsyncClient, db_session: AsyncSession):
    headers = await _authed_headers(db_session, role="admin")
    pw_user = await make_user(db_session)  # password-only(工厂默认)
    g_user = await make_user(db_session)
    g_user.password_hash = None
    g_user.google_sub = "gsub-test-1"
    both_user = await make_user(db_session)
    both_user.google_sub = "gsub-test-2"
    await db_session.commit()

    r = await client.get(
        "/api/v1/admin/users", headers=headers, params={"page_size": 100},
    )
    by_email = {it["email"]: it for it in r.json()["items"]}
    assert by_email[pw_user.email]["register_method"] == "password"
    assert by_email[g_user.email]["register_method"] == "google"
    assert by_email[both_user.email]["register_method"] == "both"


@pytest.mark.asyncio
async def test_last_active_and_session_count(client: AsyncClient, db_session: AsyncSession):
    headers = await _authed_headers(db_session, role="admin")
    idle = await make_user(db_session)  # 无 session
    active = await make_user(db_session)
    await issue_session(db_session, user_id=active.id)
    await issue_session(db_session, user_id=active.id)  # 2 设备
    await db_session.commit()

    r = await client.get(
        "/api/v1/admin/users", headers=headers, params={"page_size": 100},
    )
    by_email = {it["email"]: it for it in r.json()["items"]}
    assert by_email[idle.email]["last_active_7d"] is None
    assert by_email[idle.email]["active_sessions"] == 0
    assert by_email[active.email]["last_active_7d"] is not None
    assert by_email[active.email]["active_sessions"] == 2
    # 验证字段齐全(email_verified 工厂默认 True)
    assert by_email[active.email]["email_verified"] is True
    assert by_email[active.email]["role"] == "user"
