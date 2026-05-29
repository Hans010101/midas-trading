"""飞书通知 pytest · ADR 0032 阶段二:token 缓存 + 发送 + adapter + 双通道分发。

不打真实飞书 / Redis:token 缓存用 FakeRedis,HTTP 用 httpx.MockTransport,
dispatcher 双通道用 monkeypatch 记录 send_text(隔离真实 Redis/网络)。
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.notification import NotificationConfig
from app.services.notifications import feishu_client
from app.services.notifications.adapters import feishu as feishu_adapter
from app.services.notifications.dispatcher import dispatch, send_test
from app.services.notifications.events import TradeFilledEvent
from tests.factories import make_user


class _FakeRedis:
    """最小 Redis 替身 · 只实现 get/setex(token 缓存够用)。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.setex_calls = 0

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self.setex_calls += 1
        self.store[key] = value


def _trade() -> TradeFilledEvent:
    return TradeFilledEvent(
        symbol="NVDA", market="us", side="buy",
        quantity=Decimal("10"), price=Decimal("140"),
        notional=Decimal("1400"), commission=Decimal("0"), currency="USD",
    )


@pytest.fixture
def feishu_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "feishu_app_id", "cli_fake")
    monkeypatch.setattr(settings, "feishu_app_secret", "secret_fake")


# ── _to_plain_text:剥 Markdown 标记 ──────────────────────────────────


def test_to_plain_text_strips_markers() -> None:
    md = "*点金 Midas · 成交通知*\n\n📊 NVDA\n_本次为模拟交易,不构成投资建议_"
    plain = feishu_adapter._to_plain_text(md)
    assert "*" not in plain
    assert "_" not in plain
    assert "`" not in plain
    assert "点金 Midas · 成交通知" in plain
    assert "本次为模拟交易,不构成投资建议" in plain


# ── token 缓存:命中复用 / force_refresh 重取 ─────────────────────────


@pytest.mark.asyncio
@pytest.mark.usefixtures("feishu_creds")
async def test_token_cached_and_reused() -> None:
    fetches = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal fetches
        if "tenant_access_token" in str(request.url):
            fetches += 1
            return httpx.Response(200, json={
                "code": 0, "tenant_access_token": "tok-1", "expire": 7200,
            })
        return httpx.Response(200, json={"code": 0})

    fake = _FakeRedis()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        t1 = await feishu_client.get_tenant_access_token(redis=fake, client=c)
        t2 = await feishu_client.get_tenant_access_token(redis=fake, client=c)
        assert t1 == t2 == "tok-1"
        assert fetches == 1, "第二次应命中缓存,不再打 token 接口"
        assert fake.setex_calls == 1
        # force_refresh 强制重取
        t3 = await feishu_client.get_tenant_access_token(
            redis=fake, client=c, force_refresh=True,
        )
        assert t3 == "tok-1"
        assert fetches == 2


@pytest.mark.asyncio
@pytest.mark.usefixtures("feishu_creds")
async def test_send_text_posts_to_im_api() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "tenant_access_token" in str(request.url):
            return httpx.Response(200, json={
                "code": 0, "tenant_access_token": "tok-x", "expire": 7200,
            })
        # IM 发消息
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "om_x"}})

    fake = _FakeRedis()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        await feishu_client.send_text("ou_abc", "你好世界", redis=fake, client=c)

    assert "im/v1/messages" in captured["url"]
    assert "receive_id_type=open_id" in captured["url"]
    assert captured["auth"] == "Bearer tok-x"
    assert captured["body"]["receive_id"] == "ou_abc"
    assert captured["body"]["msg_type"] == "text"
    assert json.loads(captured["body"]["content"]) == {"text": "你好世界"}


@pytest.mark.asyncio
@pytest.mark.usefixtures("feishu_creds")
async def test_send_text_refreshes_on_auth_error() -> None:
    """token 过期(99991663)→ 失效缓存重取一次再发 · 第二次成功。"""
    states = {"sends": 0, "fetches": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "tenant_access_token" in str(request.url):
            states["fetches"] += 1
            tok = f"tok-{states['fetches']}"
            return httpx.Response(200, json={
                "code": 0, "tenant_access_token": tok, "expire": 7200,
            })
        states["sends"] += 1
        if states["sends"] == 1:
            return httpx.Response(200, json={"code": 99991663, "msg": "token invalid"})
        return httpx.Response(200, json={"code": 0})

    fake = _FakeRedis()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        await feishu_client.send_text("ou_abc", "x", redis=fake, client=c)
    assert states["sends"] == 2, "首发 401 后应重发一次"
    assert states["fetches"] == 2, "应 force_refresh 重取 token"


# ── adapter:send_event 调 send_text 且文本已剥标记 ───────────────────


@pytest.mark.asyncio
async def test_adapter_send_event_uses_plain_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    async def _recorder(open_id: str, text: str, **_kw: Any) -> None:
        captured["open_id"] = open_id
        captured["text"] = text

    monkeypatch.setattr(feishu_client, "send_text", _recorder)
    await feishu_adapter.send_event("ou_z", _trade())
    assert captured["open_id"] == "ou_z"
    assert "*" not in captured["text"]
    assert "_" not in captured["text"]
    assert "成交通知" in captured["text"]


# ── dispatcher 双通道:两边都绑 → 都发 ───────────────────────────────


@pytest.fixture
def bot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tg_bot_token", "123456:FAKE")


def _tg_ok(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


@pytest.mark.asyncio
@pytest.mark.usefixtures("bot_token", "feishu_creds")
async def test_dispatch_both_channels_when_both_bound(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tg_chat_id + feishu_open_id 都绑 → telegram + feishu 都发(独立通道)。"""
    feishu_calls: list[str] = []

    async def _fake_feishu_send(open_id: str, _text: str, **_kw: Any) -> None:
        feishu_calls.append(open_id)

    monkeypatch.setattr(feishu_client, "send_text", _fake_feishu_send)

    user = await make_user(db_session)
    db_session.add(NotificationConfig(
        user_id=user.id, tg_chat_id="chat42", feishu_open_id="ou_42",
    ))
    await db_session.commit()

    async with httpx.AsyncClient(transport=httpx.MockTransport(_tg_ok)) as c:
        result = await dispatch(db_session, user.id, _trade(), client=c)

    channels = {r.channel for r in result.results if r.ok}
    assert channels == {"telegram", "feishu"}
    assert feishu_calls == ["ou_42"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("feishu_creds")
async def test_dispatch_feishu_only_when_tg_unbound(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """只绑飞书(无 tg_chat_id / 未配 tg token)→ 只发飞书。"""
    async def _fake_feishu_send(_open_id: str, _text: str, **_kw: Any) -> None:
        return None

    monkeypatch.setattr(feishu_client, "send_text", _fake_feishu_send)
    user = await make_user(db_session)
    db_session.add(NotificationConfig(user_id=user.id, feishu_open_id="ou_only"))
    await db_session.commit()
    result = await dispatch(db_session, user.id, _trade())
    assert [r.channel for r in result.results if r.ok] == ["feishu"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("bot_token")
async def test_dispatch_no_feishu_when_app_unconfigured(
    db_session: AsyncSession,
) -> None:
    """绑了 feishu_open_id 但未配飞书应用(app_id/secret 空)→ 飞书不发(只 telegram)。"""
    user = await make_user(db_session)
    db_session.add(NotificationConfig(
        user_id=user.id, tg_chat_id="c", feishu_open_id="ou_x",
    ))
    await db_session.commit()
    async with httpx.AsyncClient(transport=httpx.MockTransport(_tg_ok)) as c:
        result = await dispatch(db_session, user.id, _trade(), client=c)
    assert [r.channel for r in result.results if r.ok] == ["telegram"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("feishu_creds")
async def test_send_test_feishu_not_bound(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    config = NotificationConfig(user_id=user.id, feishu_open_id=None)
    db_session.add(config)
    await db_session.commit()
    r = await send_test(config, "feishu")
    assert r.ok is False
    assert "未绑定飞书" in (r.error or "")
