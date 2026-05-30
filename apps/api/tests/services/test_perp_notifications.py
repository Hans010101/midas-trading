"""#296 · 永续成交 + 强平 通知 单测。

覆盖:模板渲染(perp 成交开/平 + 强平逐仓/全仓)、DISCLAIMER 红线、quiet_exempt 豁免、
dispatcher 新 kind 受 trade_alert_enabled 控制、纯 builder 字段映射、emit helper(mock broker)。
全部纯函数 / mock · 不打 DB / 网络。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.models.perp import PerpAction, PerpSide
from app.models.virtual import Currency
from app.services.notifications import emit
from app.services.notifications.dispatcher import _kind_enabled
from app.services.notifications.events import (
    LiquidationEvent,
    NotificationKind,
    PerpFilledEvent,
)
from app.services.notifications.perp_events import (
    build_liquidation_event_single,
    build_perp_filled_event,
)
from app.services.notifications.templates import DISCLAIMER, render_telegram

# ===== 模板渲染 =====


def test_perp_filled_open_template() -> None:
    text = render_telegram(
        PerpFilledEvent(
            symbol="BTCUSDT", action="open_long", margin_mode="isolated",
            leverage=20, quantity=Decimal("0.5"), price=Decimal("63200"),
            notional=Decimal("31600"), fee=Decimal("25.28"),
            realized_pnl=None, currency="USDT",
        ),
    )
    assert "合约成交" in text
    assert "BTCUSDT" in text
    assert "逐仓 20x" in text
    assert "开多" in text
    assert "已实现盈亏" not in text  # 开仓不显示盈亏
    assert "成交价 63,200 USDT" in text  # 价格动态精度:63200 → 0 位
    assert "手续费 25.28 USDT" in text  # 🔴 USDT 手续费固定 2 位(收尾调整 · 旧为 4 位)
    assert DISCLAIMER in text


def test_perp_filled_close_template_shows_pnl() -> None:
    text = render_telegram(
        PerpFilledEvent(
            symbol="ETHUSDT", action="close_long", margin_mode="cross",
            leverage=10, quantity=Decimal("2"), price=Decimal("3200"),
            notional=Decimal("6400"), fee=Decimal("3.2"),
            realized_pnl=Decimal("374.72"), currency="USDT",
        ),
    )
    assert "平多" in text
    assert "全仓 10x" in text
    assert "已实现盈亏 +374.72 USDT" in text  # 🔴 USDT 盈亏固定 2 位(收尾调整)· 盈利带 + 号
    assert "手续费 3.20 USDT" in text  # USDT 手续费 2 位(3.2 → 3.20)
    assert DISCLAIMER in text


def test_liquidation_isolated_template() -> None:
    text = render_telegram(
        LiquidationEvent(
            is_cross=False, symbol="BTCUSDT", side="long", leverage=20,
            liquidation_price=Decimal("60100"), realized_pnl=Decimal("-1580"),
            position_count=1, currency="USDT",
        ),
    )
    assert "强制平仓" in text
    assert "BTCUSDT" in text
    assert "多头" in text
    assert "强平价 60,100 USDT" in text  # 价格动态精度:60100 → 0 位
    assert "已实现盈亏 -1,580.00 USDT" in text  # 🔴 USDT 盈亏固定 2 位(收尾调整)· 亏损带 - 号
    assert DISCLAIMER in text


def test_liquidation_cross_template() -> None:
    text = render_telegram(
        LiquidationEvent(
            is_cross=True, position_count=3, remaining_cash=Decimal("0"),
            floored=True, currency="USDT",
        ),
    )
    assert "全仓强制平仓" in text
    assert "3 个仓位" in text
    assert "剩余可用" in text
    assert "穿仓" in text  # floored=True
    assert DISCLAIMER in text


# ===== quiet_exempt 豁免(钱相关 · 安静时段照发)=====


def test_perp_events_are_quiet_exempt() -> None:
    assert PerpFilledEvent.quiet_exempt is True
    assert LiquidationEvent.quiet_exempt is True


# ===== dispatcher · 新 kind 受现有 trade_alert_enabled 控制 =====


@pytest.mark.parametrize("kind", [NotificationKind.PERP_FILLED, NotificationKind.LIQUIDATION])
def test_new_kinds_gated_by_trade_alert(kind: NotificationKind) -> None:
    event = SimpleNamespace(kind=kind)
    on = SimpleNamespace(trade_alert_enabled=True, price_alert_enabled=False)
    off = SimpleNamespace(trade_alert_enabled=False, price_alert_enabled=True)
    assert _kind_enabled(event, on) is True   # type: ignore[arg-type]
    assert _kind_enabled(event, off) is False  # type: ignore[arg-type]


# ===== 纯 builder · 字段映射 =====


def _account() -> SimpleNamespace:
    return SimpleNamespace(currency=Currency.USDT, user_id="u-1")


def test_build_perp_filled_open_uses_order_leverage_no_pnl() -> None:
    order = SimpleNamespace(
        symbol="BTCUSDT", action=PerpAction.OPEN_LONG, leverage=20,
        quantity=Decimal("0.5"), price=Decimal("63200"),
        notional=Decimal("31600"), fee=Decimal("25.28"), realized_pnl=None,
    )
    position = SimpleNamespace(margin_mode="isolated", leverage=20, side=PerpSide.LONG)
    ev = build_perp_filled_event(order, position, _account())  # type: ignore[arg-type]
    assert ev.action == "open_long"
    assert ev.leverage == 20
    assert ev.margin_mode == "isolated"
    assert ev.realized_pnl is None  # 开仓不带盈亏
    assert ev.currency == "USDT"


def test_build_perp_filled_close_falls_back_to_position_leverage_with_pnl() -> None:
    # 平仓单 leverage=None → 回落 position.leverage;realized_pnl 透传
    order = SimpleNamespace(
        symbol="ETHUSDT", action=PerpAction.CLOSE_LONG, leverage=None,
        quantity=Decimal("2"), price=Decimal("3200"),
        notional=Decimal("6400"), fee=Decimal("3.2"), realized_pnl=Decimal("374.72"),
    )
    position = SimpleNamespace(margin_mode="cross", leverage=10, side=PerpSide.LONG)
    ev = build_perp_filled_event(order, position, _account())  # type: ignore[arg-type]
    assert ev.leverage == 10  # 回落 position
    assert ev.margin_mode == "cross"
    assert ev.realized_pnl == Decimal("374.72")


def test_build_liquidation_single() -> None:
    order = SimpleNamespace(
        symbol="BTCUSDT", action=PerpAction.CLOSE_LONG, realized_pnl=Decimal("-1580"),
    )
    position = SimpleNamespace(
        side=PerpSide.LONG, leverage=20, liquidation_price=Decimal("60100"),
    )
    ev = build_liquidation_event_single(order, position, _account())  # type: ignore[arg-type]
    assert ev.is_cross is False
    assert ev.symbol == "BTCUSDT"
    assert ev.side == "long"
    assert ev.leverage == 20
    assert ev.liquidation_price == Decimal("60100")
    assert ev.realized_pnl == Decimal("-1580")
    assert ev.position_count == 1


# ===== emit helper(mock broker · 旁路不抛)=====


def test_emit_perp_order_sends_task() -> None:
    emit._celery_client = None  # noqa: SLF001
    with patch.object(emit, "_get_celery_client") as getter:
        client = getter.return_value
        emit.emit_perp_order(77)
        client.send_task.assert_called_once_with(
            "tasks.notifications.send_perp_order_notification", args=[77],
        )


def test_emit_cross_liquidation_sends_task() -> None:
    emit._celery_client = None  # noqa: SLF001
    with patch.object(emit, "_get_celery_client") as getter:
        client = getter.return_value
        emit.emit_cross_liquidation(5, 3, floored=True, remaining_cash=Decimal("0"))
        client.send_task.assert_called_once_with(
            "tasks.notifications.send_cross_liquidation_notification",
            args=[5, 3, True, "0"],
        )


def test_emit_perp_order_broker_down_does_not_raise() -> None:
    emit._celery_client = None  # noqa: SLF001

    def boom() -> None:
        raise ConnectionError("broker unreachable")

    with patch.object(emit, "_get_celery_client", side_effect=boom):
        emit.emit_perp_order(1)  # 不抛
        emit.emit_cross_liquidation(1, 1, floored=False, remaining_cash="0")  # 不抛
