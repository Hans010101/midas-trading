"""用户语言偏好(i18n Phase 0)· PATCH /user/language + /auth/me 回显 · pytest。

🔴 覆盖:设 en/zh 成功 + /me 回显 · 新用户 NULL(跟随浏览器)· 非法语言 → 422 · 未登录 → 401。
需 PG(client + db_session fixture)· 本地无 PG 走 CI。
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth import issue_session
from tests.factories import make_user


async def _authed(db: AsyncSession) -> dict[str, str]:
    user = await make_user(db)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_set_language_en_success(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _authed(db_session)
    r = await client.patch("/api/v1/user/language", headers=headers, json={"language": "en"})
    assert r.status_code == 200  # noqa: PLR2004
    assert r.json()["language"] == "en"
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["language_pref"] == "en"


@pytest.mark.asyncio
async def test_set_language_zh_success(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _authed(db_session)
    r = await client.patch("/api/v1/user/language", headers=headers, json={"language": "zh"})
    assert r.status_code == 200  # noqa: PLR2004
    assert r.json()["language"] == "zh"


@pytest.mark.asyncio
async def test_me_default_language_null(client: AsyncClient, db_session: AsyncSession) -> None:
    """新用户 language_pref = NULL(前端据此跟随浏览器/cookie)。"""
    headers = await _authed(db_session)
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["language_pref"] is None


@pytest.mark.asyncio
async def test_set_language_invalid_422(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _authed(db_session)
    r = await client.patch("/api/v1/user/language", headers=headers, json={"language": "fr"})
    assert r.status_code == 422  # noqa: PLR2004


@pytest.mark.asyncio
async def test_set_language_unauthed_401(client: AsyncClient) -> None:
    r = await client.patch("/api/v1/user/language", json={"language": "en"})
    assert r.status_code == 401  # noqa: PLR2004
