"""通知 client pytest · Telegram(httpx MockTransport)· 0025 G2a 飞书已移除。"""

from __future__ import annotations

import json

import httpx
import pytest

from app.services.notifications import telegram


@pytest.mark.asyncio
async def test_telegram_send_success():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.read().decode()
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        body = await telegram.send(
            "12345:fake", "67890",
            "*test*",
            client=client,
        )
    assert body["ok"] is True
    assert "12345:fake" in captured["url"]
    body_json = json.loads(captured["body"])
    assert body_json["chat_id"] == "67890"
    assert body_json["text"] == "*test*"


@pytest.mark.asyncio
async def test_telegram_invalid_token_raises():
    """token 不对 · TG 返 401 + ok=false。"""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"ok": False, "error_code": 401, "description": "Unauthorized"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(telegram.TelegramApiError) as exc:
            await telegram.send("bad", "0", "test", client=client)
    assert "Unauthorized" in exc.value.detail


@pytest.mark.asyncio
async def test_telegram_network_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(telegram.TelegramApiError) as exc:
            await telegram.send("t", "c", "msg", client=client)
    assert exc.value.status == 0
