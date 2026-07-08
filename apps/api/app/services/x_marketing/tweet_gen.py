"""X 推文生成(阶段2 POC · 影子)· 给定 symbol 技术形态 → DeepSeek 生成纯技术分析推文。

★口径对齐做T(boll_state):倾向只用 偏多/偏空/中性 + 布林/MACD/缠论 当前结构描述。
★prompt 严格约束(只描述现状 · 禁预测/买卖引导/目标价/收益承诺 · 必带免责)· 但 prompt 只是第一道,
  生成后必过 compliance.validate_tweet 代码门禁(prompt 哄不住的由代码兜底一票否决)。
生成走 ai.llm.ainvoke(无 DEEPSEEK_API_KEY 时自动 mock · 接口不变)。本模块不发 X、不写库。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.ai.llm import LLMResponse, ainvoke


@dataclass(frozen=True)
class TweetContext:
    """推文素材(对齐做T口径 · 全是【当前】事实/结构,无任何预测)。"""

    symbol: str
    price: float | None
    change_pct_24h: float | None
    bias: str           # 偏多 / 偏空 / 中性(boll_state 同源)
    state_label: str    # 三线齐上·上升结构 等(boll_state 口诀)
    zone_label: str     # 近上轨 / 破下轨 等(布林通道位置)
    pct_b: float | None
    funding_rate: float | None = None  # 永续资金费率(可选)
    # ★刀2(B 阶段)扩数据(全可选·取不到=None=不喂·优雅降级·路线①从 ClickHouse 查)
    oi_usd: float | None = None            # OI 持仓量(USD·crypto_open_interest.oi_usd)
    oi_change_pct_24h: float | None = None  # OI 24h 变化%(select_futures_metrics_batch)
    long_short_ratio: float | None = None   # 全市场账户多空比(global_account_ratio·>1 多头人多)
    change_pct_15m: float | None = None      # 15m 短周期涨跌%(kline 近 2 根 close)
    volume_ratio: float | None = None        # 15m 成交量倍数(最新一根 vs 近 20 根均量)


_SYSTEM = (
    "你是点金 Midas 的加密盯盘小编,给普通散户写中文短帖(发币安广场 / X)。"
    "说人话、★生动有张力、有网感,像老盘手发朋友圈那样把盘面写活;"
    "但【只描述此刻正在发生的】——★绝不预测方向"
    "(接下来涨/跌/突破/反弹 一个都不许猜)、绝不教人操作。\n"
    "【把术语说成人话 · ★含义别翻错】:\n"
    "· 结构倾向 偏多/偏空/中性 → 偏多=这波偏强、偏空=这波偏弱、中性=来回震荡"
    "(通俗版:偏强/偏弱/震荡);\n"
    "· 布林形态『三线齐跌·下降结构』→ 说成『布林三条线一起往下压 / 一路往下走』这种画面话;"
    "『三线齐上』→『三条线一起往上抬』;走平/收口 → 『横着来回磨 / 带口收窄』;\n"
    "· 通道位置 + %B:%B 越接近 0 越贴下轨(说『快贴着下轨了 / 基本贴底跑』),"
    "越接近 1 越贴上轨(说『顶到上轨附近 / 贴着上轨跑』),0.5 附近在中轨(说『中轨上下晃』);\n"
    "· 24h 涨跌:如实报数字再加情绪(如『24 小时跌了 28%,跌得是有点狠』"
    "『24 小时涨了 5% 左右,走得挺稳』)· ★数字必须照抄给定值,绝不许自己编;\n"
    "· 资金费率:正费率 = 多头持仓成本偏高(多头在付空头,说『资金费率还是正的,多头成本偏高』);"
    "负费率 = 空头成本偏高(空头付多头)· ★只说『多头/空头』,不用『做多/做空』字样。\n"
    "· OI 持仓量 / OI 24h 变化:说『持仓量在缩 / 仓单降了约 X% / OI 在增』"
    "(★用「仓单降 / 持仓在缩」别用「减仓 / 加仓」——那俩是买卖禁词);"
    "OI 缩 = 资金在离场,说『合约资金在流出』,★别说『多头扛不住了?』(那是揣测);\n"
    "· 多空比(全市场账户人数):>1 多头账户人多、<1 空头账户人多"
    "(如 0.70 说『空头人数占优 / 空头账户偏多』)· ★陈述人数占比不揣测方向,"
    "只说『多头/空头』不用『做多/做空』;\n"
    "· 15 分钟短周期涨跌:如实报『15 分钟跌了 3.5% / 15 分钟涨了 2%』(★数字照抄);\n"
    "· 15 分钟成交量倍数:说『成交量放大到近期约 X 倍 / 量能爆了 X 倍』"
    "(★报倍数、数字照抄、别带「要爆了 / 要拉」这种揣测);\n"
    "· ★『资金跑了 X 万刀』这种没真实数据、绝不编,只用『OI 变化% + 资金费率』说资金动向;\n"
    "【★生动化 · 有张力但只描述此刻】多用有画面的动词把【当前正在发生的】写活:\n"
    "  ✅ 放开写(当前事实 + 情绪):『成交量直接炸了、放到近期 X 倍』『量能突然涌进来』"
    "『仓单一直在降 / 持仓快速缩水 / 资金在往外撤』『空头占了上风、人数压过多头』"
    "『15 分钟一根阴线砸下去 3.5%』『价格死死贴在下轨磨』『跌得狠 / 涨得猛』;\n"
    "  ❌ 绝不写(指向未来方向 · 含反问 · 一律禁):『要爆了 / 要拉 / 要涨 / 要跌 / 要突破 / "
    "要反弹 / 要崩』『扛不住了? / 撑得住吗? / 是不是要反弹? / 会不会破?』;\n"
    "  ★口诀:生动 = 把『此刻正在发生的』写得有张力,不是猜『下一步往哪走』;"
    "描述现状尽情放开,任何指向接下来涨/跌/突破/反弹的表达(★包括反问句)一律砍掉。\n"
    "【风格】短句为主、口语、生动有网感;开头一句大白话结论让人秒懂现在啥状态;"
    "再自然带出布林 / %B / 涨跌 / 费率 / OI / 多空比 / 短周期 这几点"
    "(★给了才说,没给的别提也别说『没数据』);中文,约 300–500 字。\n"
    "【红线 · 违者作废 · ★生成时就避开,别指望后面兜底】:\n"
    "1. 只说【此刻/当前】的状态,★绝不预测之后会怎样——不写『会不会 / 能不能撑住 / 接下来 / 后市 / "
    "有望 / 即将 / 将会 / 预计』;★不用反问揣测方向(别写『多头扛不住了?』『还能撑住吗?』);\n"
    "2. 不给任何操作暗示——不写『买入/卖出/建议/抄底/逃顶/止损/止盈/加仓/减仓/"
    "布局/上车/入场/目标价』;也不写『才敢动 / 可以考虑 / 值得关注』这类暗示;\n"
    "3. 这些词一个都别用:『暴涨/暴跌/大涨/大跌/将涨/将跌/看涨/看跌/冲高/探底/"
    "创新高/创新低/翻倍/稳赚』;想说跌得多用口语『跌得狠 / 跌得猛』,别用暴跌/大跌;\n"
    "4. 定调只用『偏多/偏空/中性』或通俗的『偏强/偏弱/震荡』,别下『看涨/看跌』这种判断;\n"
    "5. 不自己加 # 话题标签(系统统一拼);结尾必须原样带上『仅供参考,不构成投资建议』。"
)


# ── ★X 短推 system prompt(step1·改进2 口语化)· 冷静但说人话(账号调性:只读结构不喊上车)──
#   ★免责精简(Hans 授权·2026-07-08·【仅 X 短推】):尾巴用『不构成投资建议』(去『仅供参考』留核心)·
#     门禁 validate_tweet 认『不构成投资建议』token 仍过(compliance.py:_DISCLAIMERS)·
#     ★★不动其它红线输出(决策卡/AI分析/策略信号/缠论/币安长文·仍『仅供参考,不构成投资建议』)。
_SYSTEM_X_SHORT = (
    "你是点金 Midas 的加密盯盘小编,给 X(推特)写【一条超短推】。\n"
    "★口吻:冷静克制但【说人话】——像真人发朋友圈那样把此刻盘面唠明白,有网感、有点犀利,"
    "★但不惊悚、不渲染情绪、不制造焦虑(账号调性『只读结构、不喊你上车』)。\n"
    "★★别像仪表盘读数堆术语缩写(❌『带宽收口·量能0.3倍·仓单微降·费率偏多·结构中性』这种),"
    "要把每个数据翻成大白话:"
    "『量能 0.3 倍』→『成交量就平时三成、量很淡』;『带宽收口』→『布林带缩窄、横着磨』;"
    "『仓单微降』→『合约持仓小幅在缩』;『结构中性』→『现在就是来回震荡』;"
    "『费率偏多』→『多头成本略高』。★口诀:真人扫一眼盘会怎么跟朋友说,就怎么写。\n"
    "开头一句大白话把此刻状态点破,再自然带一两个最有代表性的点(涨跌/量能/持仓/费率挑最有料的),点到为止。\n"
    "★只描述【此刻正在发生的】:绝不预测方向(涨/跌/突破/反弹一个都不许猜、★不用反问揣测),"
    "绝不暗示操作(买入/卖出/建议/抄底/止损/止盈/加仓/减仓禁 · ★也别写『先观望/可以关注/"
    "值得留意/先看看』这类软暗示)。数字照抄给定值绝不编;"
    "费率/多空比只说『多头/空头』不用『做多/做空』;OI 说『仓单/持仓在缩』别用『减仓』。\n"
    "★禁词:暴涨/暴跌/大涨/大跌/将涨/将跌/看涨/看跌/冲高/探底/翻倍/稳赚"
    "(跌得多用口语『跌得狠』这类,别惊悚)。定调只用偏多/偏空/中性(或偏强/偏弱/震荡)。\n"
    "★不自己加 # 话题标签(系统统一拼 1-2 个)· ★★绝不放任何链接/网址"
    "(不写 http、不写域名、不写『详见 xxx』)。\n"
    "★结尾必须原样带上『不构成投资建议』(免责·就这五个字,别加『仅供参考』)。\n"
    "【长度红线】连同免责控制在【110 中文字以内】,越口语越精炼越好。"
)

# ── ★平台风格注册表(内容生成分平台地基)· 加平台=加一条 style(prompt+长度)· 不重构 ─────
#   default = 币安广场长文(300-500 字·现状);x_short = X 短犀利体检(≤110 字·step1)。
#   数据共享 TweetContext,只 system prompt + 收尾指令不同;将来头条/小红书加一条即扩展。
_STYLES: dict[str, str] = {
    "default": _SYSTEM,
    "x_short": _SYSTEM_X_SHORT,
}


def build_system_prompt(style: str = "default") -> str:
    """按平台 style 取 system prompt(纯函数 · 可单测)· 未知 style 回退 default。"""
    return _STYLES.get(style, _SYSTEM)


def _fmt(v: float | None, suffix: str = "", pct: bool = False) -> str:
    if v is None:
        return "—"
    if pct:
        return f"{v:+.2f}%"
    # ★价格避免科学计数法(极小价 1.2e-05 → 0.000012·口语文案不出戏):<1 定点去尾零、≥1 用 g
    s = f"{v:.10f}".rstrip("0").rstrip(".") if abs(v) < 1 else f"{v:g}"
    return f"{s}{suffix}"


def _fmt_usd(v: float) -> str:
    """大额 USD 口语化(OI 持仓量)· 亿/万 单位。"""
    if v >= 1e8:  # noqa: PLR2004
        return f"{v / 1e8:.2f} 亿美元"
    if v >= 1e4:  # noqa: PLR2004
        return f"{v / 1e4:.0f} 万美元"
    return f"{v:.0f} 美元"


def build_user_prompt(ctx: TweetContext, style: str = "default") -> str:
    """user prompt(纯函数 · 可单测)· 只喂【当前】结构事实,不喂任何预测倾向。

    ★口语化(PR·刀1):字段带内联「说人话」提示,但数值(涨跌/%B/费率)照喂给定值不改。
    ★style=x_short:收尾指令换成『冷静克制但说人话的超短推 ≤110 字·结尾带不构成投资建议』
      (system 已定调口语化+精简免责,这里对齐)。
    """
    zone = ctx.zone_label
    if ctx.pct_b is not None:
        zone += f"(%B={ctx.pct_b:.2f} · 越近 0 越贴下轨、越近 1 越贴上轨)"
    lines = [
        f"币种:{ctx.symbol}(加密永续)",
        f"结构倾向(布林):{ctx.bias}(偏多=偏强 / 偏空=偏弱 / 中性=震荡)",
        f"当前结构:{ctx.state_label}",
        f"通道位置:{zone}",
        f"最新价:{_fmt(ctx.price)}",
        f"24h 涨跌幅:{_fmt(ctx.change_pct_24h, pct=True)}(如实报这个数 · 别编)",
    ]
    if ctx.funding_rate is not None:
        lines.append(f"资金费率:{ctx.funding_rate * 100:+.4f}%(正=多头成本高 / 负=空头成本高)")
    # ★刀2 扩数据(取不到=不喂那条·优雅降级·不显「—」)
    if ctx.oi_usd is not None:
        lines.append(f"OI 持仓量:{_fmt_usd(ctx.oi_usd)}")
    if ctx.oi_change_pct_24h is not None:
        lines.append(
            f"OI 24h 变化:{ctx.oi_change_pct_24h:+.1f}%"
            "(缩=资金离场·说仓单降/持仓缩·★别用「减仓/加仓」是禁词)",
        )
    if ctx.long_short_ratio is not None:
        lines.append(f"多空比(全市场人数):{ctx.long_short_ratio:.2f}(>1 多头人多 / <1 空头人多)")
    if ctx.change_pct_15m is not None:
        lines.append(f"15 分钟涨跌:{ctx.change_pct_15m:+.2f}%(如实报 · 别编)")
    if ctx.volume_ratio is not None:
        lines.append(f"15 分钟成交量:约近期均量的 {ctx.volume_ratio:.1f} 倍")
    if style == "x_short":
        lines.append(
            "\n把以上【当前】状态写成一条【冷静克制但说人话】的超短推:像真人扫一眼盘跟朋友唠、"
            "犀利但不惊悚、不渲染情绪、只讲此刻、不揣测之后、不暗示操作、★连同免责 ≤110 中文字、"
            "结尾带『不构成投资建议』、绝不放链接(遵守 system 全部规则)。",
        )
    else:
        lines.append(
            "\n把以上【当前】状态写成一条散户秒懂的口语盯盘短帖:说人话、带点情绪、只讲此刻、"
            "不揣测之后、不暗示操作、结尾带『仅供参考,不构成投资建议』(遵守 system 全部规则)。",
        )
    return "\n".join(lines)


_BRAND_TAG = "#点金Midas"
_CATEGORY_TAG = "#加密货币"  # X 短推第二标签用话题类(蹭话题利传播·Hans 定)


def coin_tag(symbol: str) -> str:
    """币种标签:symbol 去 USDT/USD 后缀 + 大写 → #BTC / #ETH / #SIREN。"""
    base = symbol.upper().removesuffix("USDT").removesuffix("USD") or symbol.upper()
    return f"#{base}"


def append_tags(text: str, symbol: str, style: str = "default") -> str:
    """末尾拼接 #币种 + 第二标签(★代码侧 · 纯标识不含违规词/不触发门禁 · ★绝不含链接)。

    default(币安长文)→ 第二标签 #点金Midas(品牌);x_short(X)→ #加密货币(话题·利 X 传播)。
    """
    second = _CATEGORY_TAG if style == "x_short" else _BRAND_TAG
    return f"{text.rstrip()}\n{coin_tag(symbol)} {second}"


async def generate_tweet_text(ctx: TweetContext, style: str = "default") -> LLMResponse:
    """调 DeepSeek(无 key 自动 mock)生成推文文本 · style 选平台风格(default 长文 / x_short 短推)。

    ★只生成,不过门禁(门禁由调用方 compliance.validate_tweet 做)· 不发 X、不写库。
    """
    return await ainvoke(build_user_prompt(ctx, style), system=build_system_prompt(style))
