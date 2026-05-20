"""Celery worker 入口。"""

from celery import Celery

app = Celery("midas-worker")
app.config_from_object("config.celery_config")

# 显式 import task 模块,触发 @shared_task 注册到 broker。
# 不用 autodiscover_tasks(那是为 Django-style "<app>/tasks.py" 设计的,
# 我们的布局 `tasks/<feature>.py` 用不上)。
from tasks import (  # noqa: E402, F401
    data_ingest,
    equity_snapshot,
    incremental,
    notifications,
    price_alerts,
)
