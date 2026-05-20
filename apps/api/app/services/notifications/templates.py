"""消息模板渲染 · 0009 § 5。

每个通道(feishu / telegram)各有一份渲染函数。
所有模板必带「点金 Midas」字样(同时满足飞书关键词校验)+ 「不构成投资建议」尾。
绝不使用绿色 · 成交色用飞书 wathet(青色)/ TG 无色。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.services.notifications.events import (
    NotificationEvent,
    PriceAnomalyEvent,
    TradeFilledEvent,
)

MARKET_LABEL: dict[str, str] = {"cn": "A 股", "us": "美股", "crypto": "加密"}
CURRENCY_SYMBOL: dict[str, str] = {"CNY": "¥", "USD": "$", "USDT": "USDT"}

DISCLAIMER = "本次为模拟交易,不构成投资建议"


def _fmt_money(amount: Decimal, currency: str) -> str:
    decimals = 4 if currency == "USDT" else 2
    formatted = f"{amount:,.{decimals}f}"
    if currency == "USDT":
        return f"{formatted} USDT"
    return f"{CURRENCY_SYMBOL.get(currency, currency)}{formatted}"


def _fmt_pct(pct: Decimal) -> str:
    sign = "+" if pct >= 0 else ""
    return f"{sign}{float(pct):.2f}%"


# ===== 飞书 interactive card =====


def render_feishu(event: NotificationEvent) -> dict[str, Any]:
    """渲染飞书自定义机器人 interactive card payload。"""
    if isinstance(event, TradeFilledEvent):
        return _feishu_trade_filled(event)
    if isinstance(event, PriceAnomalyEvent):
        return _feishu_price_anomaly(event)
    msg = f"未知事件类型 {type(event)}"
    raise ValueError(msg)


def _feishu_trade_filled(event: TradeFilledEvent) -> dict[str, Any]:
    side_label = "买入" if event.side == "buy" else "卖出"
    pnl_line = ""
    if event.realized_pnl is not None and event.side == "sell":
        pnl_line = (
            f"\n已实现盈亏 · {_fmt_money(event.realized_pnl, event.currency)}"
        )
    body = (
        f"**{event.symbol} · {MARKET_LABEL.get(event.market, event.market)}**\n"
        f"{side_label} {event.quantity} · 成交价 "
        f"{_fmt_money(event.price, event.currency)}\n"
        f"手续费 {_fmt_money(event.commission, event.currency)}"
        f"{pnl_line}"
    )
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "点金 Midas · 成交通知",
                },
                # 0009 § 5:不用绿色,wathet 是飞书 card preset 中最克制的色
                "template": "wathet",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": body}},
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": DISCLAIMER},
                    ],
                },
            ],
        },
    }


def _feishu_price_anomaly(event: PriceAnomalyEvent) -> dict[str, Any]:
    is_up = event.change_pct >= 0
    # 行情色 · 涨用红 / 跌用绿(允许 · 0009 § 5)
    template = "red" if is_up else "green"
    direction = "异动 ↑" if is_up else "异动 ↓"
    body = (
        f"**{event.symbol} · {MARKET_LABEL.get(event.market, event.market)}**\n"
        f"{direction} {_fmt_pct(event.change_pct)}\n"
        f"现价 {_fmt_money(event.current_price, event.currency)} · "
        f"参考价 {_fmt_money(event.reference_price, event.currency)}"
    )
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "点金 Midas · 价格异动",
                },
                "template": template,
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": body}},
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": DISCLAIMER},
                    ],
                },
            ],
        },
    }


def render_feishu_test() -> dict[str, Any]:
    """「发送测试消息」按钮的固定文案 · 验证 webhook 可达。"""
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "点金 Midas · 测试消息",
                },
                "template": "wathet",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            "✓ 飞书机器人配置成功\n\n"
                            "之后你的成交通知和价格异动会推到这里。"
                        ),
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": DISCLAIMER},
                    ],
                },
            ],
        },
    }


# ===== TG markdown =====


def render_telegram(event: NotificationEvent) -> str:
    """渲染 TG Markdown 文本。"""
    if isinstance(event, TradeFilledEvent):
        return _tg_trade_filled(event)
    if isinstance(event, PriceAnomalyEvent):
        return _tg_price_anomaly(event)
    msg = f"未知事件类型 {type(event)}"
    raise ValueError(msg)


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
        "✓ Telegram bot 配置成功\n\n"
        "之后你的成交通知和价格异动会推到这里。\n\n"
        f"_{DISCLAIMER}_"
    )
