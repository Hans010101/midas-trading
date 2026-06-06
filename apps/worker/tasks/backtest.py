"""研究室回测 Celery 编排(P1-4b-1 · 方案戊)· 主 worker 侧:落库 + 触发 vibe-worker + 收结果。

链路:
  run_backtest(主 worker · celery 队列)
    → 落 pending 行 + send_task("vibe.run_backtest_job", queue="backtest",
        link=persist_outcome@queue="celery")
  → vibe-worker(midas-vibe 容器 · backtest 队列)跑 run_one → 写 artifacts 到共享卷 →
     经 Celery result 返回 {status,run_id,run_dir,artifacts_dir,metrics?/error?}
  → persist_outcome(主 worker · celery 队列)读共享卷 artifacts → persist_result/error → 清 run_dir。

🔴 红线:纯研究 · 绝不连 place_market_order / 虚拟下单引擎 · 只读 CH ·
  ★主 worker 不 import vibe(用 send_task by name)· 主 worker 不订阅 backtest 队列(无 -Q)。
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Any
from uuid import UUID

from celery import current_app, shared_task, signature
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.backtest_run import BacktestRun
from app.services.backtest.persistence import (
    create_pending_run,
    persist_error,
    persist_result,
)
from app.services.backtest.service import build_backtest_config, parse_artifacts
from app.services.backtest.types import BacktestParams

logger = logging.getLogger(__name__)

# 共享卷挂载点(midas-vibe 写 / 主 worker 读 · compose 里 backtest_runs:/work/runs)。
_SHARED_RUNS_ROOT = "/work/runs"

# vibe-worker 任务名(★ 与 deploy/vibe/vibe_celery_app.py @app.task(name=...) 逐字一致 · 易踩坑2)
_VIBE_TASK = "vibe.run_backtest_job"


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


async def _persist(vibe_result: dict[str, Any], run_pk: int) -> None:
    """读 vibe 返回 + 共享卷 artifacts → persist_result/error · 落库后清 run_dir。"""
    engine = create_async_engine(settings.database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            run = await session.get(BacktestRun, run_pk)
            if run is None:
                logger.error("[backtest] persist_outcome:找不到 run %s,丢弃", run_pk)
                return
            run_id = vibe_result.get("run_id")
            if vibe_result.get("status") == "ok":
                params = BacktestParams(**run.params_json)  # 从 pending 行重建入参
                result = parse_artifacts(Path(vibe_result["run_dir"]), params)
                await persist_result(session, run, result, run_id=run_id)
            else:
                err = str(vibe_result.get("error", "unknown"))
                await persist_error(session, run, err, run_id=run_id)
            await session.commit()
    finally:
        await engine.dispose()
    # 落库后清共享卷 run_dir(防堆积 · 16 指标已进 PG)。
    # TODO(P1-4b-2 加固):若 B 档报告 UI 需 equity/trades 曲线,改为持久化进 PG 后再清,
    #   或保留 run_dir + beat 定期清 N 天前目录(本步先落库即删,卷只做中转)。
    run_dir = vibe_result.get("run_dir")
    if run_dir:
        shutil.rmtree(run_dir, ignore_errors=True)


@shared_task(
    bind=True,
    name="tasks.backtest.run_backtest",
    max_retries=0,
)
def run_backtest(self: Any, params: dict[str, Any], user_id: str | None = None) -> dict[str, Any]:  # noqa: ARG001
    """触发一次研究室回测:落 pending → enqueue 到 backtest 队列(vibe-worker 消费)。

    Args:
        params: BacktestParams 的字段 dict(symbol/start/end/market/period/sma_fast/sma_slow/...)。
        user_id: 触发者 UUID 字符串(可空 · 匿名研究跑)。

    Returns:
        契约 dict:{backtest_run_id, status:"pending"}(异步 · 结果由 persist_outcome 回填)。
    """
    bt_params = BacktestParams(**params)
    # 早校验:period 不支持等 → ValueError(在落库前就暴露,不写脏 pending 行)
    config = build_backtest_config(bt_params)
    uid = UUID(user_id) if user_id else None

    run_pk = asyncio.run(_create_pending(bt_params, uid))

    # 共享卷 run_dir(vibe + 主 worker 同挂 /work/runs)· vibe job 用 config["run_dir"]
    config["run_id"] = str(run_pk)
    config["run_dir"] = f"{_SHARED_RUNS_ROOT}/{run_pk}"

    # enqueue 到 backtest 队列(by name · 主 worker 不 import vibe)。
    # ★ link 必须显式 queue="celery"(易踩坑1):否则被 vibe app 的 task_default_queue=backtest
    #   吞进 backtest 队列 → vibe-worker 自己收(它没 app./没 persist 任务)→ 主 worker 永远收不到。
    current_app.send_task(
        _VIBE_TASK,
        args=[config],
        queue="backtest",
        link=signature("tasks.backtest.persist_outcome", args=[run_pk], queue="celery"),
    )

    # TODO(P1-4b-2 加固 · 超时兜底):vibe-worker 若卡死/丢任务,pending 行会永远悬着。
    #   落点:① persist_outcome 加 soft_time_limit;② 一个 beat 任务扫 created_at 超 N 分钟仍
    #   pending 的行 → 标 error/timeout。本步先留 TODO,不写复杂逻辑。
    logger.info("[backtest] run %s 落 pending + enqueue 到 backtest 队列", run_pk)
    return {"backtest_run_id": run_pk, "status": "pending"}


@shared_task(
    name="tasks.backtest.persist_outcome",
    max_retries=0,
)
def persist_outcome(vibe_result: dict[str, Any], run_pk: int) -> dict[str, Any]:
    """vibe-worker 成功后的回调(主 worker · celery 队列)· 读 artifacts 落库 + 清卷。

    Args:
        vibe_result: vibe.run_backtest_job 返回 {status,run_id,run_dir,artifacts_dir,metrics?/error?}。
        run_pk: 对应 backtest_runs.id(send_task link 里 partial 传入)。
    """
    asyncio.run(_persist(vibe_result, run_pk))
    return {"backtest_run_id": run_pk, "persisted": vibe_result.get("status")}
