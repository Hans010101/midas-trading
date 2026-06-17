"""个人中心:修改密码 + 头像选择器 · pytest。

🔴 覆盖:改密码(旧对→成功 · 旧错→400 · OAuth-only→409 · 弱密码→422 · ★明文不入返回)·
头像(0-16 存 · 0→NULL 恢复默认 · 超范围→422)· /auth/me 返 has_password + avatar_id · 未登录 401。
复用 hash_password/verify_password,不重造加密。
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth import issue_session, verify_password
from tests.factories import make_user

_DEFAULT_PW = "testpass1234"  # make_user 默认明文


async def _authed(
    db: AsyncSession, *, oauth_only: bool = False,
) -> tuple[Any, dict[str, str]]:
    user = await make_user(db)
    if oauth_only:
        user.password_hash = None  # 模拟 Google OAuth-only 用户(无密码)
        await db.flush()
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return user, {"Authorization": f"Bearer {token}"}


# ── 修改密码 ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_change_password_success(client: AsyncClient, db_session: AsyncSession) -> None:
    """旧密码对 → 写入新 hash(persisted)· ★ 响应体不含任何密码/hash 明文。"""
    user, headers = await _authed(db_session)
    r = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"old_password": _DEFAULT_PW, "new_password": "newpass5678"},
    )
    assert r.status_code == 200  # noqa: PLR2004
    # ★ 防泄露:返回体不含 password / hash
    assert "password" not in r.text.lower()
    assert "hash" not in r.text.lower()
    # 持久化:新密码可验、旧密码失效
    await db_session.refresh(user)
    assert verify_password("newpass5678", user.password_hash) is True
    assert verify_password(_DEFAULT_PW, user.password_hash) is False


@pytest.mark.asyncio
async def test_change_password_wrong_old_400(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    user, headers = await _authed(db_session)
    r = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"old_password": "wrongold", "new_password": "newpass5678"},
    )
    assert r.status_code == 400  # noqa: PLR2004
    await db_session.refresh(user)
    assert verify_password(_DEFAULT_PW, user.password_hash) is True  # 未变更


@pytest.mark.asyncio
async def test_change_password_oauth_user_409(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """🔴 OAuth-only 用户(password_hash=None)→ 409 拒(账户安全由 Google 管理)。"""
    _user, headers = await _authed(db_session, oauth_only=True)
    r = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"old_password": "anything", "new_password": "newpass5678"},
    )
    assert r.status_code == 409  # noqa: PLR2004


@pytest.mark.asyncio
async def test_change_password_weak_new_422(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _user, headers = await _authed(db_session)
    r = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"old_password": _DEFAULT_PW, "new_password": "short"},  # <8 位
    )
    assert r.status_code == 422  # noqa: PLR2004


@pytest.mark.asyncio
async def test_change_password_unauthed_401(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/change-password",
        json={"old_password": "x", "new_password": "newpass5678"},
    )
    assert r.status_code == 401  # noqa: PLR2004


# ── /auth/me 字段 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_me_returns_has_password_and_avatar(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _user, headers = await _authed(db_session)
    r = await client.get("/api/v1/auth/me", headers=headers)
    assert r.status_code == 200  # noqa: PLR2004
    body = r.json()
    assert body["has_password"] is True
    assert body["avatar_id"] is None  # 新用户默认首字母


@pytest.mark.asyncio
async def test_me_oauth_user_has_password_false(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _user, headers = await _authed(db_session, oauth_only=True)
    r = await client.get("/api/v1/auth/me", headers=headers)
    assert r.json()["has_password"] is False


# ── 头像 ────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_avatar_success(client: AsyncClient, db_session: AsyncSession) -> None:
    """选预设 7 → 存 7,/me 回显 7(★零图片存储 · 只存编号)。"""
    _user, headers = await _authed(db_session)
    r = await client.patch("/api/v1/user/avatar", headers=headers, json={"avatar_id": 7})
    assert r.status_code == 200  # noqa: PLR2004
    assert r.json()["avatar_id"] == 7  # noqa: PLR2004
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["avatar_id"] == 7  # noqa: PLR2004


@pytest.mark.asyncio
async def test_set_avatar_zero_resets_to_default(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """0 → NULL(恢复默认首字母)。"""
    _user, headers = await _authed(db_session)
    await client.patch("/api/v1/user/avatar", headers=headers, json={"avatar_id": 5})
    r = await client.patch("/api/v1/user/avatar", headers=headers, json={"avatar_id": 0})
    assert r.status_code == 200  # noqa: PLR2004
    assert r.json()["avatar_id"] is None
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["avatar_id"] is None


@pytest.mark.asyncio
async def test_set_avatar_out_of_range_422(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _user, headers = await _authed(db_session)
    too_big = await client.patch("/api/v1/user/avatar", headers=headers, json={"avatar_id": 17})
    assert too_big.status_code == 422  # noqa: PLR2004
    negative = await client.patch("/api/v1/user/avatar", headers=headers, json={"avatar_id": -1})
    assert negative.status_code == 422  # noqa: PLR2004


@pytest.mark.asyncio
async def test_set_avatar_unauthed_401(client: AsyncClient) -> None:
    r = await client.patch("/api/v1/user/avatar", json={"avatar_id": 3})
    assert r.status_code == 401  # noqa: PLR2004
