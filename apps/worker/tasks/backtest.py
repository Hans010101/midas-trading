"""研究室回测 Celery task(P1-4c 块3 骨架)· 触发 midas-vibe 容器执行 + 落库。

★ 容器编排(怎么调 midas-vibe 跑 deploy/vibe/run_backtest_job.py)= P1-4b(compose
  就绪)才定。本骨架只做:① 入参 → BacktestParams ② 早校验 config(period 等)
  ③ 落一行 pending(backtest_runs)④ 返回入参出参契约。容器调用 + 落 done/error 留
  清晰 TODO(parse_artifacts / persist_result / persist_error 已在 app.services.backtest
  写好,P1-4b 直接接)。

🔴 红线:纯研究 · 绝不连 place_market_order / 虚拟下单引擎 · loader 只读 CH ·
  不 import vibe(api/worker 层零 vibe 依赖;vibe 只在 midas-vibe 容器内)。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from celery import shared_task
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.services.backtest.persistence import create_pending_run
from app.services.backtest.service import build_backtest_config
from app.services.backtest.types import BacktestParams

logger = logging.getLogger(__name__)


async def _create_pending(params: BacktestParams, user_id: UUID | None) -> int:
    """落 pending 行,返回自增 id(独立 engine · 用完 dispose)。"""
    engine = create_async_engine(settings.database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            run = await create_pending_run(session, params, user_id=user_id)
            await session.commit()
            return run.id
    finally:
        await engine.dispose()


@shared_task(
    bind=True,
    name="tasks.backtest.run_backtest",
    max_retries=0,
)
def run_backtest(self: Any, params: dict[str, Any], user_id: str | None = None) -> dict[str, Any]:  # noqa: ARG001
    """触发一次研究室回测(骨架)。

    Args:
        params: BacktestParams 的字段 dict(symbol/start/end/market/period/sma_fast/sma_slow/...)。
        user_id: 触发者 UUID 字符串(可空 · 匿名研究跑)。

    Returns:
        契约 dict:{backtest_run_id, status, config, note}。
    """
    bt_params = BacktestParams(**params)
    # 早校验:period 不支持等 → ValueError(在落库前就暴露,不写脏 pending 行)
    config = build_backtest_config(bt_params)
    uid = UUID(user_id) if user_id else None

    run_pk = asyncio.run(_create_pending(bt_params, uid))

    # ── TODO(P1-4b · 容器编排,等 compose 就绪)──────────────────────────────
    #   1. config["run_dir"]/["run_id"] 指向共享卷,把 config 交给 midas-vibe 容器跑
    #      deploy/vibe/run_backtest_job.py(docker run --network midas-net 挂 loader+job,
    #      或 compose run 一次性 job;具体编排 P1-4b 和 compose 一起定)。
    #   2. 容器写 artifacts → app.services.backtest.parse_artifacts(run_dir, bt_params) → result。
    #   3. 落 done:app.services.backtest.persistence.persist_result(session, run, result, run_id)
    #      失败:persist_error(session, run, error, run_id)。
    # ────────────────────────────────────────────────────────────────────────
    logger.info("[backtest] pending run %s 已落库;容器执行 = P1-4b TODO", run_pk)
    return {
        "backtest_run_id": run_pk,
        "status": "pending",
        "config": config,
        "note": "容器执行 + 落 done/error = P1-4b TODO(compose 就绪后接)",
    }
