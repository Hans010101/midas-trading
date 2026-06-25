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
    reply_markup: dict[str, Any] | None = None,
    disable_preview: bool = False,
    timeout: float = 5.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """POST text 到 TG Bot API · 失败抛 TelegramApiError。

    reply_markup 传入 inline_keyboard(G3 按钮界面)· None = 纯文本(G1/G2 行为不变)。
    disable_preview=True → 关底部网页预览大卡(★只抑制预览卡 · 正文 [text](url) 内联链接仍可点);
    默认 False = TG 原生预览行为不变(成交/价格/告警/周报等其他推送不受影响)。
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if disable_preview:
        payload["disable_web_page_preview"] = True
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

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


# ── G3 · 按钮回调 / 原地编辑(共用 POST helper)──────────────────────────


async def _post_json(
    bot_token: str,
    method: str,
    payload: dict[str, Any],
    *,
    timeout: float,
    client: httpx.AsyncClient | None,
) -> dict[str, Any]:
    """通用 Bot API POST · 失败抛 TelegramApiError(G3 新方法共用)。"""
    url = f"https://api.telegram.org/bot{bot_token}/{method}"
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


async def send_photo(
    bot_token: str,
    chat_id: str,
    photo_url: str,
    *,
    caption: str | None = None,
    parse_mode: str = "Markdown",
    reply_markup: dict[str, Any] | None = None,
    timeout: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """sendPhoto(photo=URL · TG 服务端拉取渲图)· KLINE-001 K线图截图。失败抛 TelegramApiError。

    photo 用 URL(JSON · 无需 multipart)· URL 404/不可达 → TG 返 ok=false → _post_json 抛错
    → 调用方(_send_photo_safe)回退发文本网页链接。caption 支持 Markdown · reply_markup 保留按钮。
    timeout 比纯文本长(TG 要拉图渲染)。
    """
    payload: dict[str, Any] = {"chat_id": chat_id, "photo": photo_url}
    if caption is not None:
        payload["caption"] = caption
        payload["parse_mode"] = parse_mode
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return await _post_json(
        bot_token, "sendPhoto", payload, timeout=timeout, client=client,
    )


async def answer_callback_query(
    bot_token: str,
    callback_query_id: str,
    *,
    text: str | None = None,
    timeout: float = 5.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """回应 callback_query · 消除按钮 loading 态。可选轻量 toast text。"""
    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text is not None:
        payload["text"] = text
    return await _post_json(
        bot_token, "answerCallbackQuery", payload, timeout=timeout, client=client,
    )


async def edit_message_text(
    bot_token: str,
    chat_id: str,
    message_id: int,
    text: str,
    *,
    parse_mode: str = "Markdown",
    reply_markup: dict[str, Any] | None = None,
    timeout: float = 5.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """原地编辑已发消息(菜单/查询结果刷新 · 比连发新消息干净)。"""
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return await _post_json(
        bot_token, "editMessageText", payload, timeout=timeout, client=client,
    )


async def set_my_commands(
    bot_token: str,
    commands: list[dict[str, str]],
    *,
    timeout: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """setMyCommands · 设置 bot 命令菜单(G5 DP-G5-5 · 启动期随代码同步)。

    commands = [{"command": "menu", "description": "功能菜单"}, ...]。幂等。
    """
    return await _post_json(
        bot_token, "setMyCommands", {"commands": commands},
        timeout=timeout, client=client,
    )


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
        # message(/start 绑定 + 命令)+ callback_query(G3 inline 按钮回调)· 其余降噪
        "allowed_updates": ["message", "callback_query"],
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
