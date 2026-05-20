"""非阻塞事件 emit · 0009 § 3。

emit_trade_filled 在 engine._record_filled 末尾调用 · 走 Celery broker
异步派发任务给 worker · broker 失败仅 log · 主链路继续。
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


_celery_client: Any | None = None


def _get_celery_client() -> Any:
    """Lazy 创建 Celery 客户端 · 用于 send_task。

    不引入完整 worker 配置 · 仅作为 broker 发任务的轻量客户端。
    """
    global _celery_client
    if _celery_client is None:
        from celery import Celery  # noqa: PLC0415

        broker = os.environ.get(
            "CELERY_BROKER_URL", "redis://localhost:6379/1",
        )
        _celery_client = Celery("midas-api", broker=broker)
    return _celery_client


def emit_trade_filled(order_id: int) -> None:
    """非阻塞 emit · 失败仅 log · 主链路不抛异常。

    走 Celery broker · 网络 IO ~5ms · 不算阻塞响应。
    broker 挂了不算异常情况 · 用户已经看到下单成功了。
    """
    try:
        client = _get_celery_client()
        client.send_task(
            "tasks.notifications.send_trade_notification",
            args=[order_id],
        )
        logger.debug("[emit] trade filled order_id=%s", order_id)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[emit] trade filled FAILED order_id=%s err=%s",
            order_id, e,
        )
