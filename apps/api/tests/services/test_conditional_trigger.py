"""should_trigger 触发矩阵单测(ADR 0041 刀2)· 6 条矩阵 × 命中/不命中/恰好等于 = 18 例。

锁死刀1 模型 docstring 矩阵 · 全含等号(到价即触发)· 纯函数零依赖本地可跑。
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.conditional_order import ConditionalKind
from app.models.virtual import OrderSide, PositionSide
from app.services.virtual_trading.conditional_trigger import should_trigger

T = Decimal("100")  # trigger_price 基准

# (kind, side, position_side, price, expected)
_CASES = [
    # ── LIMIT + BUY:P ≤ T 触发(低吸)──
    (ConditionalKind.LIMIT, OrderSide.BUY, PositionSide.LONG, Decimal("99"), True),
    (ConditionalKind.LIMIT, OrderSide.BUY, PositionSide.LONG, Decimal("101"), False),
    (ConditionalKind.LIMIT, OrderSide.BUY, PositionSide.LONG, T, True),  # 等号边界
    # ── LIMIT + SELL:P ≥ T 触发(高抛)──
    (ConditionalKind.LIMIT, OrderSide.SELL, PositionSide.LONG, Decimal("101"), True),
    (ConditionalKind.LIMIT, OrderSide.SELL, PositionSide.LONG, Decimal("99"), False),
    (ConditionalKind.LIMIT, OrderSide.SELL, PositionSide.LONG, T, True),
    # ── STOP_LOSS 平多(LONG):P ≤ T 触发(跌破止损)──
    (ConditionalKind.STOP_LOSS, OrderSide.SELL, PositionSide.LONG, Decimal("99"), True),
    (ConditionalKind.STOP_LOSS, OrderSide.SELL, PositionSide.LONG, Decimal("101"), False),
    (ConditionalKind.STOP_LOSS, OrderSide.SELL, PositionSide.LONG, T, True),
    # ── STOP_LOSS 平空(SHORT):P ≥ T 触发(涨破止损)──
    (ConditionalKind.STOP_LOSS, OrderSide.BUY, PositionSide.SHORT, Decimal("101"), True),
    (ConditionalKind.STOP_LOSS, OrderSide.BUY, PositionSide.SHORT, Decimal("99"), False),
    (ConditionalKind.STOP_LOSS, OrderSide.BUY, PositionSide.SHORT, T, True),
    # ── TAKE_PROFIT 平多:P ≥ T 触发(到价止盈)──
    (ConditionalKind.TAKE_PROFIT, OrderSide.SELL, PositionSide.LONG, Decimal("101"), True),
    (ConditionalKind.TAKE_PROFIT, OrderSide.SELL, PositionSide.LONG, Decimal("99"), False),
    (ConditionalKind.TAKE_PROFIT, OrderSide.SELL, PositionSide.LONG, T, True),
    # ── TAKE_PROFIT 平空:P ≤ T 触发 ──
    (ConditionalKind.TAKE_PROFIT, OrderSide.BUY, PositionSide.SHORT, Decimal("99"), True),
    (ConditionalKind.TAKE_PROFIT, OrderSide.BUY, PositionSide.SHORT, Decimal("101"), False),
    (ConditionalKind.TAKE_PROFIT, OrderSide.BUY, PositionSide.SHORT, T, True),
]


@pytest.mark.parametrize(("kind", "side", "pside", "price", "expected"), _CASES)
def test_trigger_matrix(
    kind: ConditionalKind, side: OrderSide, pside: PositionSide,
    price: Decimal, expected: bool,
) -> None:
    assert should_trigger(kind, side, pside, T, price) is expected
