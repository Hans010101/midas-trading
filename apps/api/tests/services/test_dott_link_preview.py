"""做T 推送关 Telegram 底部链接预览卡(fix/dot-t-disable-link-preview)单测。

两层验证:
  ① client send():disable_preview=True → payload 带 disable_web_page_preview · 默认不带(其他推送不变);
  ② adapter send_event():做T 两 kind → disable_preview=True · 其他事件(价格异动等)→ False。
★只关底部预览卡,正文 [SYMBOL](url) 内联链接不动(文案层不在本刀改动范围)。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.services.notifications import telegram
from app.services.notifications.adapters import telegram as tg_adapter
from app.services.notifications.events import NotificationKind


def _ok_handler(captured: dict) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.read().decode())
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    return handler


@pytest.mark.asyncio
async def test_client_send_disable_preview_adds_field() -> None:
    # ★disable_preview=True → payload 带 disable_web_page_preview=true(关底部预览卡)
    captured: dict = {}
    async with httpx.AsyncClient(transport=httpx.MockTransport(_ok_handler(captured))) as c:
        await telegram.send("t:fake", "c", "[BTCUSDT](https://x/y?symbol=BTCUSDT)",
                            disable_preview=True, client=c)
    assert captured["body"]["disable_web_page_preview"] is True
    # ★正文内联链接原样在 payload.text(只关预览卡,不动超链接本身)
    assert "[BTCUSDT](https://x/y?symbol=BTCUSDT)" in captured["body"]["text"]


@pytest.mark.asyncio
async def test_client_send_default_no_preview_field() -> None:
    # 默认(不传 disable_preview)→ payload 不带该字段 → TG 原生预览行为(其他推送不受影响)
    captured: dict = {}
    async with httpx.AsyncClient(transport=httpx.MockTransport(_ok_handler(captured))) as c:
        await telegram.send("t:fake", "c", "成交通知", client=c)
    assert "disable_web_page_preview" not in captured["body"]


async def _capture_send_event(monkeypatch: pytest.MonkeyPatch, kind: NotificationKind) -> bool:
    """跑 send_event(给定 kind)· 返回是否传了 disable_preview=True(隔离渲染,只验路由)。"""
    seen: dict = {}

    async def fake_send(*_args: object, disable_preview: bool = False, **_kwargs: object) -> None:
        seen["disable_preview"] = disable_preview

    monkeypatch.setattr(tg_adapter.telegram_client, "send", fake_send)
    monkeypatch.setattr(tg_adapter, "render_telegram", lambda _e: "txt")
    await tg_adapter.send_event("chat", SimpleNamespace(kind=kind))  # type: ignore[arg-type]
    return seen["disable_preview"]


@pytest.mark.asyncio
async def test_send_event_dott_digest_disables_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    # ★体系1 全景 → 关预览
    assert await _capture_send_event(monkeypatch, NotificationKind.DOTT_DIGEST) is True


@pytest.mark.asyncio
async def test_send_event_dott_transition_disables_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    # ★体系2 转换 → 关预览
    assert await _capture_send_event(monkeypatch, NotificationKind.DOTT_TRANSITION) is True


@pytest.mark.asyncio
async def test_real_dott_digest_event_disables_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    # ★问题1 回归锁死:用 worker 实际走的工厂造【真实】DottDigestEvent(全景)· 经 send_event
    #   → disable_preview=True(证明全景关预览不是 bug · 截图带卡纯属部署时序:旧全景早于 PR#43 上线)
    from app.services.notifications.dott_push import _make_dott_event

    seen: dict = {}

    async def fake_send(*_a: object, disable_preview: bool = False, **_k: object) -> None:
        seen["disable_preview"] = disable_preview

    monkeypatch.setattr(tg_adapter.telegram_client, "send", fake_send)
    monkeypatch.setattr(tg_adapter, "render_telegram", lambda _e: "全景文案")
    event = _make_dott_event(NotificationKind.DOTT_DIGEST, "全景文案")
    await tg_adapter.send_event("chat", event)
    assert seen["disable_preview"] is True


@pytest.mark.asyncio
async def test_send_event_other_kinds_keep_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    # ★其他推送(价格异动/成交/告警/周报)→ disable_preview=False · 预览行为一字不动
    for kind in (
        NotificationKind.PRICE_ANOMALY,
        NotificationKind.TRADE_FILLED,
        NotificationKind.ALERT_TRIGGERED,
        NotificationKind.WEEKLY_REPORT,
    ):
        assert await _capture_send_event(monkeypatch, kind) is False
