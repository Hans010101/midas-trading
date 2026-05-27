"""Telegram 适配层 · inline 键盘 + 消息渲染(纯函数)· 0025 M1-G G3。

只把核心层的结构化结果(SymbolQuote / WatchlistRow / PositionRow)渲染成 Telegram
Markdown + inline_keyboard。无 IO、无 DB —— 便于单测。

🔴 红线:每条消息尾部必带「仅供参考,不构成投资建议」;K 线走网页深链(DP14),不在
bot 里画图;下单 / 告警规则配置本期是占位(分别 G4 / G5)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from app.services.bot.query import PositionRow, SymbolQuote, WatchlistRow

DISCLAIMER = "仅供参考,不构成投资建议"
_BRAND = "点金 Midas"
_MARKET_LABEL: dict[str, str] = {"cn": "A股", "us": "美股", "crypto": "加密"}
_CCY_SYMBOL: dict[str, str] = {"CNY": "¥", "USD": "$", "USDT": ""}
# 市场 → 网页个股详情页路径(DP14 深链 · 完整 K 线在网页看)
_PREVIEW_PATH: dict[str, str] = {
    "cn": "cn-preview", "us": "us-preview", "crypto": "crypto-preview",
}

Keyboard = dict[str, list[list[dict[str, str]]]]


@dataclass(frozen=True)
class BotReply:
    """一次 bot 响应 · text(Markdown)+ 可选 inline 键盘。"""

    text: str
    keyboard: Keyboard | None = None


# ── 数值格式化 ────────────────────────────────────────────────────────


def _fmt_price(v: float, currency: str) -> str:
    sym = _CCY_SYMBOL.get(currency, "")
    decimals = 4 if currency == "USDT" else 2
    body = f"{v:,.{decimals}f}"
    return f"{sym}{body}" if sym else f"{body} {currency}".strip()


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    icon = "🔴" if v >= 0 else "🟢"  # CN 习惯:涨红跌绿 · emoji 不依赖颜色
    sign = "+" if v >= 0 else ""
    return f"{icon} {sign}{v:.2f}%"


def _fmt_compact_usd(v: float) -> str:
    """大额 USD 紧凑:1.23B / 45.6M / 789K。"""
    a = abs(v)
    if a >= 1e9:
        return f"${v / 1e9:.2f}B"
    if a >= 1e6:  # noqa: PLR2004
        return f"${v / 1e6:.2f}M"
    if a >= 1e3:  # noqa: PLR2004
        return f"${v / 1e3:.2f}K"
    return f"${v:.2f}"


def _fmt_qty(v: float) -> str:
    if v == int(v):
        return f"{int(v):,}"
    return f"{v:,.8f}".rstrip("0").rstrip(".")


def web_chart_url(market: str, symbol: str) -> str:
    """拼网页 K 线深链(DP14)· crypto 用 Binance 风格无斜杠。"""
    base = settings.public_web_base_url.rstrip("/")
    path = _PREVIEW_PATH.get(market, "workbench")
    sym = symbol.replace("/", "") if market == "crypto" else symbol
    return f"{base}/{path}?symbol={sym}"


def _tail(text: str) -> str:
    """统一加品牌头部已在各 render 处理;这里只补免责尾。"""
    return f"{text}\n\n_{DISCLAIMER}_"


# ── inline 键盘 ───────────────────────────────────────────────────────


def main_menu_keyboard() -> Keyboard:
    return {
        "inline_keyboard": [
            [
                {"text": "📊 行情查询", "callback_data": "menu:quote"},
                {"text": "📈 K线图", "callback_data": "menu:kline"},
            ],
            [
                {"text": "⭐ 我的自选", "callback_data": "act:watchlist"},
                {"text": "💼 我的持仓", "callback_data": "act:positions"},
            ],
            [
                {"text": "🛒 下单(下一期)", "callback_data": "stub:order"},
                {"text": "🔔 告警规则", "callback_data": "stub:rules"},
            ],
        ],
    }


def _market_picker_keyboard(intent: str) -> Keyboard:
    """intent = quote / kline · 选完市场后等用户输代码。"""
    return {
        "inline_keyboard": [
            [
                {"text": "A股", "callback_data": f"ask:{intent}:cn"},
                {"text": "美股", "callback_data": f"ask:{intent}:us"},
                {"text": "加密", "callback_data": f"ask:{intent}:crypto"},
            ],
            [{"text": "⬅️ 返回菜单", "callback_data": "menu:main"}],
        ],
    }


def _back_keyboard() -> Keyboard:
    return {"inline_keyboard": [[{"text": "⬅️ 返回菜单", "callback_data": "menu:main"}]]}


def _quote_keyboard(market: str, symbol: str) -> Keyboard:
    return {
        "inline_keyboard": [
            [{"text": "📈 网页看K线", "url": web_chart_url(market, symbol)}],
            [{"text": "⬅️ 返回菜单", "callback_data": "menu:main"}],
        ],
    }


# ── 渲染 ─────────────────────────────────────────────────────────────


def render_main_menu() -> BotReply:
    text = (
        f"*{_BRAND} · 迷你终端*\n\n"
        "选择功能 ↓\n"
        "· 📊 行情查询 / 📈 K线图(网页)\n"
        "· ⭐ 自选 / 💼 持仓\n\n"
        "也可直接发送 `/price <代码>` 查行情"
    )
    return BotReply(_tail(text), main_menu_keyboard())


def render_market_picker(intent: str) -> BotReply:
    what = "查行情" if intent == "quote" else "看K线"
    return BotReply(
        _tail(f"*{_BRAND}*\n\n{what} —— 先选市场:"),
        _market_picker_keyboard(intent),
    )


def render_ask_symbol(intent: str, market: str) -> BotReply:
    examples = {"cn": "600519", "us": "NVDA", "crypto": "BTC/USDT"}
    what = "查行情" if intent == "quote" else "看K线"
    mlabel = _MARKET_LABEL.get(market, market)
    text = (
        f"*{_BRAND}*\n\n"
        f"{mlabel} · {what}\n"
        f"请发送代码,例如 `{examples.get(market, 'BTC/USDT')}`"
    )
    return BotReply(_tail(text), _back_keyboard())


def render_quote(quote: SymbolQuote) -> BotReply:
    mlabel = _MARKET_LABEL.get(quote.market, quote.market)
    lines = [
        f"*{_BRAND} · 行情*",
        "",
        f"📊 {quote.symbol} · {mlabel}",
    ]
    if quote.price is not None:
        lines.append(f"最新价 {_fmt_price(quote.price, quote.currency)}")
    lines.append(f"涨跌幅 {_fmt_pct(quote.change_pct)}")
    if quote.volume is not None:
        lines.append(f"成交量 {_fmt_qty(quote.volume)}")
    # crypto 衍生(有才显示)
    if quote.funding_rate is not None:
        lines.append(f"资金费率 {quote.funding_rate * 100:+.4f}%")
    if quote.open_interest_usd is not None:
        lines.append(f"未平仓额 {_fmt_compact_usd(quote.open_interest_usd)}")
    if quote.long_short_ratio is not None:
        lines.append(f"多空比(大户) {quote.long_short_ratio:.2f}")
    if quote.basis_pct is not None:
        lines.append(f"基差 {quote.basis_pct:+.3f}%")
    return BotReply(_tail("\n".join(lines)), _quote_keyboard(quote.market, quote.symbol))


def render_symbol_not_found(market: str, symbol: str) -> BotReply:
    mlabel = _MARKET_LABEL.get(market, market)
    text = (
        f"*{_BRAND}*\n\n"
        f"未找到 {symbol}({mlabel})的数据。\n"
        "请确认代码,或换一个再试(只查已采集标的)。"
    )
    return BotReply(_tail(text), _back_keyboard())


def render_kline_link(market: str, symbol: str) -> BotReply:
    mlabel = _MARKET_LABEL.get(market, market)
    text = (
        f"*{_BRAND} · K线*\n\n"
        f"📈 {symbol} · {mlabel}\n"
        "点下方按钮在网页打开完整 K 线图(含缠论 / 指标)。"
    )
    return BotReply(_tail(text), _quote_keyboard(market, symbol))


def render_watchlist(rows: list[WatchlistRow]) -> BotReply:
    if not rows:
        text = (
            f"*{_BRAND} · 自选*\n\n"
            "你还没有自选标的。\n在网页端工作台用 Cmd/Ctrl+K 添加。"
        )
        return BotReply(_tail(text), _back_keyboard())
    lines = [f"*{_BRAND} · 自选*", ""]
    for r in rows:
        mlabel = _MARKET_LABEL.get(r.market, r.market)
        price = "—" if r.price is None else _fmt_price(r.price, _market_ccy(r.market))
        lines.append(f"{r.symbol} · {mlabel}  {price}  {_fmt_pct(r.change_pct)}")
    return BotReply(_tail("\n".join(lines)), _back_keyboard())


def render_positions(rows: list[PositionRow]) -> BotReply:
    if not rows:
        text = (
            f"*{_BRAND} · 持仓*\n\n"
            "当前没有活仓。\n所有交易均为 VIRTUAL · 模拟。"
        )
        return BotReply(_tail(text), _back_keyboard())
    lines = [f"*{_BRAND} · 持仓* (VIRTUAL · 模拟)", ""]
    for r in rows:
        mlabel = _MARKET_LABEL.get(r.market, r.market)
        side_cn = "多" if r.side == "long" else "空"
        tag = f"永续{r.leverage}x" if r.kind == "perp" else mlabel
        entry = _fmt_price(r.avg_entry_price, r.currency)
        lines.append(
            f"{r.symbol} · {tag} · {side_cn}  {_fmt_qty(r.quantity)} @ {entry}",
        )
    return BotReply(_tail("\n".join(lines)), _back_keyboard())


def render_order_stub() -> BotReply:
    text = (
        f"*{_BRAND} · 下单*\n\n"
        "🛒 bot 内虚拟下单将在下一期(G4)开放。\n"
        "目前可在网页端工作台下单(全程 VIRTUAL · 模拟)。"
    )
    return BotReply(_tail(text), _back_keyboard())


def render_rules_stub() -> BotReply:
    text = (
        f"*{_BRAND} · 告警规则*\n\n"
        "🔔 请在网页端【设置 → 消息推送】配置告警规则。\n"
        "(bot 内规则配置后续上线)"
    )
    return BotReply(_tail(text), _back_keyboard())


def render_not_bound() -> BotReply:
    text = (
        f"*{_BRAND}*\n\n"
        "你的 Telegram 还没绑定 Midas 账号。\n"
        "请到网页端【设置 → 消息推送】点「绑定 Telegram」,按提示完成绑定后再用。"
    )
    return BotReply(_tail(text), None)


def render_hint() -> BotReply:
    text = (
        f"*{_BRAND}*\n\n"
        "发送 /menu 打开功能菜单,或 `/price <代码>` 直接查行情。"
    )
    return BotReply(_tail(text), main_menu_keyboard())


def _market_ccy(market: str) -> str:
    return {"cn": "CNY", "us": "USD", "crypto": "USDT"}.get(market, "USD")
