"""x-shooter 独立最小 Celery app(阶段4a · PR-4 · 仅 midas-xshot 容器内运行)。

★ 只注册 xshot.capture 任务,broker/backend = 同一套 Redis(与主 worker 共用)。
★ 不 import app.* / 不连 DB —— shooter 只截图写 /shots/<id>.png,image_path 落库
  由【主 worker 侧】link 回调(tasks.x_tweets.set_image_path)做(解耦,照搬 vibe 范式)。

启动(compose 里):celery -A xshot_celery_app worker -Q xshot --concurrency=1 -n xshot@%h
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from celery import Celery

# ★ celery worker 进程的 sys.path 不保证含 /work → 显式自定位本文件目录,保证 task 内
#   `from capture import capture_one` 找得到同目录模块(对齐 vibe_celery_app 的同款修法)。
sys.path.insert(0, str(Path(__file__).resolve().parent))

# broker/backend env 名对齐主 worker(apps/worker/config/celery_config.py)。
_BROKER = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")
_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/2")

app = Celery("midas-xshot", broker=_BROKER, backend=_BACKEND)

# 本 app 自身默认进 xshot 队列;但跨 app 回调(set_image_path)必须由【主 worker 侧】在
# send_task 的 link 上显式 queue="celery"(见 tasks/x_tweets.py),否则被这里的默认队列吞掉。
app.conf.task_default_queue = "xshot"
app.conf.task_acks_late = True  # 截完才 ack(worker 崩则重投)

# 截图实测十几秒(开页+等渲染+截图)→ soft 90s 先抛(被 capture_one 兜底转 error dict),
# hard 120s 强杀兜底。配合主 worker 入队 expires(超时①)双层防卡。
_SOFT_TIME_LIMIT_S = 90
_HARD_TIME_LIMIT_S = 120


@app.task(name="xshot.capture", soft_time_limit=_SOFT_TIME_LIMIT_S, time_limit=_HARD_TIME_LIMIT_S)
def capture_task(tweet_id: int, symbol: str) -> dict:
    """消费 xshot 队列 · 截 crypto-preview 主图卡 · 返回 {tweet_id,status,path?/error?}。

    ★ 任务名 "xshot.capture" 须与主 worker send_task by name 逐字一致(易踩坑)。
    复用 capture.capture_one(同 /work 目录挂载)· capture_one 永不 raise(顶层兜底转 error dict)。
    """
    from capture import capture_one

    return capture_one(tweet_id, symbol)
