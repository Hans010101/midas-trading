"""告警规则路由 pytest · 0025 G2b · CRUD + registry 校验 + DP6 上限 + 跨用户隔离。"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_rule import AlertRule
from app.services.auth import issue_session
from tests.factories import make_user


async def _auth(user, db: AsyncSession) -> dict[str, str]:  # type: ignore[no-untyped-def]
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_indicators(client: AsyncClient, db_session: AsyncSession):
    user = await make_user(db_session)
    await db_session.commit()
    r = await client.get(
        "/api/v1/alert-rules/indicators", headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    keys = {d["key"] for d in r.json()}
    # 覆盖各类:技术 / crypto 衍生 / 全局 / 市场结构
    assert {"rsi_14", "funding_rate", "fear_greed", "cn_breadth_up_ratio"} <= keys


@pytest.mark.asyncio
async def test_create_valid_per_symbol(client: AsyncClient, db_session: AsyncSession):
    user = await make_user(db_session)
    await db_session.commit()
    r = await client.post(
        "/api/v1/alert-rules",
        json={
            "market": "us", "symbol": "NVDA", "indicator": "rsi_14",
            "operator": "gt", "threshold": 70, "timeframe": "1d",
        },
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["indicator"] == "rsi_14"
    assert body["symbol"] == "NVDA"
    assert body["enabled"] is True


@pytest.mark.asyncio
async def test_create_unknown_indicator_400(client: AsyncClient, db_session: AsyncSession):
    user = await make_user(db_session)
    await db_session.commit()
    r = await client.post(
        "/api/v1/alert-rules",
        json={"market": "us", "symbol": "NVDA", "indicator": "bogus", "operator": "gt", "threshold": 1},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 400
    assert "未知指标" in r.json()["detail"]


@pytest.mark.asyncio
async def test_create_wrong_market_400(client: AsyncClient, db_session: AsyncSession):
    """funding_rate 只支持 crypto · 用 us → 400。"""
    user = await make_user(db_session)
    await db_session.commit()
    r = await client.post(
        "/api/v1/alert-rules",
        json={"market": "us", "symbol": "NVDA", "indicator": "funding_rate", "operator": "gt", "threshold": 0},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 400
    assert "不支持市场" in r.json()["detail"]


@pytest.mark.asyncio
async def test_create_missing_symbol_400(client: AsyncClient, db_session: AsyncSession):
    """per-symbol 指标缺 symbol → 400。"""
    user = await make_user(db_session)
    await db_session.commit()
    r = await client.post(
        "/api/v1/alert-rules",
        json={"market": "us", "indicator": "rsi_14", "operator": "gt", "threshold": 70},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 400
    assert "需要 symbol" in r.json()["detail"]


@pytest.mark.asyncio
async def test_create_market_level_no_symbol_ok(client: AsyncClient, db_session: AsyncSession):
    """市场级指标(恐贪)无需 symbol · 传了也被忽略为 None。"""
    user = await make_user(db_session)
    await db_session.commit()
    r = await client.post(
        "/api/v1/alert-rules",
        json={"market": "crypto", "symbol": "ignored", "indicator": "fear_greed", "operator": "lt", "threshold": 20},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 201
    assert r.json()["symbol"] is None


@pytest.mark.asyncio
async def test_create_respects_cap(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("app.api.v1.alert_rules.MAX_RULES_PER_USER", 1)
    user = await make_user(db_session)
    await db_session.commit()
    headers = await _auth(user, db_session)
    body = {"market": "us", "symbol": "NVDA", "indicator": "price", "operator": "gt", "threshold": 100, "timeframe": "1d"}
    r1 = await client.post("/api/v1/alert-rules", json=body, headers=headers)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/alert-rules", json=body, headers=headers)
    assert r2.status_code == 400
    assert "上限" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_patch_rule(client: AsyncClient, db_session: AsyncSession):
    user = await make_user(db_session)
    rule = AlertRule(
        user_id=user.id, market="us", symbol="NVDA", indicator="rsi_14",
        operator="gt", threshold=70, timeframe="1d",
    )
    db_session.add(rule)
    await db_session.commit()
    r = await client.patch(
        f"/api/v1/alert-rules/{rule.id}",
        json={"enabled": False, "threshold": 80},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert float(r.json()["threshold"]) == 80.0


@pytest.mark.asyncio
async def test_delete_own_and_cross_user(client: AsyncClient, db_session: AsyncSession):
    owner = await make_user(db_session)
    other = await make_user(db_session)
    rule = AlertRule(
        user_id=owner.id, market="crypto", symbol="BTC/USDT", indicator="funding_rate",
        operator="gt", threshold=0.01,
    )
    db_session.add(rule)
    await db_session.commit()

    # 别人删不了(404)
    r_cross = await client.delete(
        f"/api/v1/alert-rules/{rule.id}", headers=await _auth(other, db_session),
    )
    assert r_cross.status_code == 404
    still = await db_session.scalar(select(AlertRule).where(AlertRule.id == rule.id))
    assert still is not None

    # 本人删得掉(204)
    r_own = await client.delete(
        f"/api/v1/alert-rules/{rule.id}", headers=await _auth(owner, db_session),
    )
    assert r_own.status_code == 204


@pytest.mark.asyncio
async def test_apply_recommended_creates_then_idempotent(
    client: AsyncClient, db_session: AsyncSession,
):
    """一键应用推荐 → 建 9 条;再次调用全跳过(幂等)· user_id 取自登录用户。"""
    user = await make_user(db_session)
    await db_session.commit()
    headers = await _auth(user, db_session)

    r1 = await client.post("/api/v1/alert-rules/apply-recommended", headers=headers)
    assert r1.status_code == 200
    assert r1.json() == {"created": 9, "skipped": 0}

    # 列表确有 9 条
    listed = await client.get("/api/v1/alert-rules", headers=headers)
    assert len(listed.json()) == 9

    # 再次 → 全部已存在 → 跳过(不重复建)
    r2 = await client.post("/api/v1/alert-rules/apply-recommended", headers=headers)
    assert r2.json() == {"created": 0, "skipped": 9}
    listed2 = await client.get("/api/v1/alert-rules", headers=headers)
    assert len(listed2.json()) == 9
