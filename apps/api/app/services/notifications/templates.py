"""消息模板渲染 · 0009 § 5 → 0025 G2a(移除飞书 · 仅 Telegram)。

Telegram Markdown 渲染(属 Telegram 适配层的「渲染」部分)。
所有模板必带「点金 Midas」字样 + 「不构成投资建议」尾。
成交通知不用绿色;价格异动用 🔴/🟢 emoji 标方向(不依赖颜色)。
"""

from __future__ import annotations

from decimal import Decimal

from app.services.notifications.events import (
    AlertTriggeredEvent,
    NotificationEvent,
    PriceAnomalyEvent,
    TradeFilledEvent,
)

MARKET_LABEL: dict[str, str] = {"cn": "A 股", "us": "美股", "crypto": "加密"}
CURRENCY_SYMBOL: dict[str, str] = {"CNY": "¥", "USD": "$", "USDT": "USDT"}

DISCLAIMER = "本次为模拟交易,不构成投资建议"
# 告警类不是交易,用「仅供参考」免责(红线:bot 文案必带免责)
ALERT_DISCLAIMER = "仅供参考,不构成投资建议"
_OP_SYMBOL: dict[str, str] = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤"}


def _fmt_money(amount: Decimal, currency: str) -> str:
    decimals = 4 if currency == "USDT" else 2
    formatted = f"{amount:,.{decimals}f}"
    if currency == "USDT":
        return f"{formatted} USDT"
    return f"{CURRENCY_SYMBOL.get(currency, currency)}{formatted}"


def _fmt_pct(pct: Decimal) -> str:
    sign = "+" if pct >= 0 else ""
    return f"{sign}{float(pct):.2f}%"


# ===== Telegram markdown =====


def render_telegram(event: NotificationEvent) -> str:
    """渲染 TG Markdown 文本。"""
    if isinstance(event, TradeFilledEvent):
        return _tg_trade_filled(event)
    if isinstance(event, PriceAnomalyEvent):
        return _tg_price_anomaly(event)
    if isinstance(event, AlertTriggeredEvent):
        return _tg_alert_triggered(event)
    msg = f"未知事件类型 {type(event)}"
    raise ValueError(msg)


def _fmt_num(n: float) -> str:
    """紧凑数值:整数去小数,否则保留 2 位(去尾零)。"""
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.2f}".rstrip("0").rstrip(".")


def _tg_alert_triggered(event: AlertTriggeredEvent) -> str:
    target = event.symbol or MARKET_LABEL.get(event.market, event.market)
    unit = event.unit or ""
    op = _OP_SYMBOL.get(event.operator, event.operator)
    return (
        "*点金 Midas · 告警触发*\n\n"
        f"🔔 {target} · {MARKET_LABEL.get(event.market, event.market)}\n"
        f"{event.indicator_label}  {op} {_fmt_num(event.threshold)}{unit}\n"
        f"当前 {_fmt_num(event.value)}{unit}\n\n"
        f"_{ALERT_DISCLAIMER}_"
    )


def _tg_trade_filled(event: TradeFilledEvent) -> str:
    side_label = "买入" if event.side == "buy" else "卖出"
    pnl_line = ""
    if event.realized_pnl is not None and event.side == "sell":
        pnl_line = (
            f"\n已实现盈亏 · {_fmt_money(event.realized_pnl, event.currency)}"
        )
    return (
        "*点金 Midas · 成交通知*\n\n"
        f"📊 {event.symbol} · {MARKET_LABEL.get(event.market, event.market)}\n"
        f"{side_label} {event.quantity} · 成交价 "
        f"{_fmt_money(event.price, event.currency)}\n"
        f"手续费 {_fmt_money(event.commission, event.currency)}"
        f"{pnl_line}\n\n"
        f"_{DISCLAIMER}_"
    )


def _tg_price_anomaly(event: PriceAnomalyEvent) -> str:
    is_up = event.change_pct >= 0
    icon = "🔴" if is_up else "🟢"  # M0 用 emoji,不依赖颜色
    direction = "异动 ↑" if is_up else "异动 ↓"
    return (
        "*点金 Midas · 价格异动*\n\n"
        f"{icon} {event.symbol} · {MARKET_LABEL.get(event.market, event.market)}\n"
        f"{direction} {_fmt_pct(event.change_pct)}\n"
        f"现价 {_fmt_money(event.current_price, event.currency)} · "
        f"参考 {_fmt_money(event.reference_price, event.currency)}\n\n"
        f"_{DISCLAIMER}_"
    )


def render_telegram_test() -> str:
    return (
        "*点金 Midas · 测试消息*\n\n"
        "✓ Telegram 推送已连通\n\n"
        "之后你的成交通知和价格异动会推到这里。\n\n"
        f"_{DISCLAIMER}_"
    )
