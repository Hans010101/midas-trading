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
        # #296:debug → info,生产 worker 跑 --loglevel=info,方便排查"发没发"
        logger.info("[emit] trade filled order_id=%s", order_id)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[emit] trade filled FAILED order_id=%s err=%s",
            order_id, e,
        )


def emit_perp_order(order_id: int) -> None:
    """非阻塞 emit · 永续成交 + 逐仓强平(virtual_perp_order)· #296。

    只在调用方 commit 之后调用(commit 后 emit · 避免"通知发了但事务回滚")。
    走 Celery broker · 失败仅 log · 绝不抛(broker 挂不影响交易/强平主流程)。
    """
    try:
        client = _get_celery_client()
        client.send_task(
            "tasks.notifications.send_perp_order_notification",
            args=[order_id],
        )
        logger.info("[emit] perp order order_id=%s", order_id)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[emit] perp order FAILED order_id=%s err=%s",
            order_id, e,
        )


def emit_cross_liquidation(
    account_id: int,
    liquidated_count: int,
    floored: bool,
    remaining_cash: object,
) -> None:
    """非阻塞 emit · 全仓账户级强平(一次性全平 N 仓 · 汇总一条)· #296。

    只在 worker commit 之后调用。remaining_cash 传 Decimal/str 均可(内部 str 化过 JSON)。
    失败仅 log · 绝不抛。
    """
    try:
        client = _get_celery_client()
        client.send_task(
            "tasks.notifications.send_cross_liquidation_notification",
            args=[account_id, liquidated_count, floored, str(remaining_cash)],
        )
        logger.info(
            "[emit] cross liquidation account_id=%s count=%s",
            account_id, liquidated_count,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[emit] cross liquidation FAILED account_id=%s err=%s",
            account_id, e,
        )
