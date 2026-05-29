"""#296 改动一 · 成交通知去重(方向③ 合一)单测。

覆盖:engine notify 守卫(notify=True 发 / notify=False 抑制)、spot 事件 builder 字段、
bot 富回执渲染(✅ 前缀 + 返回菜单键盘 + 复用 A 文案)。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.virtual import Currency, OrderSide, OrderStatus
from app.services.bot import telegram_ui as ui
from app.services.notifications.perp_events import build_trade_filled_event
from app.services.virtual_trading.engine import (
    PlaceOrderRequest,
    place_market_order,
)
from tests.factories import (
    make_static_price_fetcher,
    make_user,
    make_virtual_account,
)


async def _setup(db_session: AsyncSession):
    user = await make_user(db_session)
    await make_virtual_account(
        db_session, user_id=user.id, market="us",
        initial_capital=Decimal("100000"),
    )
    await db_session.commit()
    fetcher = make_static_price_fetcher({("NVDA", "us"): Decimal("140")})
    return user, fetcher


@pytest.mark.asyncio
async def test_notify_default_true_emits(db_session: AsyncSession):
    """网页/默认路径:notify 默认 True → 引擎发异步成交推送(行为不变)。"""
    user, fetcher = await _setup(db_session)
    with patch("app.services.virtual_trading.engine.emit_trade_filled") as m:
        req = PlaceOrderRequest(
            user_id=user.id, symbol="NVDA", market="us",
            side=OrderSide.BUY, quantity=Decimal("10"),
        )
        order = await place_market_order(db_session, req, fetcher)
        await db_session.commit()
    assert order.status == OrderStatus.FILLED
    m.assert_called_once_with(order.id)


@pytest.mark.asyncio
async def test_notify_false_suppresses_emit(db_session: AsyncSession):
    """bot 路径:notify=False → 引擎抑制异步推送(bot 走自己的富回执去重)。"""
    user, fetcher = await _setup(db_session)
    with patch("app.services.virtual_trading.engine.emit_trade_filled") as m:
        req = PlaceOrderRequest(
            user_id=user.id, symbol="NVDA", market="us",
            side=OrderSide.BUY, quantity=Decimal("10"), notify=False,
        )
        order = await place_market_order(db_session, req, fetcher)
        await db_session.commit()
    assert order.status == OrderStatus.FILLED  # 撮合不受影响 · 只是不发推送
    m.assert_not_called()


def test_build_trade_filled_event_fields():
    order = SimpleNamespace(
        symbol="NVDA", market="us", side="buy", quantity=Decimal("10"),
        price=Decimal("140"), notional=Decimal("1400"),
        commission=Decimal("0"), realized_pnl=None,
    )
    account = SimpleNamespace(currency=Currency.USD)
    ev = build_trade_filled_event(order, account)  # type: ignore[arg-type]
    assert ev.symbol == "NVDA"
    assert ev.market == "us"
    assert ev.currency == "USD"
    assert ev.notional == Decimal("1400")


def test_render_order_receipt_prefix_and_keyboard():
    body = (
        "*点金 Midas · 合约成交*\n\n📊 BTCUSDT · 永续 · 逐仓 20x\n"
        "_本次为模拟交易,不构成投资建议_"
    )
    reply = ui.render_order_receipt(body)
    assert reply.text.startswith("✅ ")          # 保留成功确认感
    assert "合约成交" in reply.text               # 复用 A 富文本
    assert "本次为模拟交易" in reply.text          # 免责仅一句(body 内)
    assert reply.keyboard is not None             # 「返回菜单」键盘在
