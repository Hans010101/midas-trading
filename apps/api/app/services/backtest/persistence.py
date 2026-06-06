"""回测结果落库(P1-4c 块3)· backtest_runs 表读写 · async · 调用方负责 commit。

🔴 红线:纯研究记录 · 绝不碰下单 / 撮合 / 余额 · 不 import vibe。
"""
from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backtest_run import BacktestRun
from app.services.backtest.types import BacktestParams, BacktestResult


async def create_pending_run(
    session: AsyncSession,
    params: BacktestParams,
    *,
    user_id: UUID | None = None,
) -> BacktestRun:
    """落一行 pending 回测记录(尚未执行)· flush 拿 id · 调用方 commit。"""
    run = BacktestRun(
        user_id=user_id,
        symbol=params.symbol,
        market=params.market,
        period=params.period,
        start_date=params.start,
        end_date=params.end,
        params_json=asdict(params),
        status="pending",
    )
    session.add(run)
    await session.flush()  # 拿自增 id(不 commit)
    return run


async def persist_result(
    session: AsyncSession,
    run: BacktestRun,
    result: BacktestResult,
    *,
    run_id: str | None = None,
) -> None:
    """回填成功结果(status=done + 16 指标 metrics_json + run_id)· 调用方 commit。"""
    run.status = "done"
    run.metrics_json = dict(result["metrics"])
    if run_id is not None:
        run.run_id = run_id
    await session.flush()


async def persist_error(
    session: AsyncSession,
    run: BacktestRun,
    error: str,
    *,
    run_id: str | None = None,
) -> None:
    """回填失败(status=error + error 文本)· 调用方 commit。"""
    run.status = "error"
    run.error = error
    if run_id is not None:
        run.run_id = run_id
    await session.flush()
