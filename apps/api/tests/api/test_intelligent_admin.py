"""智能交易 PR-2 · admin 端点 status / toggle / 账户管理(★AdminDep 403 + 默认 OFF + 金额管理)。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth import issue_session
from tests.factories import make_user


async def _admin_headers(db: AsyncSession) -> dict[str, str]:
    user = await make_user(db, role="admin")
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_status_normal_user_403(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session, role="user")
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()
    r = await client.get(
        "/api/v1/admin/intelligent/status", headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_toggle_unauthenticated_401(client: AsyncClient) -> None:
    r = await client.post("/api/v1/admin/intelligent/toggle", json={"enabled": True})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_status_default_off_no_account(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin_headers(db_session)
    r = await client.get("/api/v1/admin/intelligent/status", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False        # ★默认 OFF
    assert body["account_ready"] is False  # 还没建账户


@pytest.mark.asyncio
async def test_toggle_on_provisions_account(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin_headers(db_session)
    r = await client.post("/api/v1/admin/intelligent/toggle", json={"enabled": True}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["account_ready"] is True              # ★开则幂等建账户
    assert body["initial_capital"] == 100000.0        # 默认 10万U
    assert body["cash_balance"] == 100000.0
    assert body["open_positions"] == 0


@pytest.mark.asyncio
async def test_set_capital_changes_initial(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin_headers(db_session)
    r = await client.post(
        "/api/v1/admin/intelligent/account/capital", json={"amount": 50000}, headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["initial_capital"] == 50000.0  # ★金额改了
    assert r.json()["cash_balance"] == 50000.0


@pytest.mark.asyncio
async def test_set_capital_invalid(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin_headers(db_session)
    r = await client.post(
        "/api/v1/admin/intelligent/account/capital", json={"amount": 0}, headers=headers,
    )
    assert r.status_code == 400  # ★金额 ≤ 0 非法


@pytest.mark.asyncio
async def test_reset_account_endpoint(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin_headers(db_session)
    # 先开(建账户)→ reset → 200 + cash 重置
    await client.post("/api/v1/admin/intelligent/toggle", json={"enabled": True}, headers=headers)
    r = await client.post("/api/v1/admin/intelligent/account/reset", headers=headers)
    assert r.status_code == 200
    assert r.json()["cash_balance"] == r.json()["initial_capital"]
