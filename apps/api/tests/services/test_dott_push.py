"""做T 真发广播(M2-5)单测 · ★总闸关不发 / 开真发 / Pro 发送前确认 / 失败逐人隔离 / 渲染 / 订阅筛选。

纯逻辑(mock query_dott_subscribers + dispatch + resolve_plan · 不需 PG)· 验证发送链路安全网。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.services.notifications.dispatcher import ChannelResult, DispatchResult, _kind_enabled
from app.services.notifications.dott_push import broadcast_dott
from app.services.notifications.events import (
    DottDigestEvent,
    DottTransitionEvent,
    NotificationKind,
)
from app.services.notifications.templates import render_telegram

_OK = DispatchResult(results=[ChannelResult(channel="telegram", ok=True)])


@pytest.mark.asyncio
async def test_broadcast_flag_off_never_sends(monkeypatch: pytest.MonkeyPatch) -> None:
    # ★总闸 DOTT_PUSH_LIVE=false → 不真发(live=False · dispatch 一次都不调)· 影子刹车
    monkeypatch.setattr(settings, "dott_push_live", False)
    disp = AsyncMock()
    monkeypatch.setattr("app.services.notifications.dott_push.dispatch", disp)
    res = await broadcast_dott(object(), ["msg"], kind=NotificationKind.DOTT_DIGEST)  # type: ignore[arg-type]
    assert res.live is False
    assert res.sent == 0
    disp.assert_not_called()


@pytest.mark.asyncio
async def test_broadcast_pro_filter_only_sends_to_pro(monkeypatch: pytest.MonkeyPatch) -> None:
    # ★总闸开 + 发送前 Pro 再确认:u1=pro 发 · u2=free 跳过(双保险,非 Pro 即便 DB flag=true 也不发)
    monkeypatch.setattr(settings, "dott_push_live", True)
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(
        "app.services.notifications.dott_push.query_dott_subscribers",
        AsyncMock(return_value=[(u1, "c1"), (u2, "c2")]),
    )

    async def fake_plan(_session: object, user_id: uuid.UUID) -> str:
        return "pro" if user_id == u1 else "free"

    monkeypatch.setattr("app.services.notifications.dott_push.resolve_plan", fake_plan)
    disp = AsyncMock(return_value=_OK)
    monkeypatch.setattr("app.services.notifications.dott_push.dispatch", disp)

    res = await broadcast_dott(object(), ["m1"], kind=NotificationKind.DOTT_DIGEST)  # type: ignore[arg-type]
    assert res.live is True
    assert res.subscribers == 2
    assert res.sent == 1            # ★只 u1(pro)真发
    assert res.skipped_non_pro == 1  # ★u2(free)发送前被拦
    assert disp.await_count == 1    # ★dispatch 只对 pro 调用


@pytest.mark.asyncio
async def test_broadcast_failure_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    # ★失败逐人隔离:u1 dispatch 抛 → 计 failed · u2 照常发(一人失败不影响其他 · 照搬周报)
    monkeypatch.setattr(settings, "dott_push_live", True)
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(
        "app.services.notifications.dott_push.query_dott_subscribers",
        AsyncMock(return_value=[(u1, "c1"), (u2, "c2")]),
    )
    monkeypatch.setattr(
        "app.services.notifications.dott_push.resolve_plan", AsyncMock(return_value="pro"),
    )
    disp = AsyncMock(side_effect=[RuntimeError("boom"), _OK])
    monkeypatch.setattr("app.services.notifications.dott_push.dispatch", disp)

    res = await broadcast_dott(object(), ["m1"], kind=NotificationKind.DOTT_TRANSITION)  # type: ignore[arg-type]
    assert res.failed == 1
    assert res.sent == 1
    assert disp.await_count == 2  # 两人都尝试(不因第一人失败中断)


def test_render_telegram_dott_events_passthrough() -> None:
    # 做T 事件 render = 原样返回组装好的文案(不重新渲染 · 文案在组装期已过门禁)
    assert render_telegram(DottDigestEvent(message="📊 做T扫描 · 14:00\n…")) == "📊 做T扫描 · 14:00\n…"
    assert render_telegram(DottTransitionEvent(message="📊 布林做T · 转换提醒")) == "📊 布林做T · 转换提醒"


def test_kind_enabled_dott_maps_to_each_field() -> None:
    # _kind_enabled:DOTT_DIGEST→dott_digest_enabled · DOTT_TRANSITION→dott_transition_enabled(各自筛选)
    cfg = SimpleNamespace(dott_digest_enabled=True, dott_transition_enabled=False)
    assert _kind_enabled(DottDigestEvent(message="x"), cfg) is True       # type: ignore[arg-type]
    assert _kind_enabled(DottTransitionEvent(message="x"), cfg) is False  # type: ignore[arg-type]
    cfg2 = SimpleNamespace(dott_digest_enabled=False, dott_transition_enabled=True)
    assert _kind_enabled(DottDigestEvent(message="x"), cfg2) is False      # type: ignore[arg-type]
    assert _kind_enabled(DottTransitionEvent(message="x"), cfg2) is True   # type: ignore[arg-type]


def test_dott_events_quiet_not_exempt() -> None:
    # ★两体系都受用户安静时段(quiet_exempt=False · dispatch 会按 config.quiet_hours 过滤 · 半夜不打扰)
    assert DottDigestEvent.quiet_exempt is False
    assert DottTransitionEvent.quiet_exempt is False
