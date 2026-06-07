"""回测结果落库(P1-4c 块3)· backtest_runs 表读写 · async · 调用方负责 commit。

🔴 红线:纯研究记录 · 绝不碰下单 / 撮合 / 余额 · 不 import vibe。
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
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
    """回填成功结果(status=done + 16 指标 + equity/trades/run_card + run_id)· 调用方 commit。"""
    run.status = "done"
    run.metrics_json = dict(result["metrics"])
    # P1-4c.5 full-data:equity/trades/run_card 一并落 PG(此前被丢 · B 档报告 UI 用)。
    #   EquityPoint/Trade 是 TypedDict(运行时即 dict)· dict() 转成可入 JSONB 的 list[dict]。
    run.equity_json = [dict(point) for point in result["equity"]]
    run.trades_json = [dict(trade) for trade in result["trades"]]
    run.run_card_json = result["run_card"]
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


async def sweep_stale_pending(session: AsyncSession, *, older_than_minutes: int) -> int:
    """超时兜底:把超过 older_than_minutes 仍 pending 的回测行标 error · 返回标记数 · 调用方 commit。

    防 vibe-worker 抖动/OOM/丢任务导致 pending 永远转圈(P1-4b-2 三层超时的最后一层)。
    created_at 是 tz-aware(server_default now())· 与 aware UTC cutoff 比较。
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
    stmt = select(BacktestRun).where(
        BacktestRun.status == "pending",
        BacktestRun.created_at < cutoff,
    )
    rows = list((await session.execute(stmt)).scalars().all())
    for run in rows:
        run.status = "error"
        run.error = f"timeout: 超过 {older_than_minutes} 分钟未返回结果(vibe-worker 兜底扫描)"
    await session.flush()
    return len(rows)
