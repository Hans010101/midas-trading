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


_SYSTEM = (
    "你是点金 Midas 的加密盯盘小编,给普通散户写中文短帖(发币安广场 / X)。"
    "说人话、有画面、带点情绪,像老盘手发朋友圈那样——但【只讲此刻的状态】,绝不预测、绝不教人操作。\n"
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
    "【风格】短句为主、口语、有网感;开头一句大白话结论让人秒懂现在啥状态;"
    "再自然带出布林 / %B / 涨跌 / 费率这几点(★给了才说,没给的别提也别说『没数据』);"
    "中文,约 280–460 字。\n"
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


def build_system_prompt() -> str:
    """system prompt(纯函数 · 可单测)。"""
    return _SYSTEM


def _fmt(v: float | None, suffix: str = "", pct: bool = False) -> str:
    if v is None:
        return "—"
    if pct:
        return f"{v:+.2f}%"
    # ★价格避免科学计数法(极小价 1.2e-05 → 0.000012·口语文案不出戏):<1 定点去尾零、≥1 用 g
    s = f"{v:.10f}".rstrip("0").rstrip(".") if abs(v) < 1 else f"{v:g}"
    return f"{s}{suffix}"


def build_user_prompt(ctx: TweetContext) -> str:
    """user prompt(纯函数 · 可单测)· 只喂【当前】结构事实,不喂任何预测倾向。

    ★口语化(PR·刀1):字段带内联「说人话」提示,但数值(涨跌/%B/费率)照喂给定值不改。
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
    lines.append(
        "\n把以上【当前】状态写成一条散户秒懂的口语盯盘短帖:说人话、带点情绪、只讲此刻、"
        "不揣测之后、不暗示操作、结尾带『仅供参考,不构成投资建议』(遵守 system 全部规则)。",
    )
    return "\n".join(lines)


_BRAND_TAG = "#点金Midas"


def coin_tag(symbol: str) -> str:
    """币种标签:symbol 去 USDT/USD 后缀 + 大写 → #BTC / #ETH / #SIREN。"""
    base = symbol.upper().removesuffix("USDT").removesuffix("USD") or symbol.upper()
    return f"#{base}"


def append_tags(text: str, symbol: str) -> str:
    """末尾拼接 #币种 + #点金Midas(★代码侧 · 不依赖 AI · 标签纯标识不含违规词,不触发门禁)。"""
    return f"{text.rstrip()}\n{coin_tag(symbol)} {_BRAND_TAG}"


async def generate_tweet_text(ctx: TweetContext) -> LLMResponse:
    """调 DeepSeek(无 key 自动 mock)生成推文文本 · 返回 LLMResponse(.text / .is_mock)。

    ★只生成,不过门禁(门禁由调用方 compliance.validate_tweet 做)· 不发 X、不写库。
    """
    return await ainvoke(build_user_prompt(ctx), system=build_system_prompt())
