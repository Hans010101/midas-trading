"""网站访问看板 API + 埋点 ingest pytest(访问看板模块)。

★ 重点:track ingest 记 PV/UV → admin /visit-stats 读回(Redis 实时叠加 · 不等 flush)·
   AdminDep 403 · UV 同 vid 去重 · 防滥用密钥静默忽略 · 注册趋势(user.created_at)·
   纯只读:/visit-stats 仅 GET · /track/visit 仅 POST。
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.services.auth import issue_session
from app.services.visit_stats import cn_today
from tests.factories import make_user


async def _admin_headers(db: AsyncSession) -> dict[str, str]:
    admin = await make_user(db, role="admin")
    token = await issue_session(db, user_id=admin.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


async def _clear_today() -> None:
    """删今日 visit:* key,隔离跨测试计数(key 是全局按天 · 非 per-user)。"""
    redis = await get_redis()
    d = cn_today().isoformat()
    await redis.delete(f"visit:pv:{d}", f"visit:uv:{d}")


# ===== AdminDep 边界 =====


@pytest.mark.asyncio
async def test_visit_stats_unauthenticated_401(client: AsyncClient):
    r = await client.get("/api/v1/admin/visit-stats")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_visit_stats_normal_user_403(client: AsyncClient, db_session: AsyncSession):
    u = await make_user(db_session)
    token = await issue_session(db_session, user_id=u.id)
    await db_session.commit()
    r = await client.get(
        "/api/v1/admin/visit-stats", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 403


# ===== 埋点 → 看板 端到端(真 Redis · PV/UV 去重)=====


@pytest.mark.asyncio
async def test_track_then_dashboard_pv_uv(client: AsyncClient, db_session: AsyncSession):
    await _clear_today()
    headers = await _admin_headers(db_session)
    # 同 vid 'va' 两次(PV+2 · UV+1)· vid 'vb' 一次(PV+1 · UV+1)→ 今日 pv=3 uv=2
    for vid in ("va", "vb", "va"):
        rr = await client.post("/api/v1/track/visit", json={"visitor_id": vid})
        assert rr.status_code == 204
    r = await client.get("/api/v1/admin/visit-stats?days=7", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["today"]["pv"] == 3
    assert data["today"]["uv"] == 2  # 同 vid 去重
    assert data["cumulative_pv"] == 3
    assert len(data["daily"]) == 7
    assert data["daily"][-1]["date"] == cn_today().isoformat()


@pytest.mark.asyncio
async def test_track_secret_mismatch_silently_ignored(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    from app.core.config import settings

    await _clear_today()
    monkeypatch.setattr(settings, "track_ingest_secret", "topsecret")
    headers = await _admin_headers(db_session)
    # 配了密钥但请求不带 header → 静默 204 + 不计数
    rr = await client.post("/api/v1/track/visit", json={"visitor_id": "x"})
    assert rr.status_code == 204
    r = await client.get("/api/v1/admin/visit-stats?days=1", headers=headers)
    assert r.json()["today"]["pv"] == 0


# ===== 注册趋势(user.created_at · 可回溯)=====


@pytest.mark.asyncio
async def test_visit_stats_registration_trend(client: AsyncClient, db_session: AsyncSession):
    headers = await _admin_headers(db_session)  # 建 1 个 admin
    await make_user(db_session)
    await make_user(db_session)
    await db_session.commit()
    r = await client.get("/api/v1/admin/visit-stats?days=30", headers=headers)
    data = r.json()
    assert data["total_registrations"] >= 3
    assert len(data["registrations"]) == 30
    today_reg = next(p for p in data["registrations"] if p["date"] == cn_today().isoformat())
    assert today_reg["count"] >= 3


# ===== 纯只读:仅 GET / 仅 POST(机器扫描)=====


def test_visit_stats_route_is_get_only():
    from app.api.v1 import router

    methods: set[str] = set()
    for r in router.routes:
        if getattr(r, "path", "") == "/admin/visit-stats":
            methods |= r.methods  # type: ignore[attr-defined]
    assert methods == {"GET"}


def test_track_visit_route_is_post_only():
    from app.api.v1 import router

    methods: set[str] = set()
    for r in router.routes:
        if getattr(r, "path", "") == "/track/visit":
            methods |= r.methods  # type: ignore[attr-defined]
    assert methods == {"POST"}
