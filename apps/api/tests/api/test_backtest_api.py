"""P1-4c.5 研究室回测读端点 pytest · GET 列表 + GET /{id}(authed-only · 按 user 过滤)。

覆盖:列表只返回本人的 + 倒序;取自己的 run → 200 full-data;取他人的 → 404(越权防护);
未登录 → 401。POST 发起端点待 orchestration 拍板后补(连同其单测)。
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backtest_run import BacktestRun
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
async def test_create_enqueues_and_returns_pending_single_row(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # mock enqueue:不真打 broker · 记录调用参数
    calls: list[tuple[dict[str, object], str, int]] = []

    def _fake_enqueue(params: dict[str, object], user_id: str, backtest_run_id: int) -> None:
        calls.append((params, user_id, backtest_run_id))

    monkeypatch.setattr("app.api.v1.backtest.enqueue_run_backtest", _fake_enqueue)

    alice = await make_user(db_session)
    resp = await client.post(
        "/api/v1/backtest",
        json={"symbol": "BTC/USDT", "start": "2025-01-01", "end": "2025-02-01"},
        headers=await _auth(alice, db_session),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert isinstance(body["id"], int)

    # enqueue 恰好调一次,run_id == 返回 id,user_id == alice,params 透传 symbol
    assert len(calls) == 1
    sent_params, sent_uid, sent_run_id = calls[0]
    assert sent_run_id == body["id"]
    assert sent_uid == str(alice.id)
    assert sent_params["symbol"] == "BTC/USDT"

    # ★ 关键:DB 里只有 1 条 pending 行(不是双行 · Option A 复用 id 的核心)· 归属 alice
    count = (
        await db_session.execute(
            select(func.count()).select_from(BacktestRun).where(BacktestRun.user_id == alice.id),
        )
    ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_create_rejects_bad_period(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    # period Literal 不含 3d → Pydantic 422(在 handler 前短路 · enqueue 不会被调,无需 mock)
    alice = await make_user(db_session)
    resp = await client.post(
        "/api/v1/backtest",
        json={"symbol": "BTC/USDT", "start": "2025-01-01", "end": "2025-02-01", "period": "3d"},
        headers=await _auth(alice, db_session),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_unauthenticated_rejected(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/backtest")).status_code == 401
    assert (await client.get("/api/v1/backtest/1")).status_code == 401
    post = await client.post(
        "/api/v1/backtest",
        json={"symbol": "BTC/USDT", "start": "2025-01-01", "end": "2025-02-01"},
    )
    assert post.status_code == 401
