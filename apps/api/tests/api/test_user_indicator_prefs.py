"""用户指标偏好(做T线后端)· GET/PATCH /user/indicator-prefs · pytest。

🔴 覆盖:新用户默认(布林/缠论 ON · 做T OFF)· PATCH 部分更新只改传入键 · 持久化 ·
   脏键忽略 · 未登录 401。需 PG(client + db_session)· 本地无 PG 走 CI。
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
async def test_defaults_for_new_user(client: AsyncClient, db_session: AsyncSession) -> None:
    """新用户 indicator_prefs=NULL → 合并默认:布林/缠论 ON · 做T OFF。"""
    headers = await _authed(db_session)
    r = await client.get("/api/v1/user/indicator-prefs", headers=headers)
    assert r.status_code == 200  # noqa: PLR2004
    assert r.json() == {"bollinger": True, "chan": True, "day_trade": False}


@pytest.mark.asyncio
async def test_patch_day_trade_on_persists(client: AsyncClient, db_session: AsyncSession) -> None:
    """开启做T · 其余键不动(部分更新)· GET 回读持久。"""
    headers = await _authed(db_session)
    r = await client.patch(
        "/api/v1/user/indicator-prefs", headers=headers, json={"day_trade": True},
    )
    assert r.status_code == 200  # noqa: PLR2004
    assert r.json() == {"bollinger": True, "chan": True, "day_trade": True}
    # 回读持久
    g = await client.get("/api/v1/user/indicator-prefs", headers=headers)
    assert g.json()["day_trade"] is True
    assert g.json()["bollinger"] is True


@pytest.mark.asyncio
async def test_patch_partial_only_changes_given(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """两次 PATCH:先关布林,再开做T · 布林保持关(未被第二次覆盖)。"""
    headers = await _authed(db_session)
    await client.patch("/api/v1/user/indicator-prefs", headers=headers, json={"bollinger": False})
    r = await client.patch(
        "/api/v1/user/indicator-prefs", headers=headers, json={"day_trade": True},
    )
    assert r.json() == {"bollinger": False, "chan": True, "day_trade": True}


@pytest.mark.asyncio
async def test_unknown_key_ignored(client: AsyncClient, db_session: AsyncSession) -> None:
    """脏键(前端乱传)被忽略 · 只保留已知三键。"""
    headers = await _authed(db_session)
    r = await client.patch(
        "/api/v1/user/indicator-prefs", headers=headers,
        json={"day_trade": True, "hack": True, "rm": "-rf"},
    )
    assert r.status_code == 200  # noqa: PLR2004
    assert set(r.json()) == {"bollinger", "chan", "day_trade"}
    assert r.json()["day_trade"] is True


@pytest.mark.asyncio
async def test_unauthenticated_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/user/indicator-prefs")).status_code == 401  # noqa: PLR2004
    assert (
        await client.patch("/api/v1/user/indicator-prefs", json={"day_trade": True})
    ).status_code == 401  # noqa: PLR2004
