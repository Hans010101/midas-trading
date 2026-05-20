"""Dispatcher pytest · 验证 per-channel 失败独立 + 总开关过滤。"""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationConfig
from app.services.notifications.dispatcher import dispatch, send_test
from app.services.notifications.events import (
    PriceAnomalyEvent,
    TradeFilledEvent,
)
from tests.factories import make_user


def _both_ok_handler(request: httpx.Request) -> httpx.Response:
    if "feishu" in str(request.url):
        return httpx.Response(200, json={"StatusCode": 0})
    return httpx.Response(200, json={"ok": True})


@pytest.mark.asyncio
async def test_dispatch_no_config_returns_empty(db_session: AsyncSession):
    user = await make_user(db_session)
    await db_session.commit()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_both_ok_handler),
    ) as client:
        result = await dispatch(
            db_session, user.id,
            TradeFilledEvent(symbol="NVDA", market="us", currency="USD"),
            client=client,
        )
    assert result.results == []
    assert not result.any_sent


@pytest.mark.asyncio
async def test_dispatch_both_channels_when_configured(db_session: AsyncSession):
    user = await make_user(db_session)
    config = NotificationConfig(
        user_id=user.id,
        feishu_webhook_url="https://feishu.example/webhook/x",
        tg_bot_token="bot:token",
        tg_chat_id="chat42",
    )
    db_session.add(config)
    await db_session.commit()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_both_ok_handler),
    ) as client:
        result = await dispatch(
            db_session, user.id,
            TradeFilledEvent(
                symbol="NVDA", market="us", side="buy",
                quantity=Decimal("10"), price=Decimal("140"),
                notional=Decimal("1400"), commission=Decimal("0"),
                currency="USD",
            ),
            client=client,
        )
    channels = {r.channel for r in result.results if r.ok}
    assert channels == {"feishu", "telegram"}


@pytest.mark.asyncio
async def test_dispatch_feishu_fails_telegram_succeeds(db_session: AsyncSession):
    """单通道失败不影响另一通道(0009 § 3 per-channel 失败独立)。"""
    user = await make_user(db_session)
    config = NotificationConfig(
        user_id=user.id,
        feishu_webhook_url="https://feishu.example/webhook/bad",
        tg_bot_token="bot:token", tg_chat_id="chat42",
    )
    db_session.add(config)
    await db_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        if "feishu" in str(request.url):
            return httpx.Response(200, json={"StatusCode": 19021, "StatusMessage": "no keyword"})
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await dispatch(
            db_session, user.id,
            TradeFilledEvent(symbol="NVDA", market="us", currency="USD"),
            client=client,
        )
    by_channel = {r.channel: r for r in result.results}
    assert by_channel["feishu"].ok is False
    assert by_channel["telegram"].ok is True


@pytest.mark.asyncio
async def test_dispatch_trade_alert_disabled_skips(db_session: AsyncSession):
    user = await make_user(db_session)
    config = NotificationConfig(
        user_id=user.id,
        feishu_webhook_url="https://feishu.example/webhook/x",
        trade_alert_enabled=False,
    )
    db_session.add(config)
    await db_session.commit()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_both_ok_handler),
    ) as client:
        result = await dispatch(
            db_session, user.id,
            TradeFilledEvent(symbol="NVDA", market="us", currency="USD"),
            client=client,
        )
    assert result.results == []


@pytest.mark.asyncio
async def test_dispatch_price_alert_separate_switch(db_session: AsyncSession):
    """trade off + price on:price 还会推。"""
    user = await make_user(db_session)
    config = NotificationConfig(
        user_id=user.id,
        feishu_webhook_url="https://feishu.example/webhook/x",
        trade_alert_enabled=False,
        price_alert_enabled=True,
    )
    db_session.add(config)
    await db_session.commit()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_both_ok_handler),
    ) as client:
        result = await dispatch(
            db_session, user.id,
            PriceAnomalyEvent(
                symbol="BTC/USDT", market="crypto",
                current_price=Decimal("100000"),
                reference_price=Decimal("95000"),
                change_pct=Decimal("5.26"),
                currency="USDT",
            ),
            client=client,
        )
    assert len(result.results) == 1
    assert result.results[0].channel == "feishu"
    assert result.results[0].ok is True


@pytest.mark.asyncio
async def test_send_test_feishu_unconfigured(db_session: AsyncSession):
    user = await make_user(db_session)
    config = NotificationConfig(
        user_id=user.id,
        tg_bot_token="t", tg_chat_id="c",  # 只配 TG,没配飞书
    )
    db_session.add(config)
    await db_session.commit()

    r = await send_test(config, "feishu")
    assert r.ok is False
    assert "未配置" in (r.error or "")


@pytest.mark.asyncio
async def test_send_test_feishu_ok(db_session: AsyncSession):
    user = await make_user(db_session)
    config = NotificationConfig(
        user_id=user.id,
        feishu_webhook_url="https://feishu.example/webhook/test",
    )
    db_session.add(config)
    await db_session.commit()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_both_ok_handler),
    ) as client:
        r = await send_test(config, "feishu", client=client)
    assert r.ok is True
