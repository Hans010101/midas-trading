"""会员 Phase 1 刀1 · 额度系统 pytest。

★ 本刀重点:
- 429 矩阵(free 超额 / pro 大额度内 200)· detail 结构断言
- 缓存命中不扣额度(扣减位置的灵魂)
- 回测创建失败不扣
- 🔴 红线终扫:遍历路由表机器证明 QuotaDep 只挂两个目标端点
- plan 解析:无行 / 过期行 / 非 active → free
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_clickhouse
from app.core.redis_client import get_redis
from app.main import app
from app.models.subscription import Subscription
from app.services.auth import issue_session
from app.services.membership import (
    PLAN_QUOTAS,
    consume_quota,
    get_quota_used,
    make_quota_consumer,
    quota_key,
    resolve_plan,
)
from tests.api.test_structure_api import _canned_diagnosis
from tests.factories import make_user

# ===== helpers =====


@pytest.fixture(autouse=True)
def _clean_ch_override():
    yield
    app.dependency_overrides.pop(get_clickhouse, None)


async def _authed_user(db: AsyncSession) -> tuple[Any, dict[str, str]]:
    user = await make_user(db)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return user, {"Authorization": f"Bearer {token}"}


async def _set_used(user_id: Any, feature: str, n: int) -> None:
    redis = await get_redis()
    await redis.set(quota_key(user_id, feature), n, ex=3600)


# ===== plan 解析(无行 / 过期 / 非 active → free)=====


@pytest.mark.asyncio
async def test_resolve_plan_no_row_is_free(db_session: AsyncSession):
    user = await make_user(db_session)
    assert await resolve_plan(db_session, user.id) == "free"


@pytest.mark.asyncio
async def test_resolve_plan_active_pro(db_session: AsyncSession):
    user = await make_user(db_session)
    db_session.add(Subscription(user_id=user.id, plan="pro", status="active", source="manual"))
    await db_session.flush()
    assert await resolve_plan(db_session, user.id) == "pro"


@pytest.mark.asyncio
async def test_resolve_plan_expired_or_inactive_is_free(db_session: AsyncSession):
    expired = await make_user(db_session)
    db_session.add(Subscription(
        user_id=expired.id, plan="pro", status="active", source="manual",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    ))
    canceled = await make_user(db_session)
    db_session.add(Subscription(
        user_id=canceled.id, plan="pro", status="canceled", source="manual",
    ))
    await db_session.flush()
    assert await resolve_plan(db_session, expired.id) == "free"
    assert await resolve_plan(db_session, canceled.id) == "free"


# ===== 429 矩阵(diagnose)=====


@pytest.mark.asyncio
async def test_diagnose_free_quota_exceeded_429(
    client: AsyncClient, db_session: AsyncSession,
):
    """free 用完 20 次 → 下一次 429 · detail 结构钉死。"""
    user, headers = await _authed_user(db_session)
    await _set_used(user.id, "diagnose", PLAN_QUOTAS["free"]["diagnose"])  # used=20

    app.dependency_overrides[get_clickhouse] = lambda: SimpleNamespace(_client=object())
    r = await client.post(
        "/api/v1/structure/diagnose",
        headers=headers,
        json={"symbol": "BTCUSDT", "question": "整体结构看一下"},
    )
    assert r.status_code == 429
    detail = r.json()["detail"]
    assert detail["error"] == "quota_exceeded"
    assert detail["feature"] == "diagnose"
    assert detail["plan"] == "free"
    assert detail["limit"] == 20
    assert detail["used"] == 20
    assert "reset_at" in detail


@pytest.mark.asyncio
async def test_diagnose_pro_within_quota_200(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """pro 用户 used=20(free 的红线)仍 200(pro limit=100)· service 整体 mock。"""
    user, headers = await _authed_user(db_session)
    db_session.add(Subscription(user_id=user.id, plan="pro", status="active", source="manual"))
    await db_session.commit()
    await _set_used(user.id, "diagnose", 20)

    app.dependency_overrides[get_clickhouse] = lambda: SimpleNamespace(_client=object())

    async def fake_diag(*_args: Any, **_kwargs: Any) -> Any:
        return _canned_diagnosis()

    monkeypatch.setattr("app.api.v1.structure.get_structure_diagnosis", fake_diag)
    r = await client.post(
        "/api/v1/structure/diagnose",
        headers=headers,
        json={"symbol": "BTCUSDT", "question": "整体结构看一下"},
    )
    assert r.status_code == 200


# ===== ★ 缓存命中不扣(扣减位置的灵魂)=====


@pytest.mark.asyncio
async def test_diagnose_cache_hit_does_not_consume(db_session: AsyncSession):
    """get_structure_diagnosis 命中缓存:on_llm_run 不被调 → 计数不变。

    直接测 service 层(缓存逻辑所在层):塞缓存 → 调用 → used 仍为 0。
    """
    from app.services.structure.workflow import (
        _cache_key,
        get_structure_diagnosis,
        parse_intent,
    )

    user = await make_user(db_session)
    canned = _canned_diagnosis()
    question = "BTC 现在多头是不是太拥挤"  # parse_intent → 与 canned.intent 同桶即可
    key = _cache_key("BTCUSDT", parse_intent(question))
    redis = await get_redis()
    await redis.setex(key, 60, json.dumps(canned.model_dump(mode="json"), ensure_ascii=False))

    result = await get_structure_diagnosis(
        object(),  # type: ignore[arg-type] — 命中缓存不会触 CH client
        "BTCUSDT",
        question,
        user_id=str(user.id),
        on_llm_run=make_quota_consumer(user.id, "diagnose"),
    )
    assert result.conclusion == canned.conclusion
    assert await get_quota_used(user.id, "diagnose") == 0  # ★ 命中不扣


@pytest.mark.asyncio
async def test_consume_quota_increments_with_ttl():
    """consume → used+1 · 多次累计 · 键带 TTL(48h 自动清)。"""
    fake_user_id = uuid4()
    assert await get_quota_used(fake_user_id, "diagnose") == 0
    await consume_quota(fake_user_id, "diagnose")
    await consume_quota(fake_user_id, "diagnose")
    assert await get_quota_used(fake_user_id, "diagnose") == 2
    redis = await get_redis()
    assert await redis.ttl(quota_key(fake_user_id, "diagnose")) > 0


# ===== 回测:超额 429 / 创建失败不扣 =====


@pytest.mark.asyncio
async def test_backtest_quota_exceeded_429(client: AsyncClient, db_session: AsyncSession):
    user, headers = await _authed_user(db_session)
    await _set_used(user.id, "backtest", PLAN_QUOTAS["free"]["backtest"])  # used=10
    r = await client.post(
        "/api/v1/backtest",
        headers=headers,
        json={
            "symbol": "BTCUSDT", "market": "crypto", "period": "1d",
            "start": "2025-01-01", "end": "2025-06-01",
        },
    )
    assert r.status_code == 429
    assert r.json()["detail"]["feature"] == "backtest"


@pytest.mark.asyncio
async def test_backtest_create_failure_does_not_consume(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """create_pending_run 抛错 → 异常上抛且计数不变(创建成功才扣)。"""
    user, headers = await _authed_user(db_session)

    async def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("db down (test)")

    monkeypatch.setattr("app.api.v1.backtest.create_pending_run", boom)
    with pytest.raises(RuntimeError, match="db down"):
        await client.post(
            "/api/v1/backtest",
            headers=headers,
            json={
                "symbol": "BTCUSDT", "market": "crypto", "period": "1d",
                "start": "2025-01-01", "end": "2025-06-01",
            },
        )
    assert await get_quota_used(user.id, "backtest") == 0


# ===== GET /quota/me =====


@pytest.mark.asyncio
async def test_quota_me_shape_and_counts(client: AsyncClient, db_session: AsyncSession):
    user, headers = await _authed_user(db_session)
    await _set_used(user.id, "diagnose", 3)
    r = await client.get("/api/v1/quota/me", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "free"
    by_feature = {it["feature"]: it for it in body["items"]}
    assert by_feature["diagnose"] == {"feature": "diagnose", "limit": 20, "used": 3}
    assert by_feature["backtest"] == {"feature": "backtest", "limit": 10, "used": 0}
    assert "reset_at" in body

    r2 = await client.get("/api/v1/quota/me")
    assert r2.status_code == 401  # authed-only


# ===== 🔴 红线终扫:QuotaDep 只挂两个目标端点(机器证明)=====


def _routes_with_quota_dep() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        stack = [dependant]
        hit = False
        while stack:
            d = stack.pop()
            call = getattr(d, "call", None)
            qualname = getattr(call, "__qualname__", "")
            if qualname.startswith("require_quota."):
                hit = True
            stack.extend(getattr(d, "dependencies", []))
        if hit:
            methods = getattr(route, "methods", set()) or set()
            found.extend((m, route.path) for m in methods)
    return sorted(found)


def test_quota_dep_mounted_on_exactly_two_endpoints():
    """🔴 遍历全路由:额度闸只在 diagnose + backtest POST,其余端点零挂载。

    交易链路(virtual/perp/conditional)/行情/决策卡/chan/strategy 永远不挂 ——
    新端点误挂 / 目标端点漏挂都会让这条红。
    """
    assert _routes_with_quota_dep() == [
        ("POST", "/api/v1/backtest"),
        ("POST", "/api/v1/structure/diagnose"),
    ]
