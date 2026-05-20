"""emit_trade_filled pytest · 验证非阻塞 + broker 失败不抛 · 0009 § 3。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.notifications import emit


@pytest.mark.asyncio
async def test_emit_trade_filled_calls_celery_send_task():
    """正常情况:emit 调用 celery client.send_task。"""

    # Reset singleton so we get a fresh mock
    emit._celery_client = None  # noqa: SLF001

    with patch.object(emit, "_get_celery_client") as mock_client_getter:
        mock_client = mock_client_getter.return_value
        emit.emit_trade_filled(42)
        mock_client.send_task.assert_called_once_with(
            "tasks.notifications.send_trade_notification",
            args=[42],
        )


@pytest.mark.asyncio
async def test_emit_trade_filled_broker_down_does_not_raise():
    """broker 挂了 · emit 不抛 · 主链路不受影响(0009 § 3 关键铁律)。"""

    emit._celery_client = None  # noqa: SLF001

    def boom() -> None:
        raise ConnectionError("broker unreachable")

    with patch.object(emit, "_get_celery_client", side_effect=boom):
        # 关键:这里不抛异常
        emit.emit_trade_filled(99)
