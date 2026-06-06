"""块3 落库单测 · backtest_runs 写读(需 PG · CI 跑 alembic upgrade head 后执行)。

验证:create_pending_run / persist_result / persist_error +(隐式)model↔迁移一致。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backtest_run import BacktestRun
from app.services.backtest.persistence import (
    create_pending_run,
    persist_error,
    persist_result,
    sweep_stale_pending,
)
from app.services.backtest.types import BacktestParams, BacktestResult


def _fixture_result() -> BacktestResult:
    return BacktestResult(
        params={},
        equity=[],
        trades=[],
        run_card={},
        metrics={
            "final_value": 1_100_000.0,
            "total_return": 0.1,
            "annual_return": 0.08,
            "max_drawdown": -0.05,
            "sharpe": 1.2,
            "calmar": 1.6,
            "sortino": 1.8,
            "win_rate": 0.55,
            "profit_loss_ratio": 1.3,
            "profit_factor": 1.4,
            "max_consecutive_loss": 3,
            "avg_holding_days": 4.5,
            "trade_count": 12,
            "benchmark_return": 0.06,
            "excess_return": 0.04,
            "information_ratio": 0.9,
        },
    )


async def test_create_pending_then_complete(db_session: AsyncSession) -> None:
    params = BacktestParams(
        symbol="BTC/USDT", start="2025-01-17", end="2026-05-31", sma_fast=5, sma_slow=20,
    )
    run = await create_pending_run(db_session, params)
    assert run.id is not None
    assert run.status == "pending"
    assert run.symbol == "BTC/USDT"
    assert run.params_json["sma_slow"] == 20
    assert run.metrics_json is None

    await persist_result(db_session, run, _fixture_result(), run_id="abc123")
    assert run.status == "done"
    assert run.run_id == "abc123"
    assert run.metrics_json is not None
    assert run.metrics_json["trade_count"] == 12

    # 读回(同 session · 同事务)证落库
    fetched = (
        await db_session.execute(select(BacktestRun).where(BacktestRun.id == run.id))
    ).scalar_one()
    assert fetched.status == "done"
    assert fetched.metrics_json is not None
    assert fetched.metrics_json["trade_count"] == 12


async def test_create_pending_then_error(db_session: AsyncSession) -> None:
    params = BacktestParams(symbol="ETHUSDT", start="2025-01-01", end="2025-02-01")
    run = await create_pending_run(db_session, params)
    await persist_error(db_session, run, "MidasCHLoader: 查无数据", run_id="x1")
    assert run.status == "error"
    assert run.error is not None
    assert "查无数据" in run.error


async def test_sweep_stale_pending_marks_only_old(db_session: AsyncSession) -> None:
    # 新鲜 pending(server now · 不该被扫)
    fresh = await create_pending_run(
        db_session, BacktestParams(symbol="BTCUSDT", start="2025-01-01", end="2025-02-01"),
    )
    # 陈旧 pending(手动 backdate created_at 到 1 小时前)
    stale = await create_pending_run(
        db_session, BacktestParams(symbol="ETHUSDT", start="2025-01-01", end="2025-02-01"),
    )
    stale.created_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.flush()

    swept = await sweep_stale_pending(db_session, older_than_minutes=10)
    assert swept == 1
    assert stale.status == "error"
    assert stale.error is not None
    assert "timeout" in stale.error
    assert fresh.status == "pending"  # 新鲜的不动
