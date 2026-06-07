"""P1-4c.5 persist_result 扩写单测 · equity/trades/run_card 落 PG(CH-free / vibe-free)。

确认报告 C2:persist_result 此前只写 metrics_json,equity/trades/run_card 被丢。
本测试断言扩写后 4 个 json 字段都落库 + DB round-trip 读得回。
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backtest_run import BacktestRun
from app.services.backtest.persistence import create_pending_run, persist_result
from app.services.backtest.types import BacktestParams
from tests.factories import make_backtest_result, make_user


@pytest.mark.asyncio
async def test_persist_result_writes_full_data(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    params = BacktestParams(symbol="BTC/USDT", start="2025-01-17", end="2025-01-18")
    run = await create_pending_run(db_session, params, user_id=user.id)

    # pending 阶段:四个结果字段都还空
    assert run.status == "pending"
    assert run.metrics_json is None
    assert run.equity_json is None
    assert run.trades_json is None
    assert run.run_card_json is None

    await persist_result(db_session, run, make_backtest_result(params), run_id="42")

    assert run.status == "done"
    assert run.run_id == "42"
    # 16 指标(原有)
    assert run.metrics_json is not None
    assert run.metrics_json["trade_count"] == 12
    # equity 两点(新增)
    assert run.equity_json is not None
    assert len(run.equity_json) == 2
    assert run.equity_json[1]["equity"] == 1_010_000.0
    # trades 一笔(新增)
    assert run.trades_json is not None
    assert len(run.trades_json) == 1
    assert run.trades_json[0]["code"] == "BTCUSDT"
    # run_card(新增)
    assert run.run_card_json is not None
    assert run.run_card_json["data_sources"] == ["ccxt"]


@pytest.mark.asyncio
async def test_persist_result_round_trips_through_db(db_session: AsyncSession) -> None:
    """落库 + commit 后从 DB 重新读回 · 确认 JSONB 真写进了 PG(不只是 ORM 内存态)。"""
    user = await make_user(db_session)
    params = BacktestParams(symbol="ETH/USDT", start="2025-02-01", end="2025-02-10")
    run = await create_pending_run(db_session, params, user_id=user.id)
    await persist_result(db_session, run, make_backtest_result(params), run_id="7")
    await db_session.commit()

    fetched = await db_session.get(BacktestRun, run.id)
    assert fetched is not None
    assert fetched.equity_json is not None
    assert len(fetched.equity_json) == 2
    assert fetched.trades_json is not None
    assert fetched.trades_json[0]["side"] == "buy"
    assert fetched.run_card_json is not None
    assert fetched.run_card_json["data_sources"] == ["ccxt"]
