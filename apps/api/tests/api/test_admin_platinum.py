"""铂金标记 pytest(多账户 PR-1 权限层)· superadmin 手动设 · 享受所有 pro 权益。

★重点:① is_platinum=true → resolve_plan 返 'pro'(核心·一处全生效)· ② 端到端 /quota/me 返 pro ·
③ set-platinum 设/取 + 审计 + operator 防伪造 · ④ 403(非 admin)/ 404。
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_action_log import AdminActionLog
from app.models.user import User
from app.services.auth import issue_session
from app.services.membership import resolve_plan
from tests.factories import make_user


async def _admin(db: AsyncSession) -> tuple[Any, dict[str, str]]:
    admin = await make_user(db, role="admin")
    token = await issue_session(db, user_id=admin.id)
    await db.commit()
    return admin, {"Authorization": f"Bearer {token}"}


# ===== ★核心:is_platinum → resolve_plan 返 pro(一处全生效)=====


@pytest.mark.asyncio
async def test_platinum_resolves_pro(db_session: AsyncSession) -> None:
    user = await make_user(db_session)  # 无订阅 → 默认 free
    await db_session.commit()
    assert await resolve_plan(db_session, user.id) == "free"  # 设前 free
    user.is_platinum = True
    await db_session.commit()
    assert await resolve_plan(db_session, user.id) == "pro"  # ★设后 pro(享受所有 pro 权益)


# ===== ★端到端:set-platinum 后该用户 /quota/me 返 pro =====


@pytest.mark.asyncio
async def test_platinum_grants_pro_end_to_end(client: AsyncClient, db_session: AsyncSession) -> None:
    _admin_u, headers = await _admin(db_session)
    target = await make_user(db_session, password="pw12345678")
    await db_session.commit()

    # 设铂金前:quota/me = free
    login = await client.post(
        "/api/v1/auth/login", json={"email": target.email, "password": "pw12345678"},
    )
    tok = login.json()["access_token"]
    th = {"Authorization": f"Bearer {tok}"}
    assert (await client.get("/api/v1/quota/me", headers=th)).json()["plan"] == "free"

    # superadmin 设铂金
    await client.post(
        f"/api/v1/admin/users/{target.id}/set-platinum",
        headers=headers, json={"is_platinum": True},
    )
    # ★设后:同一用户 quota/me = pro(全库 pro 权益自动生效)
    assert (await client.get("/api/v1/quota/me", headers=th)).json()["plan"] == "pro"


# ===== 设置 + 审计 + operator 防伪造 =====


@pytest.mark.asyncio
async def test_set_platinum_writes_audit_and_flag(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    admin, headers = await _admin(db_session)
    target = await make_user(db_session)
    await db_session.commit()

    r = await client.post(
        f"/api/v1/admin/users/{target.id}/set-platinum",
        headers=headers, json={"is_platinum": True, "note": "做T测试"},
    )
    assert r.status_code == 200
    assert r.json()["is_platinum"] is True

    refreshed = await db_session.scalar(select(User).where(User.id == target.id))
    assert refreshed.is_platinum is True

    log = await db_session.scalar(
        select(AdminActionLog).where(AdminActionLog.target_user_id == target.id),
    )
    assert log is not None
    assert log.action == "set_platinum"
    assert log.operator_id == admin.id  # ★operator 取鉴权·不信前端
    assert log.detail["note"] == "做T测试"


@pytest.mark.asyncio
async def test_unset_platinum(client: AsyncClient, db_session: AsyncSession) -> None:
    _admin_u, headers = await _admin(db_session)
    target = await make_user(db_session)
    await db_session.commit()

    await client.post(
        f"/api/v1/admin/users/{target.id}/set-platinum",
        headers=headers, json={"is_platinum": True},
    )
    r = await client.post(
        f"/api/v1/admin/users/{target.id}/set-platinum",
        headers=headers, json={"is_platinum": False},
    )
    assert r.status_code == 200
    assert r.json()["is_platinum"] is False
    refreshed = await db_session.scalar(select(User).where(User.id == target.id))
    assert refreshed.is_platinum is False
    # 取消后回 free
    assert await resolve_plan(db_session, target.id) == "free"
    logs = (await db_session.execute(
        select(AdminActionLog).where(AdminActionLog.target_user_id == target.id),
    )).scalars().all()
    assert {x.action for x in logs} == {"set_platinum", "unset_platinum"}


# ===== 403 / 404 =====


@pytest.mark.asyncio
async def test_set_platinum_403_non_admin(client: AsyncClient, db_session: AsyncSession) -> None:
    target = await make_user(db_session)
    tok = await issue_session(db_session, user_id=target.id)
    await db_session.commit()
    r = await client.post(
        f"/api/v1/admin/users/{target.id}/set-platinum",
        headers={"Authorization": f"Bearer {tok}"}, json={"is_platinum": True},
    )
    assert r.status_code == 403  # ★只 superadmin 能设


@pytest.mark.asyncio
async def test_set_platinum_404_missing(client: AsyncClient, db_session: AsyncSession) -> None:
    _admin_u, headers = await _admin(db_session)
    r = await client.post(
        f"/api/v1/admin/users/{uuid.uuid4()}/set-platinum",
        headers=headers, json={"is_platinum": True},
    )
    assert r.status_code == 404
    r2 = await client.post(
        "/api/v1/admin/users/not-uuid/set-platinum", headers=headers, json={"is_platinum": True},
    )
    assert r2.status_code == 404
