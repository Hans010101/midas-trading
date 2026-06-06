"""vibe-worker 的独立最小 Celery app(P1-4b · 仅 midas-vibe 容器内运行)。

★ 只注册 backtest 任务,broker/backend = 同一套 Redis(与主 worker 共用)。
★ 不 import app.* / 不连 DB / 不拿 DB 凭证 —— vibe-worker 只算不落库(解耦)。
★ 任务里走路径B(CryptoEngine + 运行时挂载的 MidasCHLoader),不碰 registry/下单引擎。

启动(compose 里):celery -A vibe_celery_app worker -Q backtest --concurrency=1 -n vibe@%h
"""
from __future__ import annotations

import os

from celery import Celery

# broker/backend env 名对齐主 worker(apps/worker/config/celery_config.py)。
_BROKER = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")
_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/2")

app = Celery("midas-vibe", broker=_BROKER, backend=_BACKEND)

# 本 app 自身发起的任务默认进 backtest 队列;但跨 app 回调(persist_outcome)
# 必须由【主 worker 侧】在 send_task 的 link 上显式 queue="celery"(见 tasks/backtest.py),
# 否则会被这里的默认队列吞进 backtest → 主 worker 收不到。
app.conf.task_default_queue = "backtest"
app.conf.task_acks_late = True  # 任务执行完才 ack(worker 崩则重投 · b-2 再配合超时/幂等加固)


@app.task(name="vibe.run_backtest_job")
def run_backtest_job_task(config: dict) -> dict:
    """消费 backtest 队列 · 跑一次回测 · 返回 {status,run_id,run_dir,artifacts_dir,metrics?/error?}。

    ★ 任务名 "vibe.run_backtest_job" 必须与主 worker send_task by name 逐字一致(易踩坑2)。
    复用 run_backtest_job.run_one(同 /work 目录挂载)· run_one 永不 raise(顶层兜底转 error dict)。
    """
    from run_backtest_job import run_one

    return run_one(config)
