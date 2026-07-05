"""SEO 批6 · 来源归因链路端到端(需真 Redis + PG · CI 真跑)。

覆盖:track /visit 带来源字段 → Redis 桶 → flush 落三表 → admin /source-stats 读回;
/track/crawler → 爬虫计数;admin 端点 401/403 边界。范式对齐 tests/api/test_visit_stats.py
(真 get_redis + db_session · make_user + issue_session · 每测隔离清 key)。
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.services.auth import issue_session
from app.services.visit_stats import cn_today, flush_source_recent_days
from tests.factories import make_user


async def _clear_src_keys() -> None:
    redis = await get_redis()
    d = cn_today().isoformat()
    await redis.delete(f"visit:src:{d}", f"visit:ref:{d}", f"visit:crawler:{d}")


async def _admin_headers(db: AsyncSession) -> dict[str, str]:
    admin = await make_user(db, role="admin")
    token = await issue_session(db, user_id=admin.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


# ── AdminDep 边界 ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_source_stats_unauthenticated_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/admin/source-stats")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_source_stats_normal_user_403(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    u = await make_user(db_session)
    token = await issue_session(db_session, user_id=u.id)
    await db_session.commit()
    r = await client.get(
        "/api/v1/admin/source-stats", headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


# ── 来源归因链路:track → Redis → flush → admin 读回 ─────────────────────────
@pytest.mark.asyncio
async def test_track_source_then_admin_source_stats(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    await _clear_src_keys()
    posts = [
        {"visitor_id": "v1", "ref_host": "www.google.com"},
        {"visitor_id": "v2", "ref_host": "google.com.hk"},
        {"visitor_id": "v3", "ref_host": "www.google.com"},
        {"visitor_id": "v4", "ref_host": "chat.openai.com"},
        {"visitor_id": "v5", "utm_source": "newsletter"},
    ]
    for body in posts:
        rr = await client.post("/api/v1/track/visit", json=body)
        assert rr.status_code == 204

    redis = await get_redis()
    await flush_source_recent_days(db_session, redis)

    r = await client.get(
        "/api/v1/admin/source-stats", headers=await _admin_headers(db_session),
    )
    assert r.status_code == 200
    data = r.json()
    src = {s["source"]: s["pv"] for s in data["sources"]}
    assert src.get("google") == 3
    assert src.get("chatgpt") == 1
    assert src.get("newsletter") == 1
    assert data["total_attributed_pv"] == 5
    refs = {x["referrer"]: x["pv"] for x in data["top_referrers"]}
    assert refs.get("google.com") == 2  # www.google.com ×2 归一同 host
    assert refs.get("chat.openai.com") == 1


@pytest.mark.asyncio
async def test_track_visit_without_source_still_ok(client: AsyncClient) -> None:
    """★向后兼容:老 payload {visitor_id}(无来源字段)仍 204 · 不计来源。"""
    await _clear_src_keys()
    rr = await client.post("/api/v1/track/visit", json={"visitor_id": "vx"})
    assert rr.status_code == 204
    redis = await get_redis()
    assert await redis.hgetall(f"visit:src:{cn_today().isoformat()}") == {}


@pytest.mark.asyncio
async def test_track_crawler_counts(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    await _clear_src_keys()
    for bot in ("GPTBot", "GPTBot", "PerplexityBot"):
        rr = await client.post("/api/v1/track/crawler", json={"bot": bot})
        assert rr.status_code == 204

    redis = await get_redis()
    await flush_source_recent_days(db_session, redis)
    r = await client.get(
        "/api/v1/admin/source-stats", headers=await _admin_headers(db_session),
    )
    assert r.status_code == 200
    crawlers = {c["bot"]: c["hits"] for c in r.json()["crawlers"]}
    assert crawlers.get("GPTBot") == 2
    assert crawlers.get("PerplexityBot") == 1
