"""N7 回补:auth 路由 pytest · 8 个场景。

涵盖:
- register: 成功 / 重复邮箱 409 / 未确认 18+ 400
- verify: 有效 token / 无效 token
- login: 成功 / 未验证邮箱 403
- me: 有 JWT 返回用户信息
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.verification_token import VerificationToken
from app.services.auth import issue_access_token
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
async def test_me_with_jwt_returns_current_user(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_user(db_session)
    await db_session.commit()

    jwt = issue_access_token(user.id)
    r = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {jwt}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == str(user.id)
    assert body["email"] == user.email
    assert body["email_verified"] is True
