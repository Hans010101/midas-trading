"""P1-4c.5 研究室回测读端点 pytest · GET 列表 + GET /{id}(authed-only · 按 user 过滤)。

覆盖:列表只返回本人的 + 倒序;取自己的 run → 200 full-data;取他人的 → 404(越权防护);
未登录 → 401。POST 发起端点待 orchestration 拍板后补(连同其单测)。
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.auth import issue_session
from app.services.backtest.persistence import create_pending_run, persist_result
from app.services.backtest.types import BacktestParams
from tests.factories import make_backtest_result, make_user


async def _auth(user: User, db: AsyncSession) -> dict[str, str]:
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_returns_only_own_runs_desc(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    alice = await make_user(db_session)
    bob = await make_user(db_session)
    p1 = BacktestParams(symbol="BTC/USDT", start="2025-01-01", end="2025-02-01")
    p2 = BacktestParams(symbol="ETH/USDT", start="2025-01-01", end="2025-02-01")
    r1 = await create_pending_run(db_session, p1, user_id=alice.id)
    r2 = await create_pending_run(db_session, p2, user_id=alice.id)
    await create_pending_run(db_session, p1, user_id=bob.id)  # bob 的 · 不该出现
    await db_session.commit()

    resp = await client.get("/api/v1/backtest", headers=await _auth(alice, db_session))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2  # 只 alice 的两条
    # created_at 倒序:后建的 r2 在前
    assert body[0]["id"] == r2.id
    assert body[1]["id"] == r1.id
    # 列表项精简:不带 equity/trades 重数据
    assert "equity_json" not in body[0]
    assert "trades_json" not in body[0]


@pytest.mark.asyncio
async def test_get_own_run_returns_full_data(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    alice = await make_user(db_session)
    params = BacktestParams(symbol="BTC/USDT", start="2025-01-17", end="2025-01-18")
    run = await create_pending_run(db_session, params, user_id=alice.id)
    await persist_result(db_session, run, make_backtest_result(params), run_id="7")
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/backtest/{run.id}", headers=await _auth(alice, db_session),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done"
    assert body["metrics_json"]["trade_count"] == 12
    assert len(body["equity_json"]) == 2
    assert body["trades_json"][0]["code"] == "BTCUSDT"
    assert body["run_card_json"]["data_sources"] == ["ccxt"]


@pytest.mark.asyncio
async def test_get_others_run_returns_404(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    alice = await make_user(db_session)
    bob = await make_user(db_session)
    params = BacktestParams(symbol="BTC/USDT", start="2025-01-01", end="2025-02-01")
    run = await create_pending_run(db_session, params, user_id=bob.id)  # bob 的
    await db_session.commit()

    # alice 取 bob 的 run → 越权 → 404(不是 403,不泄露存在性)
    resp = await client.get(
        f"/api/v1/backtest/{run.id}", headers=await _auth(alice, db_session),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_rejected(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/backtest")).status_code == 401
    assert (await client.get("/api/v1/backtest/1")).status_code == 401
