"""通道中立的回复 / 入站模型 + 内容构建(build_*)· ADR 0032 阶段一地基。

这一层【不含任何 Telegram / 飞书专属格式】:
- 出站 ReplyModel:标题 + 正文 + 按钮(行×列)+ 免责尾 —— 由各通道 renderer 渲染成
  TG inline_keyboard 或飞书 interactive card。
- 入站 InboundMessage:已验签事件归一后的中立入站(channel + channel_uid + 文本/按钮)。
- build_*:把核心层结构化结果(SymbolQuote / OrderPreview / …)构建成 ReplyModel。

🔴 红线(随多通道继承):
- action 命名空间 = 原 Telegram callback_data 原样冻结(零回归基石,见 ADR 0032 §3)。
- 下单(G4)全程 VIRTUAL·模拟 + 必经二次确认(确认按钮 action="ordok",见 router)。
- 输出不带免责尾 / VIRTUAL 徽章噪音(平台层已说明全程虚拟)。

数值格式化 helper 属"中立呈现"(数字→展示串),放这里供 build_* 复用;Markdown 粗体 /
斜体等 TG 专属修饰只在 renderers/telegram.py 处理。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta, timezone
from typing import TYPE_CHECKING, Literal

from app.core.config import settings
from app.core.formatting import format_price_number
from app.services.bot import order as order_mod

if TYPE_CHECKING:
    from app.services.bot.order import OrderPreview
    from app.services.bot.query import (
        AlertRuleRow,
        NameHit,
        PositionRow,
        SpotLite,
        SymbolQuote,
        WatchlistRow,
    )
    from app.services.bot.quiet import QuietHoursView

# A股/港股均 UTC+8(无 DST)· 轻量卡「更新时间」按北京时间展示
_CN_TZ = timezone(timedelta(hours=8))

# 产品决策:bot 输出不再带免责句 / VIRTUAL 徽章噪音(平台层已说明全程虚拟)。
# disclaimer / badge 字段保留(供未来用),默认空 —— 渲染器条件渲染,空则不输出。
_BRAND = "点金 Midas"
_MARKET_LABEL: dict[str, str] = {"cn": "A股", "us": "美股", "crypto": "加密", "hk": "港股"}
_CCY_SYMBOL: dict[str, str] = {"CNY": "¥", "USD": "$", "USDT": "", "HKD": "HK$"}
_PREVIEW_PATH: dict[str, str] = {
    "cn": "cn-preview", "us": "us-preview", "crypto": "crypto-preview",
}


# ── 中立出站模型 ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Button:
    """一个按钮 · action(回调)与 url(外链)二选一。

    action = 原 Telegram callback_data 语义(冻结);url 非 None 时为外链按钮(K 线深链)。
    """

    label: str
    action: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class ReplyModel:
    """一次 bot 响应(通道中立)。

    - title:语义标题(无品牌前缀 / 无 Markdown);None = 仅品牌头。
    - badge:标题行尾的非加粗徽章 · 含前导空格 · 默认无(产品决策:不再用)。
    - text:正文(无标题行 / 无免责尾)· 偏中立(emoji + 纯文本 + 数字)。
    - buttons:按钮行×列(空 = 无键盘)。
    - disclaimer:免责尾(renderer 追加);None = 不追加(如成交回执已自带)。
    - kind:呈现风格提示(text/card)· TG 不分,留给飞书 card 用。
    - force_new:保留位 · 飞书/未来"强制发新消息";阶段一 TG 路径不消费(edit/new 由
      transport 按入站类型决定,行为不变)。
    - prerendered:True = text 已是完整成稿(成交回执,自带品牌头+免责)· renderer 原样输出。
    """

    text: str
    title: str | None = None
    badge: str = ""
    buttons: tuple[tuple[Button, ...], ...] = ()
    disclaimer: str | None = None
    kind: Literal["text", "card"] = "card"
    force_new: bool = False
    prerendered: bool = False
    # KLINE-001:非空 = 该回复应作为【图片】发送(photo_url 指向 K线图 PNG 端点)·
    # transport 优先 sendPhoto(text 作 caption + 按钮保留)· 发图失败/数据不足回退发 text(网页链接)。
    photo_url: str | None = None


# ── 中立入站模型 ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class InboundMessage:
    """已验签事件归一后的中立入站。

    🔴 channel_uid 只在各通道 webhook 验签通过后构造(TG chat_id / 飞书 open_id)——
    这是身份红线的物理锚点(ADR 0032 §6 · 业务层绝不从 text 取身份)。
    """

    channel: str  # "telegram" | "feishu" | "dingtalk"
    channel_uid: str
    kind: Literal["text", "button"]
    text: str | None = None  # kind=text 时的用户文本
    action: str | None = None  # kind=button 时的动作标识(= Button.action)
    reply_ctx: dict[str, object] = field(default_factory=dict)  # 通道私有透传 · 业务不读


# ── 数值格式化(中立呈现)────────────────────────────────────────────


def _fmt_price(v: float, currency: str) -> str:
    # 价格动态精度(ADR 金额精度规格)· 数字串单一事实源见 app.core.formatting.format_price_number
    # (按数量级动态 + <1 去尾零)· 仅价格类,不碰盈亏 / 手续费。
    sym = _CCY_SYMBOL.get(currency, "")
    body = format_price_number(v)
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


def _fmt_compact_cny(v: float, market: str) -> str:
    """大额成交额紧凑(人民币/港币口径):45.6亿 / 1180万 · cn=¥ · hk=HK$。"""
    sym = "HK$" if market == "hk" else "¥"
    a = abs(v)
    if a >= 1e8:
        return f"{sym}{v / 1e8:.2f}亿"
    if a >= 1e4:  # noqa: PLR2004
        return f"{sym}{v / 1e4:.2f}万"
    return f"{sym}{v:.0f}"


def _fmt_qty(v: float) -> str:
    if v == int(v):
        return f"{int(v):,}"
    return f"{v:,.8f}".rstrip("0").rstrip(".")


def _market_ccy(market: str) -> str:
    return {"cn": "CNY", "us": "USD", "crypto": "USDT", "hk": "HKD"}.get(market, "USD")


def web_chart_url(market: str, symbol: str) -> str:
    """拼网页 K 线深链(DP14)· crypto 用 Binance 风格无斜杠。"""
    base = settings.public_web_base_url.rstrip("/")
    path = _PREVIEW_PATH.get(market, "workbench")
    sym = symbol.replace("/", "") if market == "crypto" else symbol
    return f"{base}/{path}?symbol={sym}"


def chart_png_url(market: str, symbol: str, name: str = "") -> str:
    """拼 K线图 PNG 端点 URL(KLINE-001 · bot sendPhoto 用)· 公网 api 域名。

    symbol 原样传(端点内部 crypto 去斜杠对齐 CH)· URL 编码防斜杠/中文名破坏 query。
    """
    from urllib.parse import quote

    base = settings.public_api_base_url.rstrip("/")
    q = f"market={market}&symbol={quote(symbol, safe='')}"
    if name:
        q += f"&name={quote(name, safe='')}"
    return f"{base}/api/v1/chart/kline.png?{q}"


def _fmt_hour(h: int) -> str:
    return f"{h:02d}:00"


# ── 中立键盘构建(返回 Button 行×列)──────────────────────────────────


def _main_menu_buttons() -> tuple[tuple[Button, ...], ...]:
    return (
        (Button("📊 行情查询", "menu:quote"), Button("📈 K线图", "menu:kline")),
        (Button("⭐ 我的自选", "act:watchlist"), Button("💼 我的持仓", "act:positions")),
        (Button("🛒 下单", "menu:order"), Button("🔔 告警规则", "menu:rules")),
        (Button("🌙 安静时段", "menu:quiet"),),
    )


def _back_buttons() -> tuple[tuple[Button, ...], ...]:
    return ((Button("⬅️ 返回菜单", "menu:main"),),)


def _quote_buttons(market: str, symbol: str) -> tuple[tuple[Button, ...], ...]:
    return (
        (Button("📈 网页看K线", url=web_chart_url(market, symbol)),),
        (Button("⬅️ 返回菜单", "menu:main"),),
    )


def _quote_action_buttons(market: str, symbol: str) -> tuple[tuple[Button, ...], ...]:
    """行情卡【就地操作】键盘(P0-2 · 降链路:卡片直接分叉到 K线 / 下单 / 刷新,不必回菜单)。

    action `<op>:<market>:<symbol>`(op∈qk/qo/qr · symbol 原样含 crypto 斜杠 · callback_data
    ≤64 字节)· 由 router._parse_sym_action 解析:qk 看K线 / qo 直达下单 / qr 刷新行情 ·
    外加「网页K线」外链 + 返回菜单。symbol 即 query_symbol 回显形态,刷新可精确复现。
    """
    return (
        (
            Button("📈 K线", f"qk:{market}:{symbol}"),
            Button("🛒 下单", f"qo:{market}:{symbol}"),
        ),
        (
            Button("🔄 刷新", f"qr:{market}:{symbol}"),
            Button("🌐 网页K线", url=web_chart_url(market, symbol)),
        ),
        (Button("⬅️ 返回菜单", "menu:main"),),
    )


def _market_picker_buttons(intent: str) -> tuple[tuple[Button, ...], ...]:
    return (
        (
            Button("A股", f"ask:{intent}:cn"),
            Button("美股", f"ask:{intent}:us"),
            Button("加密", f"ask:{intent}:crypto"),
        ),
        (Button("⬅️ 返回菜单", "menu:main"),),
    )


def _order_market_buttons() -> tuple[tuple[Button, ...], ...]:
    return (
        (
            Button("A股", "omkt:cn"),
            Button("美股", "omkt:us"),
            Button("加密合约", "omkt:crypto"),
        ),
        (Button("⬅️ 返回菜单", "menu:main"),),
    )


def _order_direction_buttons(market: str) -> tuple[tuple[Button, ...], ...]:
    """按市场给方向按钮 · action `odir:<direction>` · 每行最多 2 个 + 返回行。"""
    dirs = order_mod.directions_for(market)
    btns = [Button(order_mod.direction_label(d), f"odir:{d}") for d in dirs]
    rows: list[tuple[Button, ...]] = [
        tuple(btns[i : i + 2]) for i in range(0, len(btns), 2)
    ]
    rows.append((Button("⬅️ 返回菜单", "menu:main"),))
    return tuple(rows)


def _order_confirm_buttons() -> tuple[tuple[Button, ...], ...]:
    return ((Button("✅ 确认下单", "ordok"), Button("✖️ 取消", "ordno")),)


_OP_SYM: dict[str, str] = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤"}


def _alert_rule_label(r: AlertRuleRow) -> str:
    icon = "🔔" if r.enabled else "🔕"
    op = _OP_SYM.get(r.operator, r.operator)
    target = r.symbol or _MARKET_LABEL.get(r.market, r.market)
    unit = r.unit or ""
    label = f"{icon} {r.indicator_label}{op}{_fmt_qty(r.threshold)}{unit} · {target}"
    return label[:60]  # Telegram 按钮文字上限(中立侧也截断,飞书同样适用)


def _alert_rules_buttons(rows: list[AlertRuleRow]) -> tuple[tuple[Button, ...], ...]:
    kb: list[tuple[Button, ...]] = [
        (Button(_alert_rule_label(r), f"rules:toggle:{r.rule_id}"),) for r in rows[:20]
    ]
    kb.append((Button("✨ 一键应用推荐规则", "rules:apply"),))
    kb.append((Button("⬅️ 返回菜单", "menu:main"),))
    return tuple(kb)


def _quiet_hours_buttons(view: QuietHoursView) -> tuple[tuple[Button, ...], ...]:
    """6 按钮:启停 + 起/止 ±1 + 网页换时区(深链)+ 返回。"""
    toggle_label = "🔕 关闭安静时段" if view.enabled else "🔔 启用安静时段"
    start_label = f"起 {_fmt_hour(view.start_hour)}"
    end_label = f"止 {_fmt_hour(view.end_hour)}"
    settings_url = f"{settings.public_web_base_url.rstrip('/')}/settings"
    return (
        (Button(toggle_label, "quiet:toggle"),),
        (
            Button("−1h", "quiet:s-"),
            Button(start_label, "quiet:noop"),
            Button("+1h", "quiet:s+"),
        ),
        (
            Button("−1h", "quiet:e-"),
            Button(end_label, "quiet:noop"),
            Button("+1h", "quiet:e+"),
        ),
        (Button("🌐 时区调整 · 在网页端", url=settings_url),),
        (Button("⬅️ 返回菜单", "menu:main"),),
    )


# ── build_*:核心结构 → ReplyModel(纯函数 · 无 IO)───────────────────


def build_main_menu() -> ReplyModel:
    text = (
        "点下方按钮选择功能 ↓\n\n"
        "也可直接发送 `/price <代码>` 查行情"
    )
    return ReplyModel(
        text=text, title="迷你终端", disclaimer=None, buttons=_main_menu_buttons(),
    )


def build_market_picker(intent: str) -> ReplyModel:
    what = "查行情" if intent == "quote" else "看K线"
    return ReplyModel(
        text=f"{what} —— 先选市场:", disclaimer=None,
        buttons=_market_picker_buttons(intent),
    )


def build_quote_ask() -> ReplyModel:
    """裸 /price 引导(P0-3 · 降链路)· 不强制先选市场,直接发代码即可(市场自动判断)。

    示例 crypto 用 `BTC/USDT`(带斜杠才被 _guess_market 判为加密;裸 BTC 会判成美股查不到)。
    """
    text = "直接发代码即可,例如 `BTC/USDT` / `NVDA` / `600519` / `00700`(市场自动识别)"
    return ReplyModel(
        text=text, title="查行情", disclaimer=None, buttons=_back_buttons(),
    )


def build_kline_ask() -> ReplyModel:
    """reply-kb [📈 K线] 引导 · 发代码看 K线(市场自动判断)· K线按代码出图,中文名先用[行情]查。"""
    text = "发代码看 K线,例如 `BTC/USDT` / `NVDA` / `600519` / `00700`(市场自动识别)"
    return ReplyModel(
        text=text, title="看K线", disclaimer=None, buttons=_back_buttons(),
    )


def build_ask_symbol(intent: str, market: str) -> ReplyModel:
    examples = {"cn": "600519", "us": "NVDA", "crypto": "BTC/USDT", "hk": "00700"}
    what = "查行情" if intent == "quote" else "看K线"
    mlabel = _MARKET_LABEL.get(market, market)
    text = (
        f"{mlabel} · {what}\n"
        f"请发送代码,例如 `{examples.get(market, 'BTC/USDT')}`"
    )
    return ReplyModel(text=text, disclaimer=None, buttons=_back_buttons())


def build_quote(quote: SymbolQuote) -> ReplyModel:
    mlabel = _MARKET_LABEL.get(quote.market, quote.market)
    lines = [f"📊 {quote.symbol} · {mlabel}"]
    if quote.price is not None:
        lines.append(f"最新价 {_fmt_price(quote.price, quote.currency)}")
    lines.append(f"涨跌幅 {_fmt_pct(quote.change_pct)}")
    if quote.volume is not None:
        lines.append(f"成交量 {_fmt_qty(quote.volume)}")
    if quote.funding_rate is not None:
        lines.append(f"资金费率 {quote.funding_rate * 100:+.4f}%")
    if quote.open_interest_usd is not None:
        lines.append(f"未平仓额 {_fmt_compact_usd(quote.open_interest_usd)}")
    if quote.long_short_ratio is not None:
        lines.append(f"多空比(大户) {quote.long_short_ratio:.2f}")
    if quote.basis_pct is not None:
        lines.append(f"基差 {quote.basis_pct:+.3f}%")
    return ReplyModel(
        text="\n".join(lines),
        title="行情",
        disclaimer=None,
        buttons=_quote_action_buttons(quote.market, quote.symbol),
    )


def build_symbol_not_found(market: str, symbol: str) -> ReplyModel:
    mlabel = _MARKET_LABEL.get(market, market)
    text = (
        f"未找到 {symbol}({mlabel})的数据。\n"
        "请确认代码,或换一个再试(只查已采集标的)。"
    )
    return ReplyModel(text=text, disclaimer=None, buttons=_back_buttons())


def build_code_not_found(raw: str) -> ReplyModel:
    """字母代码扫库(加密 + 美股)均未命中 · 提示带斜杠加密形态 / 检查代码。"""
    s = raw.strip().upper()
    text = (
        f"未找到「{raw}」对应的标的。\n"
        f"· 加密永续请带斜杠,如 `{s}/USDT`\n"
        "· 或检查代码是否正确(只查已采集标的)"
    )
    return ReplyModel(text=text, disclaimer=None, buttons=_back_buttons())


def build_name_not_found(raw: str) -> ReplyModel:
    """中文名搜索未命中 · 提示换关键词 / 直接发代码(不含加密斜杠提示)。"""
    text = (
        f"未找到「{raw}」相关标的。\n"
        "· 换个关键词试试,或直接发代码(如 600519 / 00700)"
    )
    return ReplyModel(text=text, disclaimer=None, buttons=_back_buttons())


def build_lite_quote_card(lite: SpotLite) -> ReplyModel:
    """无 kline 的轻量信息卡(只读 spot 快照 · cn/hk 长尾兜底)。

    ★诚实标注「暂无 K线/深度分析」(守不伪造红线)· 只展示 spot 能给的(价/涨跌/成交额/更新)·
    按钮仅【网页查看 + 返回菜单】· 不放下单 / 不放加自选(本刀范围外)。
    """
    mlabel = _MARKET_LABEL.get(lite.market, lite.market)
    ccy = _market_ccy(lite.market)
    when = lite.ts.astimezone(_CN_TZ).strftime("%m-%d %H:%M")
    lines = [
        f"📋 {lite.name} · {mlabel} · {lite.symbol}",
        f"最新价 {_fmt_price(lite.last_price, ccy)}",
        f"涨跌幅 {_fmt_pct(lite.change_pct)}",
        f"成交额 {_fmt_compact_cny(lite.amount, lite.market)}",
        f"更新 {when}",
        "",
        "ℹ️ 暂无 K线/深度分析数据,可在网页端查看完整信息",
    ]
    return ReplyModel(
        text="\n".join(lines),
        title="行情(简)",
        disclaimer=None,
        buttons=(
            (Button("🌐 网页查看", url=web_chart_url(lite.market, lite.symbol)),),
            (Button("⬅️ 返回菜单", "menu:main"),),
        ),
    )


def build_candidate_list(hits: list[NameHit]) -> ReplyModel:
    """中文名多命中候选(单条卡 + 一列按钮 · 照 build_alert_rules 范式)。

    每个候选一个按钮 `qv:<market>:<symbol>`(点击出该标的卡 · 有K线完整卡 / 无K线轻量卡)·
    label「代码 中文名」截断 60(兼容 TG 按钮文字上限 · 飞书同样适用)· 末行返回菜单。
    """
    rows: list[tuple[Button, ...]] = [
        (Button(f"{h.symbol} {h.name}"[:60], f"qv:{h.market}:{h.symbol}"),)
        for h in hits
    ]
    rows.append((Button("⬅️ 返回菜单", "menu:main"),))
    return ReplyModel(
        text="点选你要查看的标的 ↓",
        title="找到多个标的",
        disclaimer=None,
        buttons=tuple(rows),
    )


def build_kline_link(market: str, symbol: str) -> ReplyModel:
    """K线回复(KLINE-001)· 优先发【此刻 K线图截图】(photo_url)· 文本作 caption ·
    保留「网页看K线」按钮(交互式缠论/指标)· 发图失败/数据不足由 transport 回退发文本链接。
    """
    mlabel = _MARKET_LABEL.get(market, market)
    text = f"📈 {symbol} · {mlabel} · K线(MA / RSI / MACD · 此刻)"
    return ReplyModel(
        text=text, title="K线", disclaimer=None,
        buttons=_quote_buttons(market, symbol),
        photo_url=chart_png_url(market, symbol),
    )


def build_watchlist(rows: list[WatchlistRow]) -> ReplyModel:
    if not rows:
        text = "你还没有自选标的。\n在网页端工作台用 Cmd/Ctrl+K 添加。"
        return ReplyModel(text=text, title="自选", disclaimer=None, buttons=_back_buttons())
    lines = []
    for r in rows:
        mlabel = _MARKET_LABEL.get(r.market, r.market)
        price = "—" if r.price is None else _fmt_price(r.price, _market_ccy(r.market))
        lines.append(f"{r.symbol} · {mlabel}  {price}  {_fmt_pct(r.change_pct)}")
    return ReplyModel(
        text="\n".join(lines), title="自选", disclaimer=None, buttons=_back_buttons(),
    )


def build_positions(rows: list[PositionRow]) -> ReplyModel:
    if not rows:
        text = "当前没有活仓。"
        return ReplyModel(text=text, title="持仓", buttons=_back_buttons())
    lines = []
    for r in rows:
        mlabel = _MARKET_LABEL.get(r.market, r.market)
        side_cn = "多" if r.side == "long" else "空"
        tag = f"永续{r.leverage}x" if r.kind == "perp" else mlabel
        entry = _fmt_price(r.avg_entry_price, r.currency)
        lines.append(f"{r.symbol} · {tag} · {side_cn}  {_fmt_qty(r.quantity)} @ {entry}")
    return ReplyModel(
        text="\n".join(lines), title="持仓", buttons=_back_buttons(),
    )


def build_order_market_picker() -> ReplyModel:
    return ReplyModel(
        text="🛒 先选市场:", title="下单",
        buttons=_order_market_buttons(),
    )


def build_order_ask_symbol(market: str) -> ReplyModel:
    examples = {"cn": "600519", "us": "NVDA", "crypto": "BTC/USDT", "hk": "00700"}
    mlabel = _MARKET_LABEL.get(market, market)
    extra = "(加密为永续合约 · 逐仓)" if market == "crypto" else ""
    text = f"{mlabel} · 请发送要下单的代码,例如 `{examples.get(market, 'BTC/USDT')}`"
    # 旧实现 header 为 f"... 下单* {extra}" · 非 crypto 时 extra="" 留一个尾随空格(字节级保真)
    return ReplyModel(
        text=text, title="下单", badge=f" {extra}", disclaimer=None,
        buttons=_back_buttons(),
    )


def build_order_directions(market: str, symbol: str, price: float | None) -> ReplyModel:
    mlabel = _MARKET_LABEL.get(market, market)
    price_line = (
        f"当前价 {_fmt_price(price, _market_ccy(market))}" if price is not None else "—"
    )
    text = f"{symbol} · {mlabel}\n{price_line}\n\n选择操作:"
    return ReplyModel(
        text=text, title="下单",
        buttons=_order_direction_buttons(market),
    )


def build_order_preview(preview: OrderPreview) -> ReplyModel:
    mlabel = _MARKET_LABEL.get(preview.market, preview.market)
    lines = [
        f"{preview.direction_label} · {preview.symbol} · {mlabel}",
        f"预估价 {_fmt_price(preview.est_price, preview.currency)}",
        f"数量 ~{_fmt_qty(preview.quantity)}",
        f"名义 ~{_fmt_price(preview.notional, preview.currency)}",
    ]
    if preview.leverage is not None:
        lines.append(f"杠杆 {preview.leverage}x · 逐仓")
    lines.append("")
    lines.append("⚠️ 确认后立即以【账户资金】下单,不可撤销。")
    return ReplyModel(
        text="\n".join(lines), title="下单确认",
        buttons=_order_confirm_buttons(),
    )


def build_order_unavailable() -> ReplyModel:
    text = (
        "无法下单:可能暂无最新报价,或(平仓时)当前没有可平持仓。\n"
        "请确认代码 / 持仓后再试。"
    )
    return ReplyModel(text=text, title="下单", disclaimer=None, buttons=_back_buttons())


def build_order_result(title: str, detail: str) -> ReplyModel:
    return ReplyModel(
        text=detail, title=title, buttons=_back_buttons(),
    )


def build_order_receipt(body: str) -> ReplyModel:
    """成交富回执(#296 去重 · 方向③ 合一)。

    body 已是 render_telegram 渲染好的富文本(含品牌标题)·
    前置 ✅ + 挂返回菜单键盘 · prerendered=True 让 renderer 原样输出(不加品牌头/免责尾)。
    """
    return ReplyModel(
        text=f"✅ {body}", disclaimer=None, prerendered=True, buttons=_back_buttons(),
    )


def build_order_symbol_invalid(market: str, raw: str) -> ReplyModel:
    """下单标的识别失败(#296 改动二)· 不静默继续 · 提示重输 + 示例。"""
    eg = {
        "crypto": "BTC / BTCUSDT / BTC/USDT",
        "us": "NVDA / AAPL",
        "cn": "600519 / 000001",
    }.get(market, "BTC / NVDA / 600519")
    text = f"未找到「{raw}」对应的标的,请重新输入。\n例:{eg}"
    return ReplyModel(text=text, title="下单", disclaimer=None, buttons=_back_buttons())


def build_order_direction_hint() -> ReplyModel:
    """选方向那步误输文字时的友好引导(不再泛化推回主菜单)。"""
    text = (
        "请点上方按钮选择方向(开多 / 开空 / 平仓)。\n"
        "如需更换标的,请点「🛒 下单」重新开始。"
    )
    return ReplyModel(text=text, title="下单", disclaimer=None, buttons=_back_buttons())


def build_order_cancelled() -> ReplyModel:
    return ReplyModel(
        text="已取消,未下单。", title="下单", disclaimer=None,
        buttons=_main_menu_buttons(),
    )


def build_rate_limited() -> ReplyModel:
    return ReplyModel(text="操作过于频繁,请稍后再试(防滥用限流)。", disclaimer=None)


def build_alert_rules(rows: list[AlertRuleRow], *, note: str | None = None) -> ReplyModel:
    if not rows:
        body = (
            "你还没有告警规则。\n"
            "点「✨ 一键应用推荐规则」快速开始,或在网页端【设置 → 告警规则】自定义。"
        )
    else:
        body = "🔔=启用 / 🔕=停用 · 点规则可切换状态;全量新建在网页端。"
    text = f"{note}\n\n{body}" if note else body
    return ReplyModel(
        text=text, title="告警规则", disclaimer=None,
        buttons=_alert_rules_buttons(rows),
    )


def build_quiet_hours(view: QuietHoursView) -> ReplyModel:
    """显示当前安静时段配置 + 紧急豁免说明(对齐 N2 网页文案)。"""
    status_icon = "🌙" if view.enabled else "☀️"
    status_word = "已启用" if view.enabled else "已关闭"
    cross_night = view.start_hour > view.end_hour
    end_with_next = (
        f"次日 {_fmt_hour(view.end_hour)}" if cross_night else _fmt_hour(view.end_hour)
    )
    lines = [
        f"{status_icon} 状态:{status_word}",
        f"⏰ 时段:{_fmt_hour(view.start_hour)} – {end_with_next}",
        f"🌐 时区:{view.tz}",
        "",
        "⚠️ 安静时段内仅静默【普通告警】(自选异动 / 规则告警),",
        "    *成交 / 强平等关键事件照常推送*,夜间不漏。",
        "",
        "按下方按钮调整开关 / 起止小时;时区切换请到网页端。",
    ]
    return ReplyModel(
        text="\n".join(lines), title="安静时段", disclaimer=None,
        buttons=_quiet_hours_buttons(view),
    )


def build_not_bound() -> ReplyModel:
    text = (
        "你的 Telegram 还没绑定 Midas 账号。\n"
        "请到网页端【设置 → 消息推送】点「绑定 Telegram」,按提示完成绑定后再用。"
    )
    return ReplyModel(text=text, disclaimer=None)


def build_hint() -> ReplyModel:
    text = "发送 /menu 打开功能菜单,或 `/price <代码>` 直接查行情。"
    return ReplyModel(text=text, disclaimer=None, buttons=_main_menu_buttons())
