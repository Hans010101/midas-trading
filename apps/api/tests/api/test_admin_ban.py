"""管理员封禁/解封 pytest(用户管理刀3b-2 · 方案A 禁止登录 · 动登录链)。

★ 重点:封禁后登录被拒(邮箱+OAuth 两路)· 现有 session 立即失效 · 解封恢复 ·
不能自封 · ★★ 不误伤正常用户 · 审计 · operator 防伪造 · 403/404。
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_action_log import AdminActionLog
from app.models.user import User
from app.services.auth import issue_session
from tests.factories import make_user


async def _admin(db: AsyncSession) -> tuple[Any, dict[str, str]]:
    admin = await make_user(db, role="admin")
    token = await issue_session(db, user_id=admin.id)
    await db.commit()
    return admin, {"Authorization": f"Bearer {token}"}


# ===== 封禁 + 审计 =====


@pytest.mark.asyncio
async def test_ban_writes_audit_and_flag(client: AsyncClient, db_session: AsyncSession):
    admin, headers = await _admin(db_session)
    target = await make_user(db_session)
    await db_session.commit()

    r = await client.post(
        f"/api/v1/admin/users/{target.id}/ban", headers=headers, json={"note": "违规"},
    )
    assert r.status_code == 200
    assert r.json()["banned"] is True

    refreshed = await db_session.scalar(select(User).where(User.id == target.id))
    assert refreshed.banned_at is not None

    log = await db_session.scalar(
        select(AdminActionLog).where(AdminActionLog.target_user_id == target.id),
    )
    assert log is not None
    assert log.action == "ban"
    assert log.operator_id == admin.id  # operator 取鉴权
    assert log.detail["note"] == "违规"


# ===== ★ 封禁后登录被拒(邮箱路)=====


@pytest.mark.asyncio
async def test_banned_email_login_rejected(client: AsyncClient, db_session: AsyncSession):
    _admin_u, headers = await _admin(db_session)
    target = await make_user(db_session, password="pw12345678")
    await db_session.commit()

    # 封禁前能登
    ok = await client.post(
        "/api/v1/auth/login", json={"email": target.email, "password": "pw12345678"},
    )
    assert ok.status_code == 200

    # 封禁
    await client.post(f"/api/v1/admin/users/{target.id}/ban", headers=headers, json={})

    # 封禁后登录被拒 403 "账号已被停用"
    r = await client.post(
        "/api/v1/auth/login", json={"email": target.email, "password": "pw12345678"},
    )
    assert r.status_code == 403
    assert "停用" in r.json()["detail"]


# ===== ★ 现有 session 立即失效 =====


@pytest.mark.asyncio
async def test_banned_existing_session_invalidated(client: AsyncClient, db_session: AsyncSession):
    """已登录用户被封 → 持有效 token 请求受保护端点即被拒(get_current_user banned 检查)。"""
    _admin_u, headers = await _admin(db_session)
    target = await make_user(db_session)
    tok = await issue_session(db_session, user_id=target.id)
    await db_session.commit()
    th = {"Authorization": f"Bearer {tok}"}

    # 封禁前:受保护端点(/auth/me)正常
    assert (await client.get("/api/v1/auth/me", headers=th)).status_code == 200

    # 封禁
    await client.post(f"/api/v1/admin/users/{target.id}/ban", headers=headers, json={})

    # 封禁后:同一有效 token 立即被拒 403
    r = await client.get("/api/v1/auth/me", headers=th)
    assert r.status_code == 403
    assert "停用" in r.json()["detail"]


# ===== 解封恢复 =====


@pytest.mark.asyncio
async def test_unban_restores_access(client: AsyncClient, db_session: AsyncSession):
    _admin_u, headers = await _admin(db_session)
    target = await make_user(db_session, password="pw12345678")
    await db_session.commit()

    await client.post(f"/api/v1/admin/users/{target.id}/ban", headers=headers, json={})
    ru = await client.post(f"/api/v1/admin/users/{target.id}/unban", headers=headers, json={})
    assert ru.status_code == 200
    assert ru.json()["banned"] is False

    # 解封后登录恢复
    r = await client.post(
        "/api/v1/auth/login", json={"email": target.email, "password": "pw12345678"},
    )
    assert r.status_code == 200
    # 审计两条(ban + unban)
    logs = (await db_session.execute(
        select(AdminActionLog).where(AdminActionLog.target_user_id == target.id),
    )).scalars().all()
    assert {x.action for x in logs} == {"ban", "unban"}


# ===== ★ 不能自封 =====


@pytest.mark.asyncio
async def test_cannot_ban_self(client: AsyncClient, db_session: AsyncSession):
    admin, headers = await _admin(db_session)
    r = await client.post(f"/api/v1/admin/users/{admin.id}/ban", headers=headers, json={})
    assert r.status_code == 400
    assert "自己" in r.json()["detail"]
    # admin 自己未被封
    refreshed = await db_session.scalar(select(User).where(User.id == admin.id))
    assert refreshed.banned_at is None


# ===== ★★ 不误伤:正常用户登录 + 请求不受影响 =====


@pytest.mark.asyncio
async def test_normal_user_unaffected(client: AsyncClient, db_session: AsyncSession):
    """未封禁用户登录 + 受保护请求完全正常(banned 检查不误伤)。"""
    user = await make_user(db_session, password="pw12345678")
    await db_session.commit()
    login = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "pw12345678"},
    )
    assert login.status_code == 200
    tok = login.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200
    assert me.json()["email"] == user.email


# ===== 403 / 404 =====


@pytest.mark.asyncio
async def test_ban_403_non_admin(client: AsyncClient, db_session: AsyncSession):
    target = await make_user(db_session)
    tok = await issue_session(db_session, user_id=target.id)
    await db_session.commit()
    r = await client.post(
        f"/api/v1/admin/users/{target.id}/ban",
        headers={"Authorization": f"Bearer {tok}"}, json={},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_ban_404_missing(client: AsyncClient, db_session: AsyncSession):
    import uuid

    _admin_u, headers = await _admin(db_session)
    r = await client.post(f"/api/v1/admin/users/{uuid.uuid4()}/ban", headers=headers, json={})
    assert r.status_code == 404
    r2 = await client.post("/api/v1/admin/users/not-uuid/ban", headers=headers, json={})
    assert r2.status_code == 404
