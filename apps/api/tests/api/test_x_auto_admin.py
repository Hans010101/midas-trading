"""X 营销自动托管端点(PR-1)· status / toggle / stop(紧急熔断)。

★安全边界:AdminDep 403 矩阵 + 开关默认 OFF + stop 关开关+熔断+revoke。
stop 的 revoke 走 Celery → mock 掉(不真连 broker)。
"""

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
        "/api/v1/admin/x-auto/status", headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_toggle_unauthenticated_401(client: AsyncClient) -> None:
    r = await client.post("/api/v1/admin/x-auto/toggle", json={"enabled": True})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_toggle_and_status(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin_headers(db_session)
    # 开 → status enabled=True
    r = await client.post("/api/v1/admin/x-auto/toggle", json={"enabled": True}, headers=headers)
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    s = await client.get("/api/v1/admin/x-auto/status", headers=headers)
    assert s.json()["enabled"] is True
    assert "daily_remaining" in s.json()
    # 关
    r2 = await client.post("/api/v1/admin/x-auto/toggle", json={"enabled": False}, headers=headers)
    assert r2.json()["enabled"] is False


@pytest.mark.asyncio
async def test_stop_disables_and_circuits(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    # mock revoke(不真连 broker)
    monkeypatch.setattr("app.api.v1.admin.revoke_auto_tasks", lambda ids: len(ids))
    headers = await _admin_headers(db_session)
    await client.post("/api/v1/admin/x-auto/toggle", json={"enabled": True}, headers=headers)
    r = await client.post("/api/v1/admin/x-auto/stop", headers=headers)
    assert r.status_code == 200
    assert r.json()["stopped"] is True
    # ★熔断后:开关关 + circuit 开
    s = await client.get("/api/v1/admin/x-auto/status", headers=headers)
    assert s.json()["enabled"] is False
    assert s.json()["circuit_open"] is True


# ── ★架子刀(ADR 0050):平台勾选端点 + status.platforms ──────────────────


@pytest.mark.asyncio
async def test_status_contains_platforms(client: AsyncClient, db_session: AsyncSession) -> None:
    """status 带平台清单:binance 默认勾选+白名单内;x 默认不勾+★auto_allowed=False(暂未启用)。"""
    headers = await _admin_headers(db_session)
    r = await client.get("/api/v1/admin/x-auto/status", headers=headers)
    assert r.status_code == 200
    by_p = {p["platform"]: p for p in r.json()["platforms"]}
    assert by_p["binance_square"]["checked"] is True       # 默认 ON(现状零变化)
    assert by_p["binance_square"]["auto_allowed"] is True  # 白名单内
    assert by_p["x"]["checked"] is False                   # ★默认 OFF
    assert by_p["x"]["auto_allowed"] is False              # ★白名单外 = 暂未启用(UI 灰显)


@pytest.mark.asyncio
async def test_platform_toggle_binance_ok(client: AsyncClient, db_session: AsyncSession) -> None:
    """勾/取消币安(白名单内)→ 200 · status 里 checked 跟着变。"""
    headers = await _admin_headers(db_session)
    r = await client.post(
        "/api/v1/admin/x-auto/platforms/binance_square",
        json={"checked": False}, headers=headers,
    )
    assert r.status_code == 200
    by_p = {p["platform"]: p for p in r.json()["platforms"]}
    assert by_p["binance_square"]["checked"] is False
    r2 = await client.post(
        "/api/v1/admin/x-auto/platforms/binance_square",
        json={"checked": True}, headers=headers,
    )
    assert {p["platform"]: p for p in r2.json()["platforms"]}["binance_square"]["checked"] is True


@pytest.mark.asyncio
async def test_platform_toggle_x_rejected_400(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """★★红线:X 在白名单外 → 连勾选值都不可写(400)· 配置层同焊死(双保险之一)。"""
    headers = await _admin_headers(db_session)
    r = await client.post(
        "/api/v1/admin/x-auto/platforms/x", json={"checked": True}, headers=headers,
    )
    assert r.status_code == 400
    assert "暂未启用" in r.json()["detail"]


@pytest.mark.asyncio
async def test_platform_toggle_unknown_400(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(db_session)
    r = await client.post(
        "/api/v1/admin/x-auto/platforms/weibo", json={"checked": True}, headers=headers,
    )
    assert r.status_code == 400
    assert "未知平台" in r.json()["detail"]


@pytest.mark.asyncio
async def test_platform_toggle_normal_user_403(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    user = await make_user(db_session, role="user")
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()
    r = await client.post(
        "/api/v1/admin/x-auto/platforms/binance_square",
        json={"checked": False}, headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
