"""AI 一键下单无通知修复单测 · execute notify_user 透传 + perp 补 emit(零真实 DB/CH · 本地可跑)。

根因(真机实证):ai-order 复用 bot 的 execute,spot 被 notify=False 连带抑制、perp 路径无 emit
挂点 → 成交零通知。修法:execute 加 notify_user(默认 False = bot #296 去重零回归;
ai-order 传 True 恢复推送)。
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

import app.services.bot.order as order_mod
from app.models.virtual import OrderStatus
from app.services.bot.order import OrderIntent, execute


class _FakeDB:
    """execute 路径只用到 commit/scalar/get(查 account/preset)· 全返 None 走默认/无富回执分支。"""

    async def commit(self) -> None:
        return None

    async def scalar(self, *_a: Any, **_k: Any) -> None:
        return None

    async def get(self, *_a: Any, **_k: Any) -> None:
        return None


def _filled_order(order_id: int = 7) -> SimpleNamespace:
    return SimpleNamespace(
        id=order_id, status=OrderStatus.FILLED,
        symbol="BTCUSDT", quantity=Decimal("1"), price=Decimal("100"),
        account_id=999_999, position_id=None, source="", reject_reason=None,
    )


def _patch_perp(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """mock perp 开仓路径(route_open_perp 返回成交单)+ emit 计数。"""
    calls = {"emit": 0}

    async def fake_open(*_a: Any, **_k: Any) -> SimpleNamespace:
        return _filled_order()

    def fake_emit(order_id: int) -> None:
        assert order_id == 7
        calls["emit"] += 1

    monkeypatch.setattr(order_mod, "route_open_perp", fake_open)
    monkeypatch.setattr(order_mod, "emit_perp_order", fake_emit)
    return calls


@pytest.mark.asyncio
async def test_perp_notify_user_true_emits(monkeypatch: pytest.MonkeyPatch) -> None:
    """ai-order 路径(notify_user=True):perp 成交后补 emit_perp_order。"""
    calls = _patch_perp(monkeypatch)
    intent = OrderIntent(market="crypto", symbol="BTCUSDT",
                         direction="open_long", source="ai_signal")
    result = await execute(_FakeDB(), object(), uuid4(), intent, notify_user=True)
    assert result.filled is True
    assert calls["emit"] == 1


@pytest.mark.asyncio
async def test_perp_default_keeps_bot_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    """bot 路径(默认不传 = False):#296 去重保持,不 emit(不会一笔单双通知)。"""
    calls = _patch_perp(monkeypatch)
    intent = OrderIntent(market="crypto", symbol="BTCUSDT",
                         direction="open_long", source="bot")
    result = await execute(_FakeDB(), object(), uuid4(), intent)  # 不传 notify_user
    assert result.filled is True
    assert calls["emit"] == 0


def _patch_spot(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """mock spot 路径(数量解析 + 撮合)· 捕获 PlaceOrderRequest 断言 notify 透传。"""
    captured: dict[str, Any] = {}

    async def fake_resolve(*_a: Any, **_k: Any) -> tuple[Any, Any, Decimal]:
        from app.models.virtual import OrderSide, PositionSide

        return OrderSide.BUY, PositionSide.LONG, Decimal("1")

    async def fake_place(_db: Any, req: Any, _fetcher: Any) -> SimpleNamespace:
        captured["notify"] = req.notify
        return _filled_order(8)

    monkeypatch.setattr(order_mod, "_resolve_spot_order", fake_resolve)
    monkeypatch.setattr(order_mod, "place_market_order", fake_place)
    return captured


@pytest.mark.asyncio
async def test_spot_notify_user_threads_to_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """ai-order 路径:spot 的 PlaceOrderRequest.notify=True(engine 内走 emit_trade_filled)。"""
    captured = _patch_spot(monkeypatch)
    intent = OrderIntent(market="us", symbol="NVDA", direction="buy", source="ai_signal")
    result = await execute(_FakeDB(), object(), uuid4(), intent, notify_user=True)
    assert result.filled is True
    assert captured["notify"] is True


@pytest.mark.asyncio
async def test_spot_default_keeps_notify_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """bot 路径(默认):spot notify=False 原样(#296 去重零回归)。"""
    captured = _patch_spot(monkeypatch)
    intent = OrderIntent(market="us", symbol="NVDA", direction="buy", source="bot")
    result = await execute(_FakeDB(), object(), uuid4(), intent)
    assert result.filled is True
    assert captured["notify"] is False
