"""下单来源标记(source 列)· ADR 0036 U0(AI 模拟交易底座)。

验证:
① facade execute 把 OrderIntent.source 落到订单行(现货 VirtualOrder + 永续 VirtualPerpOrder);
② 不传 source 时默认 'manual'(= 网页手动路径默认 · 与 DB server_default 一致);
③ ★ 撮合引擎不设此列(引擎零改动),由 facade 在 commit 前标记 —— 这是 AI 单未来复用同一条
   非 HTTP 下单通道(execute)、只换 source='ai_signal' 的基础。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import VirtualPerpOrder
from app.models.virtual import VirtualOrder
from app.services.bot import order as order_mod
from tests.factories import make_user, make_virtual_account


class _FakeCH:
    def __init__(self, klines: list[Any] | None = None) -> None:
        self._klines = klines or []
        self._client = object()

    async def select_kline(self, **_kwargs: Any) -> list[Any]:
        return list(self._klines)


def _bar(close: float) -> SimpleNamespace:
    return SimpleNamespace(close=Decimal(str(close)), volume=Decimal("1"))


def test_order_intent_default_source_is_manual() -> None:
    """不传 source → 'manual'(老调用方零回归 · 与 DB server_default 一致)。"""
    intent = order_mod.OrderIntent(market="us", symbol="NVDA", direction="buy")
    assert intent.source == "manual"


@pytest.mark.asyncio
async def test_spot_order_tagged_with_source(db_session: AsyncSession) -> None:
    """现货成交单带上 intent.source('ai_signal')· 引擎不设、facade 标。"""
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="us")
    await db_session.commit()
    ch = _FakeCH([_bar(100.0)])

    result = await order_mod.execute(
        db_session, ch, user.id,  # type: ignore[arg-type]
        order_mod.OrderIntent(
            market="us", symbol="NVDA", direction="buy", source="ai_signal",
        ),
    )
    assert result.filled is True
    order = await db_session.scalar(
        select(VirtualOrder).where(VirtualOrder.symbol == "NVDA"),
    )
    assert order is not None
    assert order.source == "ai_signal"


@pytest.mark.asyncio
async def test_spot_order_default_source_manual_via_facade(
    db_session: AsyncSession,
) -> None:
    """facade 不传 source → 订单行落 'manual'(= 现有 bot/网页手动行为)。"""
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="us")
    await db_session.commit()
    ch = _FakeCH([_bar(100.0)])

    result = await order_mod.execute(
        db_session, ch, user.id,  # type: ignore[arg-type]
        order_mod.OrderIntent(market="us", symbol="AAPL", direction="buy"),
    )
    assert result.filled is True
    order = await db_session.scalar(
        select(VirtualOrder).where(VirtualOrder.symbol == "AAPL"),
    )
    assert order is not None
    assert order.source == "manual"


@pytest.mark.asyncio
async def test_perp_order_tagged_with_source(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """永续成交单带上 intent.source('ai_signal')· perp 引擎/dispatcher 不设、facade 标。"""

    async def _fake_mark(_ch: object, _sym: str) -> Decimal:
        return Decimal("60000")

    monkeypatch.setattr(order_mod, "_perp_mark", _fake_mark)
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="crypto")
    await db_session.commit()

    result = await order_mod.execute(
        db_session, _FakeCH(), user.id,  # type: ignore[arg-type]
        order_mod.OrderIntent(
            market="crypto", symbol="BTC/USDT", direction="open_long",
            source="ai_signal",
        ),
    )
    assert result.filled is True
    order = await db_session.scalar(
        select(VirtualPerpOrder).where(VirtualPerpOrder.symbol == "BTCUSDT"),
    )
    assert order is not None
    assert order.source == "ai_signal"
