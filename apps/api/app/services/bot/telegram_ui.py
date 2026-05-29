"""Telegram 适配层 · inline 键盘 + 消息渲染(纯函数)· 0025 M1-G G3。

只把核心层的结构化结果(SymbolQuote / WatchlistRow / PositionRow)渲染成 Telegram
Markdown + inline_keyboard。无 IO、无 DB —— 便于单测。

🔴 红线:每条消息尾部必带「仅供参考,不构成投资建议」;K 线走网页深链(DP14),不在
bot 里画图;下单(G4)全程 VIRTUAL·模拟 + 必经二次确认;告警规则配置占位(G5)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.config import settings
from app.services.bot import order as order_mod

if TYPE_CHECKING:
    from app.services.bot.order import OrderPreview
    from app.services.bot.query import (
        AlertRuleRow,
        PositionRow,
        SymbolQuote,
        WatchlistRow,
    )
    from app.services.bot.quiet import QuietHoursView

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
                {"text": "🛒 下单", "callback_data": "menu:order"},
                {"text": "🔔 告警规则", "callback_data": "menu:rules"},
            ],
            # 0028 N3 · 安静时段(查看 + 启停 + 起止小时步进 · 时区切换留网页 DP9)
            [{"text": "🌙 安静时段", "callback_data": "menu:quiet"}],
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
    # 泛化引导:不逐一列功能(以后加按钮无需改文案)· 按钮清单以 main_menu_keyboard 为准
    text = (
        f"*{_BRAND} · 迷你终端*\n\n"
        "点下方按钮选择功能 ↓\n\n"
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


# ── 下单(G4 · 虚拟 · 必经二次确认)────────────────────────────────────


def _order_market_keyboard() -> Keyboard:
    return {
        "inline_keyboard": [
            [
                {"text": "A股", "callback_data": "omkt:cn"},
                {"text": "美股", "callback_data": "omkt:us"},
                {"text": "加密合约", "callback_data": "omkt:crypto"},
            ],
            [{"text": "⬅️ 返回菜单", "callback_data": "menu:main"}],
        ],
    }


def _order_direction_keyboard(market: str) -> Keyboard:
    """按市场给方向按钮 · callback `odir:<direction>`。"""
    dirs = order_mod.directions_for(market)
    btns = [
        {"text": order_mod.direction_label(d), "callback_data": f"odir:{d}"}
        for d in dirs
    ]
    # 每行最多 2 个
    rows = [btns[i : i + 2] for i in range(0, len(btns), 2)]
    rows.append([{"text": "⬅️ 返回菜单", "callback_data": "menu:main"}])
    return {"inline_keyboard": rows}


def _order_confirm_keyboard() -> Keyboard:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ 确认下单", "callback_data": "ordok"},
                {"text": "✖️ 取消", "callback_data": "ordno"},
            ],
        ],
    }


def render_order_market_picker() -> BotReply:
    text = (
        f"*{_BRAND} · 下单* (VIRTUAL · 模拟)\n\n"
        "🛒 全程虚拟资金 · 先选市场:"
    )
    return BotReply(_tail(text), _order_market_keyboard())


def render_order_ask_symbol(market: str) -> BotReply:
    examples = {"cn": "600519", "us": "NVDA", "crypto": "BTC/USDT"}
    mlabel = _MARKET_LABEL.get(market, market)
    extra = "(加密为永续合约 · 逐仓)" if market == "crypto" else ""
    text = (
        f"*{_BRAND} · 下单* {extra}\n\n"
        f"{mlabel} · 请发送要下单的代码,例如 `{examples.get(market, 'BTC/USDT')}`"
    )
    return BotReply(_tail(text), _back_keyboard())


def render_order_directions(market: str, symbol: str, price: float | None) -> BotReply:
    mlabel = _MARKET_LABEL.get(market, market)
    price_line = (
        f"当前价 {_fmt_price(price, _market_ccy(market))}" if price is not None else "—"
    )
    text = (
        f"*{_BRAND} · 下单* (VIRTUAL · 模拟)\n\n"
        f"{symbol} · {mlabel}\n{price_line}\n\n选择操作:"
    )
    return BotReply(_tail(text), _order_direction_keyboard(market))


def render_order_preview(preview: OrderPreview) -> BotReply:
    mlabel = _MARKET_LABEL.get(preview.market, preview.market)
    lines = [
        f"*{_BRAND} · 下单确认* (VIRTUAL · 模拟)",
        "",
        f"{preview.direction_label} · {preview.symbol} · {mlabel}",
        f"预估价 {_fmt_price(preview.est_price, preview.currency)}",
        f"数量 ~{_fmt_qty(preview.quantity)}",
        f"名义 ~{_fmt_price(preview.notional, preview.currency)}",
    ]
    if preview.leverage is not None:
        lines.append(f"杠杆 {preview.leverage}x · 逐仓")
    lines.append("")
    lines.append("⚠️ 确认后立即以【虚拟资金】下单,不可撤销。")
    return BotReply(_tail("\n".join(lines)), _order_confirm_keyboard())


def render_order_unavailable() -> BotReply:
    text = (
        f"*{_BRAND} · 下单*\n\n"
        "无法下单:可能暂无最新报价,或(平仓时)当前没有可平持仓。\n"
        "请确认代码 / 持仓后再试。"
    )
    return BotReply(_tail(text), _back_keyboard())


def render_order_result(title: str, detail: str) -> BotReply:
    text = f"*{_BRAND} · {title}*\n\n{detail}"
    return BotReply(_tail(text), _back_keyboard())


def render_order_receipt(body: str) -> BotReply:
    """成交富回执(#296 去重 · 方向③ 合一)。

    body 已是 render_telegram 渲染好的富文本(含品牌标题 + 「本次为模拟交易,不构成
    投资建议」免责)· 前置 ✅ 成功确认 + 挂返回菜单键盘。不再走 _tail(免责已在 body 内)。
    bot 成交从此只发这一条(异步推送 A 已在 bot 路径抑制),与网页/异步同一套格式。
    """
    return BotReply(f"✅ {body}", _back_keyboard())


def render_order_symbol_invalid(market: str, raw: str) -> BotReply:
    """下单标的识别失败(#296 改动二)· 不静默继续 · 提示重输 + 示例。"""
    eg = {
        "crypto": "BTC / BTCUSDT / BTC/USDT",
        "us": "NVDA / AAPL",
        "cn": "600519 / 000001",
    }.get(market, "BTC / NVDA / 600519")
    text = (
        f"*{_BRAND} · 下单*\n\n"
        f"未找到「{raw}」对应的标的,请重新输入。\n例:{eg}"
    )
    return BotReply(_tail(text), _back_keyboard())


def render_order_cancelled() -> BotReply:
    return BotReply(_tail(f"*{_BRAND} · 下单*\n\n已取消,未下单。"), main_menu_keyboard())


def render_rate_limited() -> BotReply:
    text = (
        f"*{_BRAND}*\n\n"
        "操作过于频繁,请稍后再试(防滥用限流)。"
    )
    return BotReply(_tail(text), None)


# ── 告警规则(G5 · 查看 / 启停 / 一键推荐 · 全量新建留网页)────────────────

_OP_SYM: dict[str, str] = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤"}


def _alert_rule_label(r: AlertRuleRow) -> str:
    icon = "🔔" if r.enabled else "🔕"
    op = _OP_SYM.get(r.operator, r.operator)
    target = r.symbol or _MARKET_LABEL.get(r.market, r.market)
    unit = r.unit or ""
    label = f"{icon} {r.indicator_label}{op}{_fmt_qty(r.threshold)}{unit} · {target}"
    return label[:60]  # Telegram 按钮文字上限


def _alert_rules_keyboard(rows: list[AlertRuleRow]) -> Keyboard:
    kb: list[list[dict[str, str]]] = [
        [{"text": _alert_rule_label(r), "callback_data": f"rules:toggle:{r.rule_id}"}]
        for r in rows[:20]
    ]
    kb.append([{"text": "✨ 一键应用推荐规则", "callback_data": "rules:apply"}])
    kb.append([{"text": "⬅️ 返回菜单", "callback_data": "menu:main"}])
    return {"inline_keyboard": kb}


def render_alert_rules(rows: list[AlertRuleRow], *, note: str | None = None) -> BotReply:
    head = f"*{_BRAND} · 告警规则*"
    if note:
        head += f"\n\n{note}"
    if not rows:
        body = (
            "\n\n你还没有告警规则。\n"
            "点「✨ 一键应用推荐规则」快速开始,或在网页端【设置 → 告警规则】自定义。"
        )
    else:
        body = "\n\n🔔=启用 / 🔕=停用 · 点规则可切换状态;全量新建在网页端。"
    return BotReply(_tail(head + body), _alert_rules_keyboard(rows))


# ── 安静时段(N3 · 查看 + 启停 + 起止小时步进 · 时区切换留网页 DP9)────────


def _fmt_hour(h: int) -> str:
    return f"{h:02d}:00"


def _quiet_hours_keyboard(view: QuietHoursView) -> Keyboard:
    """6 按钮键盘:启停 + 起/止 ±1 + 网页换时区(深链)+ 返回。"""
    toggle_label = "🔕 关闭安静时段" if view.enabled else "🔔 启用安静时段"
    # 起止小时步进:把 ±1 放在数值两侧,直观
    start_label = f"起 {_fmt_hour(view.start_hour)}"
    end_label = f"止 {_fmt_hour(view.end_hour)}"
    settings_url = f"{settings.public_web_base_url.rstrip('/')}/settings"
    return {
        "inline_keyboard": [
            [{"text": toggle_label, "callback_data": "quiet:toggle"}],
            [
                {"text": "−1h", "callback_data": "quiet:s-"},
                {"text": start_label, "callback_data": "quiet:noop"},
                {"text": "+1h", "callback_data": "quiet:s+"},
            ],
            [
                {"text": "−1h", "callback_data": "quiet:e-"},
                {"text": end_label, "callback_data": "quiet:noop"},
                {"text": "+1h", "callback_data": "quiet:e+"},
            ],
            [{"text": "🌐 时区调整 · 在网页端", "url": settings_url}],
            [{"text": "⬅️ 返回菜单", "callback_data": "menu:main"}],
        ],
    }


def render_quiet_hours(view: QuietHoursView) -> BotReply:
    """显示当前安静时段配置 + 紧急豁免说明(对齐 N2 网页文案)。"""
    status_icon = "🌙" if view.enabled else "☀️"
    status_word = "已启用" if view.enabled else "已关闭"
    cross_night = view.start_hour > view.end_hour
    end_with_next = (
        f"次日 {_fmt_hour(view.end_hour)}" if cross_night else _fmt_hour(view.end_hour)
    )

    lines = [
        f"*{_BRAND} · 安静时段*",
        "",
        f"{status_icon} 状态:{status_word}",
        f"⏰ 时段:{_fmt_hour(view.start_hour)} – {end_with_next}",
        f"🌐 时区:{view.tz}",
        "",
        "⚠️ 安静时段内仅静默【普通告警】(自选异动 / 规则告警),",
        "    *成交 / 强平等关键事件照常推送*,夜间不漏。",
        "",
        "按下方按钮调整开关 / 起止小时;时区切换请到网页端。",
    ]
    return BotReply(_tail("\n".join(lines)), _quiet_hours_keyboard(view))


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
