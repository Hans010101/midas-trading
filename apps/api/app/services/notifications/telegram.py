"""Telegram bot client · 0009 § 2.2。

Bot API · POST https://api.telegram.org/bot{token}/sendMessage
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

logger = logging.getLogger(__name__)


class TelegramApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"Telegram {status}: {detail}")
        self.status = status
        self.detail = detail


async def send(
    bot_token: str,
    chat_id: str,
    text: str,
    *,
    parse_mode: str = "Markdown",
    timeout: float = 5.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """POST text 到 TG Bot API · 失败抛 TelegramApiError。"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }

    owned = client is None
    if owned:
        client = httpx.AsyncClient(timeout=timeout)
    assert client is not None

    try:
        resp = await client.post(url, json=payload)
    except httpx.HTTPError as e:
        msg = f"网络错误:{e}"
        raise TelegramApiError(0, msg) from e
    finally:
        if owned:
            await client.aclose()

    try:
        body = resp.json()
    except ValueError as e:
        raise TelegramApiError(resp.status_code, "响应不是有效 JSON") from e

    if resp.status_code != 200 or not body.get("ok"):
        detail = body.get("description") or f"HTTP {resp.status_code}"
        raise TelegramApiError(resp.status_code, str(detail))

    return cast(dict[str, Any], body)


async def set_webhook(
    bot_token: str,
    webhook_url: str,
    secret_token: str,
    *,
    timeout: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """注册 Telegram webhook(0024 v2 · 统一 bot)。

    Telegram 之后会把 update POST 到 webhook_url,并在请求头带
    `X-Telegram-Bot-Api-Secret-Token: {secret_token}` 供我们校验真伪。
    幂等:重复调用同 URL 无副作用。失败抛 TelegramApiError。
    """
    url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    payload = {
        "url": webhook_url,
        "secret_token": secret_token,
        "allowed_updates": ["message"],  # 只要 message(/start 绑定)· 降噪
    }

    owned = client is None
    if owned:
        client = httpx.AsyncClient(timeout=timeout)
    assert client is not None  # noqa: S101

    try:
        resp = await client.post(url, json=payload)
    except httpx.HTTPError as e:
        raise TelegramApiError(0, f"网络错误:{e}") from e
    finally:
        if owned:
            await client.aclose()

    try:
        body = resp.json()
    except ValueError as e:
        raise TelegramApiError(resp.status_code, "响应不是有效 JSON") from e

    if resp.status_code != 200 or not body.get("ok"):
        detail = body.get("description") or f"HTTP {resp.status_code}"
        raise TelegramApiError(resp.status_code, str(detail))

    return cast(dict[str, Any], body)
