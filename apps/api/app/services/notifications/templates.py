"""消息模板渲染 · 0009 § 5 → 0025 G2a(移除飞书 · 仅 Telegram)。

Telegram Markdown 渲染(属 Telegram 适配层的「渲染」部分)。
所有模板必带「点金 Midas」字样 + 「不构成投资建议」尾。
成交通知不用绿色;价格异动用 🔴/🟢 emoji 标方向(不依赖颜色)。
"""

from __future__ import annotations

from decimal import Decimal

from app.core.formatting import format_price_number
from app.services.notifications.events import (
    AlertTriggeredEvent,
    LiquidationEvent,
    NotificationEvent,
    PerpFilledEvent,
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
    """金额类(盈亏 / 手续费 / 余额)· 全币种固定 2 位 · 不走动态(价格才走 _fmt_price)。

    产品定调:USDT 也统一 2 位(虚拟交易、手续费象征性,接受极小值显示 0.00)。
    """
    formatted = f"{amount:,.2f}"
    if currency == "USDT":
        return f"{formatted} USDT"
    return f"{CURRENCY_SYMBOL.get(currency, currency)}{formatted}"


def _fmt_price(amount: Decimal, currency: str) -> str:
    """价格类(成交价 / 强平价 / 现价 / 名义)· 动态精度 + <1 去尾零(单一事实源 format_price_number)。

    ★ 只换「数字串」,币种符号 / 千分位包装与 _fmt_money 一致 → 非价格行字节不变。
    """
    formatted = format_price_number(float(amount))
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
    if isinstance(event, PerpFilledEvent):
        return _tg_perp_filled(event)
    if isinstance(event, LiquidationEvent):
        return _tg_liquidation(event)
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
        f"{_fmt_price(event.price, event.currency)}\n"
        f"手续费 {_fmt_money(event.commission, event.currency)}"
        f"{pnl_line}\n\n"
        f"_{DISCLAIMER}_"
    )


# ===== 永续合约(#296)=====

PERP_ACTION_LABEL: dict[str, str] = {
    "open_long": "开多",
    "open_short": "开空",
    "close_long": "平多",
    "close_short": "平空",
}
MARGIN_MODE_LABEL: dict[str, str] = {"isolated": "逐仓", "cross": "全仓"}
PERP_SIDE_LABEL: dict[str, str] = {"long": "多头", "short": "空头"}


def _fmt_signed_money(amount: Decimal, currency: str) -> str:
    """带显式 +/- 号的金额(盈亏用 · 方向一眼可辨,不依赖颜色)。"""
    sign = "+" if amount >= 0 else "-"
    return f"{sign}{_fmt_money(abs(amount), currency)}"


def _tg_perp_filled(event: PerpFilledEvent) -> str:
    action = PERP_ACTION_LABEL.get(event.action, event.action)
    mode = MARGIN_MODE_LABEL.get(event.margin_mode, event.margin_mode)
    lev = f" {event.leverage}x" if event.leverage else ""
    pnl_line = ""
    if event.realized_pnl is not None:
        pnl_line = f"\n已实现盈亏 {_fmt_signed_money(event.realized_pnl, event.currency)}"
    return (
        "*点金 Midas · 合约成交*\n\n"
        f"📊 {event.symbol} · 永续 · {mode}{lev}\n"
        f"{action} {event.quantity} · 成交价 "
        f"{_fmt_price(event.price, event.currency)}\n"
        f"名义 {_fmt_price(event.notional, event.currency)} · "
        f"手续费 {_fmt_money(event.fee, event.currency)}"
        f"{pnl_line}\n\n"
        f"_{DISCLAIMER}_"
    )


def _tg_liquidation(event: LiquidationEvent) -> str:
    if event.is_cross:
        floored_line = "\n该账户已穿仓(净亏已封顶)" if event.floored else ""
        remaining = (
            f"\n剩余可用 {_fmt_money(event.remaining_cash, event.currency)}"
            if event.remaining_cash is not None
            else ""
        )
        return (
            "*点金 Midas · 全仓强制平仓*\n\n"
            "⚠️ 全仓合约账户触发强平\n"
            f"{event.position_count} 个仓位已全部强制平仓"
            f"{remaining}{floored_line}\n\n"
            f"_{DISCLAIMER}_"
        )
    # 逐仓单仓
    side = PERP_SIDE_LABEL.get(event.side or "", event.side or "")
    lev = f" {event.leverage}x" if event.leverage else ""
    liq = (
        f"触及强平价 {_fmt_price(event.liquidation_price, event.currency)} · "
        if event.liquidation_price is not None
        else ""
    )
    pnl_line = ""
    if event.realized_pnl is not None:
        pnl_line = f"\n已实现盈亏 {_fmt_signed_money(event.realized_pnl, event.currency)}"
    return (
        "*点金 Midas · 强制平仓*\n\n"
        f"⚠️ {event.symbol} · 永续 · 逐仓{lev}\n"
        f"{side}{liq}已强制平仓"
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
        f"现价 {_fmt_price(event.current_price, event.currency)} · "
        f"参考 {_fmt_price(event.reference_price, event.currency)}\n\n"
        f"_{DISCLAIMER}_"
    )


def render_telegram_test() -> str:
    return (
        "*点金 Midas · 测试消息*\n\n"
        "✓ Telegram 推送已连通\n\n"
        "之后你的成交通知和价格异动会推到这里。\n\n"
        f"_{DISCLAIMER}_"
    )
