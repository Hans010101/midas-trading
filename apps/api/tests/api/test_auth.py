"""N7 回补:auth 路由 pytest · 8 个场景 + 2026-05-21 Session 回归覆盖。

涵盖:
- register: 成功 / 重复邮箱 409 / 未确认 18+ 400
- verify: 有效 token / 无效 token
- login: 成功(返回 session token)/ 未验证邮箱 403
- me: 有 session token 返回用户信息 · 旧 JWT 被拒
- session: 7 天滚动 · 5 设备上限 · logout · 过期清理
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.verification_token import VerificationToken
from app.services.auth import issue_session
from tests.factories import (
    make_unverified_user,
    make_user,
    make_verification_token,
    random_email,
)


@pytest.mark.asyncio
async def test_register_success_201(client: AsyncClient, db_session: AsyncSession):
    email = random_email()
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpass1234", "age_confirmed": True},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == email
    assert body["needs_verification"] is True

    # DB 状态:user 已建,email_verified_at 仍为 None
    user = await db_session.scalar(select(User).where(User.email == email))
    assert user is not None
    assert user.email_verified_at is None
    assert user.age_confirmed is True

    # 同时建了 verification_token
    token = await db_session.scalar(
        select(VerificationToken).where(VerificationToken.user_id == user.id),
    )
    assert token is not None


@pytest.mark.asyncio
async def test_register_duplicate_email_409(client: AsyncClient, db_session: AsyncSession):
    user = await make_user(db_session)
    await db_session.commit()  # 让 user 对路由内部新 session 可见(被 conftest savepoint 包裹)

    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": user.email,
            "password": "anotherpass1234",
            "age_confirmed": True,
        },
    )
    assert r.status_code == 409
    assert "已注册" in r.json()["detail"]


@pytest.mark.asyncio
async def test_register_age_not_confirmed_400(client: AsyncClient):
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": random_email(),
            "password": "testpass1234",
            "age_confirmed": False,
        },
    )
    assert r.status_code == 400
    assert "18" in r.json()["detail"]


@pytest.mark.asyncio
async def test_verify_with_valid_token_returns_true(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_unverified_user(db_session)
    token = await make_verification_token(db_session, user_id=user.id)
    await db_session.commit()

    r = await client.post(
        "/api/v1/auth/verify", json={"token": token.token},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is True
    assert body["email"] == user.email

    # DB:email_verified_at 已设
    await db_session.refresh(user)
    assert user.email_verified_at is not None


@pytest.mark.asyncio
async def test_verify_invalid_token_400(client: AsyncClient):
    r = await client.post(
        "/api/v1/auth/verify", json={"token": "not-a-real-token-xyz"},
    )
    assert r.status_code == 400
    assert "无效" in r.json()["detail"] or "过期" in r.json()["detail"]


@pytest.mark.asyncio
async def test_login_success_returns_jwt(
    client: AsyncClient, db_session: AsyncSession,
):
    password = "loginpass1234"
    user = await make_user(db_session, password=password, email_verified=True)
    await db_session.commit()

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["user_id"] == str(user.id)
    assert body["email"] == user.email
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_unverified_email_403(
    client: AsyncClient, db_session: AsyncSession,
):
    password = "loginpass1234"
    user = await make_unverified_user(db_session, password=password)
    await db_session.commit()

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    assert r.status_code == 403
    assert "未验证" in r.json()["detail"]


@pytest.mark.asyncio
async def test_me_with_session_returns_current_user(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_user(db_session)
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()

    r = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == str(user.id)
    assert body["email"] == user.email
    assert body["email_verified"] is True
    assert body["is_platinum"] is False  # ★默认非铂金(PR-6 门控数据源)


@pytest.mark.asyncio
async def test_me_returns_is_platinum_true_for_platinum_user(
    client: AsyncClient, db_session: AsyncSession,
):
    # ★铂金用户 /me 返 is_platinum=true(前端据此显铂金自助入口)
    user = await make_user(db_session, is_platinum=True)
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()
    r = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["is_platinum"] is True


@pytest.mark.asyncio
async def test_old_jwt_token_rejected_post_session_migration(
    client: AsyncClient, db_session: AsyncSession,
):
    """0006 ADR 2026-05-21 回归:旧 JWT 用户强制重登 · 任意非 session token 401。"""
    user = await make_user(db_session)
    await db_session.commit()

    # 模拟旧 JWT(或任何不在 session 表里的字符串)
    fake_jwt = "eyJhbGciOiJIUzI1NiJ9.fakefake.fakefake"
    r = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {fake_jwt}"},
    )
    assert r.status_code == 401
    _ = user  # silence unused


@pytest.mark.asyncio
async def test_logout_revokes_session(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_user(db_session)
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()

    # 登出前 me 能用
    r1 = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200

    # 登出
    r2 = await client.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    assert r2.json()["ok"] is True

    # 登出后 me 401
    r3 = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    assert r3.status_code == 401


@pytest.mark.asyncio
async def test_session_max_5_devices_evicts_oldest(
    client: AsyncClient, db_session: AsyncSession,
):
    """单用户最多 5 设备 · 第 6 次登录时最早的失效。"""
    from sqlalchemy import select as sqla_select

    from app.models.session import Session as AuthSession

    user = await make_user(db_session)
    tokens = []
    for i in range(6):
        tokens.append(
            await issue_session(
                db_session, user_id=user.id,
                user_agent=f"device-{i}",
            ),
        )
    await db_session.commit()

    # 应有 5 个 session(第 6 次登录 evict 了最早的)
    rows = (
        await db_session.execute(
            sqla_select(AuthSession).where(AuthSession.user_id == user.id),
        )
    ).scalars().all()
    assert len(rows) == 5

    # 第 0 个 token 应该已失效(被 evict)
    r0 = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens[0]}"},
    )
    assert r0.status_code == 401

    # 最新的 token(tokens[5])仍然能用
    r5 = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens[5]}"},
    )
    assert r5.status_code == 200


@pytest.mark.asyncio
async def test_session_rolling_ttl(
    client: AsyncClient, db_session: AsyncSession,
):
    """每次 verify 续 7 天 · last_used_at 更新。"""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select as sqla_select

    from app.models.session import Session as AuthSession

    user = await make_user(db_session)
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()

    # 手动把 expires_at 拨回到「快过期」(还有 1 小时)
    sess = (
        await db_session.execute(
            sqla_select(AuthSession).where(AuthSession.user_id == user.id),
        )
    ).scalar_one()
    near_expiry = datetime.now(tz=UTC) + timedelta(hours=1)
    sess.expires_at = near_expiry
    await db_session.commit()

    # 调一次 me,触发 verify_session 续期
    r = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200

    # 重读 · expires_at 应该被续到 ~7 天后
    await db_session.refresh(sess)
    days_left = (sess.expires_at - datetime.now(tz=UTC)).days
    assert days_left >= 6, f"expected 7d rolling but got {days_left}"
