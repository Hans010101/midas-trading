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
from app.services.visit_stats import cn_now, cn_today, read_redis_hours, record_visit
from tests.factories import make_user


async def _admin_headers(db: AsyncSession) -> dict[str, str]:
    admin = await make_user(db, role="admin")
    token = await issue_session(db, user_id=admin.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


async def _clear_today() -> None:
    """删今日 visit:* key(天级 + 24 小时级),隔离跨测试计数(key 全局按天 · 非 per-user)。"""
    redis = await get_redis()
    d = cn_today().isoformat()
    keys = [f"visit:pv:{d}", f"visit:uv:{d}"]
    for h in range(24):
        keys.extend((f"visit:pv:{d}:{h}", f"visit:uv:{d}:{h}"))
    await redis.delete(*keys)


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


# ===== ★ 当天 24 小时分布(情况B 新增小时采集)=====


@pytest.mark.asyncio
async def test_record_visit_writes_hour_bucket():
    """record_visit 显式 day+hour → read_redis_hours 对应桶 (pv, uv) 精确(同 vid 同小时去重)。"""
    redis = await get_redis()
    await _clear_today()
    d = cn_today()
    # 10 点:va×2 + vb×1 → pv=3 uv=2(va 去重)· 11 点:vc×1 → pv=1 uv=1
    for vid in ("va", "vb", "va"):
        await record_visit(redis, vid, day=d, hour=10)
    await record_visit(redis, "vc", day=d, hour=11)

    hours = await read_redis_hours(redis, d)
    assert len(hours) == 24, "★必须 24 个小时点"
    assert hours[10] == (3, 2), "★10 点 pv=3 uv=2(同小时同 vid 去重)"
    assert hours[11] == (1, 1)
    assert hours[0] == (0, 0), "★无访问的小时 → (0,0)"
    assert hours[23] == (0, 0)


@pytest.mark.asyncio
async def test_dashboard_hourly_24_points(client: AsyncClient, db_session: AsyncSession):
    """看板返回 hourly:24 点 · 索引=小时 0-23 · 本次访问全落同一 CST 小时桶(分桶口径正确)。"""
    await _clear_today()
    headers = await _admin_headers(db_session)
    for vid in ("va", "vb", "va"):  # pv=3 uv=2
        rr = await client.post("/api/v1/track/visit", json={"visitor_id": vid})
        assert rr.status_code == 204

    r = await client.get("/api/v1/admin/visit-stats?days=1", headers=headers)
    assert r.status_code == 200
    hourly = r.json()["hourly"]
    assert len(hourly) == 24
    assert [h["hour"] for h in hourly] == list(range(24)), "★小时 0-23 顺序"
    assert sum(h["pv"] for h in hourly) == 3, "★小时 PV 之和 = 总访问"
    # ★分桶口径:3 次访问全落【同一】CST 小时桶(不依赖具体哪个小时 · 避边界 flake)
    non_zero = [h for h in hourly if h["pv"] > 0]
    assert len(non_zero) == 1, "★同一时刻访问应聚到一个小时桶"
    assert non_zero[0]["pv"] == 3
    assert non_zero[0]["uv"] == 2  # 同 vid 去重
    assert non_zero[0]["hour"] == cn_now().hour, "★桶 = 当前 CST 小时(时区对)"
