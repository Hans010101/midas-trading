"""Dispatcher pytest · 0025 G2a 统一 bot · 已绑定 + 全局 token 才发 · 总开关过滤。"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.notification import NotificationConfig
from app.services.notifications.dispatcher import dispatch, send_test
from app.services.notifications.events import (
    PriceAnomalyEvent,
    TradeFilledEvent,
)
from tests.factories import make_user


def _ok_handler(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


@pytest.fixture
def bot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """配上全局统一 bot token(测发送路径)· monkeypatch 自动还原。"""
    monkeypatch.setattr(settings, "tg_bot_token", "123456:FAKE_TEST")


def _trade() -> TradeFilledEvent:
    return TradeFilledEvent(
        symbol="NVDA", market="us", side="buy",
        quantity=Decimal("10"), price=Decimal("140"),
        notional=Decimal("1400"), commission=Decimal("0"), currency="USD",
    )


@pytest.mark.asyncio
async def test_dispatch_no_config_returns_empty(db_session: AsyncSession):
    user = await make_user(db_session)
    await db_session.commit()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_ok_handler),
    ) as client:
        result = await dispatch(db_session, user.id, _trade(), client=client)
    assert result.results == []
    assert not result.any_sent


@pytest.mark.asyncio
@pytest.mark.usefixtures("bot_token")
async def test_dispatch_bound_sends_telegram(db_session: AsyncSession):
    """已绑定(tg_chat_id)+ 全局 token → 经统一 bot 发 Telegram。"""
    user = await make_user(db_session)
    db_session.add(NotificationConfig(user_id=user.id, tg_chat_id="chat42"))
    await db_session.commit()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_ok_handler),
    ) as client:
        result = await dispatch(db_session, user.id, _trade(), client=client)
    assert [r.channel for r in result.results if r.ok] == ["telegram"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("bot_token")
async def test_dispatch_not_bound_no_send(db_session: AsyncSession):
    """未绑定(tg_chat_id 为 None)→ 不发。"""
    user = await make_user(db_session)
    db_session.add(NotificationConfig(user_id=user.id, tg_chat_id=None))
    await db_session.commit()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_ok_handler),
    ) as client:
        result = await dispatch(db_session, user.id, _trade(), client=client)
    assert result.results == []


@pytest.mark.asyncio
async def test_dispatch_no_global_token_no_send(db_session: AsyncSession):
    """未配全局 token(统一 bot 未启用)→ 即使已绑定也不发(与 G1「未配一切照旧」一致)。"""
    # settings.tg_bot_token 默认 ""(conftest 未设,且无 bot_token fixture)
    user = await make_user(db_session)
    db_session.add(NotificationConfig(user_id=user.id, tg_chat_id="chat42"))
    await db_session.commit()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_ok_handler),
    ) as client:
        result = await dispatch(db_session, user.id, _trade(), client=client)
    assert result.results == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("bot_token")
async def test_dispatch_trade_disabled_skips(db_session: AsyncSession):
    user = await make_user(db_session)
    db_session.add(
        NotificationConfig(user_id=user.id, tg_chat_id="c", trade_alert_enabled=False),
    )
    await db_session.commit()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_ok_handler),
    ) as client:
        result = await dispatch(db_session, user.id, _trade(), client=client)
    assert result.results == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("bot_token")
async def test_dispatch_price_separate_switch(db_session: AsyncSession):
    """trade off + price on:价格异动仍推。"""
    user = await make_user(db_session)
    db_session.add(
        NotificationConfig(
            user_id=user.id, tg_chat_id="c",
            trade_alert_enabled=False, price_alert_enabled=True,
        ),
    )
    await db_session.commit()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_ok_handler),
    ) as client:
        result = await dispatch(
            db_session, user.id,
            PriceAnomalyEvent(
                symbol="BTC/USDT", market="crypto",
                current_price=Decimal("100000"), reference_price=Decimal("95000"),
                change_pct=Decimal("5.26"), currency="USDT",
            ),
            client=client,
        )
    assert len(result.results) == 1
    assert result.results[0].channel == "telegram"
    assert result.results[0].ok is True


@pytest.mark.asyncio
async def test_send_test_not_bound(db_session: AsyncSession):
    user = await make_user(db_session)
    config = NotificationConfig(user_id=user.id, tg_chat_id=None)
    db_session.add(config)
    await db_session.commit()
    r = await send_test(config, "telegram")
    assert r.ok is False
    assert "未绑定" in (r.error or "")


@pytest.mark.asyncio
@pytest.mark.usefixtures("bot_token")
async def test_send_test_bound_ok(db_session: AsyncSession):
    user = await make_user(db_session)
    config = NotificationConfig(user_id=user.id, tg_chat_id="c")
    db_session.add(config)
    await db_session.commit()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_ok_handler),
    ) as client:
        r = await send_test(config, "telegram", client=client)
    assert r.ok is True


@pytest.mark.asyncio
async def test_send_test_unknown_channel_rejected(db_session: AsyncSession):
    """飞书已移除:send_test 对未知通道返回错误(防回归引用旧通道)。"""
    user = await make_user(db_session)
    config = NotificationConfig(user_id=user.id, tg_chat_id="c")
    db_session.add(config)
    await db_session.commit()
    r = await send_test(config, "feishu")
    assert r.ok is False
    assert "未知通道" in (r.error or "")
