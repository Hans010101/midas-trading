"""AI 模拟下单端点 pytest · 0036 批次甲(★最红线敏感单元)。

验证:
- ai-order 走 U0 的 execute · 成交单标 source='ai_signal'(现货 + 加密永续)。
- ★ 现货 sell 无持仓 → 拒单(拍板④:无持仓观望 · 绝不裸做空)。
- ★ hk 已接入:按手取整成交(00700 每手 100)· 不在池 → 拒单(绝不裸下单)。
- 市场不支持的方向 → 400。
端点只做「校验 + 构造 OrderIntent(source=ai_signal) + 调 execute」,不新开下单路径
(execute 的撮合/分流/source 标记已由 test_bot_order* 充分覆盖)。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.virtual import place_ai_order
from app.models.perp import VirtualPerpOrder
from app.models.virtual import VirtualOrder
from app.schemas.virtual import AiOrderRequest
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


@pytest.mark.asyncio
async def test_ai_order_spot_buy_tags_ai_signal(db_session: AsyncSession) -> None:
    """现货 buy(cn/us)→ 成交 · 订单标 source='ai_signal'(经 execute)。"""
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="us")
    await db_session.commit()
    ch = _FakeCH([_bar(100.0)])

    resp = await place_ai_order(
        AiOrderRequest(symbol="NVDA", market="us", direction="buy"),
        ch,  # type: ignore[arg-type]
        user,  # type: ignore[arg-type]
        db_session,
        "zh",  # lang(i18n Phase3 刀2 · 直接调用端点函数需显式传)
    )
    assert resp.filled is True
    assert resp.source == "ai_signal"
    order = await db_session.scalar(select(VirtualOrder).where(VirtualOrder.symbol == "NVDA"))
    assert order is not None
    assert order.source == "ai_signal"


@pytest.mark.asyncio
async def test_ai_order_cn_buy_tags_ai_signal(db_session: AsyncSession) -> None:
    """A股 buy → 成交 · 订单标 source='ai_signal'(与美股同一现货撮合路径)。"""
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="cn")
    await db_session.commit()
    ch = _FakeCH([_bar(1800.0)])

    resp = await place_ai_order(
        AiOrderRequest(symbol="600519", market="cn", direction="buy"),
        ch,  # type: ignore[arg-type]
        user,  # type: ignore[arg-type]
        db_session,
        "zh",  # lang(i18n Phase3 刀2 · 直接调用端点函数需显式传)
    )
    assert resp.filled is True
    assert resp.source == "ai_signal"
    order = await db_session.scalar(select(VirtualOrder).where(VirtualOrder.symbol == "600519"))
    assert order is not None
    assert order.source == "ai_signal"


@pytest.mark.asyncio
async def test_ai_order_spot_sell_no_position_rejected(db_session: AsyncSession) -> None:
    """★拍板④:现货 sell 无持仓 → 拒单(无可平持仓)· 绝不裸做空。"""
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="us")
    await db_session.commit()
    ch = _FakeCH([_bar(100.0)])

    resp = await place_ai_order(
        AiOrderRequest(symbol="NVDA", market="us", direction="sell"),
        ch,  # type: ignore[arg-type]
        user,  # type: ignore[arg-type]
        db_session,
        "zh",  # lang(i18n Phase3 刀2 · 直接调用端点函数需显式传)
    )
    assert resp.filled is False  # 无持仓 → 不成交(观望)· 没有裸做空


@pytest.mark.asyncio
async def test_ai_order_crypto_open_long_tags_ai_signal(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """加密 open_long → 永续成交 · 订单标 source='ai_signal'。"""

    async def _fake_mark(_ch: object, _sym: str) -> Decimal:
        return Decimal("60000")

    monkeypatch.setattr(order_mod, "_perp_mark", _fake_mark)
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="crypto")
    await db_session.commit()

    resp = await place_ai_order(
        AiOrderRequest(symbol="BTC/USDT", market="crypto", direction="open_long"),
        _FakeCH(),  # type: ignore[arg-type]
        user,  # type: ignore[arg-type]
        db_session,
        "zh",  # lang(i18n Phase3 刀2 · 直接调用端点函数需显式传)
    )
    assert resp.filled is True
    assert resp.source == "ai_signal"
    order = await db_session.scalar(
        select(VirtualPerpOrder).where(VirtualPerpOrder.symbol == "BTCUSDT"),
    )
    assert order is not None
    assert order.source == "ai_signal"


@pytest.mark.asyncio
async def test_ai_order_hk_lot_rounded(db_session: AsyncSession) -> None:
    """港股 AI 一键(已接入)→ 成交 · 数量按手取整(00700 每手 100)· source='ai_signal'。

    价 100 · notional 50000 HKD / 100 = 500 股 → floor(500/100)*100 = 500(5 手)。
    ★ 红线:走同一虚拟撮合(execute → place_market_order)· 按手取整 · 不裸下单。
    """
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="hk")
    await db_session.commit()
    ch = _FakeCH([_bar(100.0)])

    resp = await place_ai_order(
        AiOrderRequest(symbol="00700", market="hk", direction="buy"),
        ch,  # type: ignore[arg-type]
        user,  # type: ignore[arg-type]
        db_session,
        "zh",  # lang(i18n Phase3 刀2 · 直接调用端点函数需显式传)
    )
    assert resp.filled is True
    assert resp.source == "ai_signal"
    order = await db_session.scalar(select(VirtualOrder).where(VirtualOrder.symbol == "00700"))
    assert order is not None
    assert order.source == "ai_signal"
    assert Decimal(order.quantity) % 100 == 0   # ★ 按手取整(每手 100 整数倍)
    assert Decimal(order.quantity) == Decimal(500)


@pytest.mark.asyncio
async def test_ai_order_hk_not_in_pool_rejected(db_session: AsyncSession) -> None:
    """港股 AI 一键:不在下单池标的(resolve None)→ 不成交(拒 · 绝不裸下单)。"""
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="hk")
    await db_session.commit()
    ch = _FakeCH([_bar(100.0)])

    resp = await place_ai_order(
        AiOrderRequest(symbol="99999", market="hk", direction="buy"),
        ch,  # type: ignore[arg-type]
        user,  # type: ignore[arg-type]
        db_session,
        "zh",  # lang(i18n Phase3 刀2 · 直接调用端点函数需显式传)
    )
    assert resp.filled is False
    assert "不在" in resp.detail or "池" in resp.detail


@pytest.mark.asyncio
async def test_ai_order_hk_below_one_lot_rejected(db_session: AsyncSession) -> None:
    """港股 AI 一键:notional 50000 不足 1 手(高价股 600 × 100 = 60000)→ 拒单(不裸下单)。"""
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="hk")
    await db_session.commit()
    ch = _FakeCH([_bar(600.0)])  # 50000 / 600 ≈ 83 股 < 1 手(100)→ floor = 0 → 拒

    resp = await place_ai_order(
        AiOrderRequest(symbol="00700", market="hk", direction="buy"),
        ch,  # type: ignore[arg-type]
        user,  # type: ignore[arg-type]
        db_session,
        "zh",  # lang(i18n Phase3 刀2 · 直接调用端点函数需显式传)
    )
    assert resp.filled is False
    assert "一手" in resp.detail or "不足" in resp.detail


@pytest.mark.asyncio
async def test_ai_order_invalid_direction_for_market(db_session: AsyncSession) -> None:
    """加密不支持现货 buy(走合约 open_long)· 端点 400。"""
    user = await make_user(db_session)
    await db_session.commit()
    with pytest.raises(HTTPException) as exc:
        await place_ai_order(
            AiOrderRequest(symbol="BTC/USDT", market="crypto", direction="buy"),
            _FakeCH(),  # type: ignore[arg-type]
            user,  # type: ignore[arg-type]
            db_session,
            "zh",  # lang(i18n Phase3 刀2)
        )
    assert exc.value.status_code == 400
