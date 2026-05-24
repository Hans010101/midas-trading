"""Celery worker 入口。"""

import logging

from celery import Celery
from celery.signals import worker_ready

app = Celery("midas-worker")
app.config_from_object("config.celery_config")

# 显式 import task 模块,触发 @shared_task 注册到 broker。
# 不用 autodiscover_tasks(那是为 Django-style "<app>/tasks.py" 设计的,
# 我们的布局 `tasks/<feature>.py` 用不上)。
# 在模块加载期(celery 解析 -A celery_app 时 CWD 在 sys.path 上)就 import,
# 缓存进 sys.modules。worker_ready 信号晚于此触发,届时 CWD 可能已不在 sys.path —
# 若把 import 放进 handler 里会 ModuleNotFoundError(实测踩过)。
from ch_schema import ensure_crypto_ch_tables  # noqa: E402
from tasks import (  # noqa: E402, F401
    crypto_metrics_ingest,
    data_ingest,
    equity_snapshot,
    incremental,
    market_home_ingest,
    notifications,
    perp_funding,
    perp_liquidation,
    price_alerts,
)

logger = logging.getLogger(__name__)


@worker_ready.connect
def _ensure_ch_tables(**_kwargs: object) -> None:
    """worker 起来后幂等建 ClickHouse 表(update.sh 无 CH 建表步骤 · M2-C.2.1)。"""
    ensure_crypto_ch_tables()
