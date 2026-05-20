"""通知 client pytest · 飞书 + Telegram(httpx MockTransport)。"""

from __future__ import annotations

import pytest
import httpx

from app.services.notifications import feishu, telegram


# ===== 飞书 =====


@pytest.mark.asyncio
async def test_feishu_send_success():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.read()
        return httpx.Response(200, json={"StatusCode": 0, "StatusMessage": "ok"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        body = await feishu.send(
            "https://open.feishu.cn/webhook/abc",
            {"msg_type": "interactive", "card": {}},
            client=client,
        )
    assert body["StatusCode"] == 0
    assert captured["url"] == "https://open.feishu.cn/webhook/abc"


@pytest.mark.asyncio
async def test_feishu_keyword_missing_raises_with_business_code():
    """飞书关键词不匹配:200 OK 但 StatusCode=19021。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"StatusCode": 19021, "StatusMessage": "Key Words Not Found"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(feishu.FeishuApiError) as exc:
            await feishu.send(
                "https://open.feishu.cn/webhook/abc",
                {"msg_type": "interactive"},
                client=client,
            )
    assert exc.value.status == 19021
    assert "Key Words Not Found" in exc.value.detail


@pytest.mark.asyncio
async def test_feishu_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("DNS resolution failed")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(feishu.FeishuApiError) as exc:
            await feishu.send(
                "https://invalid.example/webhook",
                {"msg_type": "interactive"},
                client=client,
            )
    assert exc.value.status == 0
    assert "网络错误" in exc.value.detail


# ===== Telegram =====


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
    import json
    assert body["ok"] is True
    assert "12345:fake" in captured["url"]
    body_json = json.loads(captured["body"])
    assert body_json["chat_id"] == "67890"
    assert body_json["text"] == "*test*"


@pytest.mark.asyncio
async def test_telegram_invalid_token_raises():
    """token 不对 · TG 返 401 + ok=false。"""

    def handler(request: httpx.Request) -> httpx.Response:
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
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(telegram.TelegramApiError) as exc:
            await telegram.send("t", "c", "msg", client=client)
    assert exc.value.status == 0
