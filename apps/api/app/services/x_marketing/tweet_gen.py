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
    "你是加密永续技术分析编辑,为点金 Midas 写中文 X(推特)帖。"
    "你【只】客观描述给定的【当前】技术结构事实,绝不预测未来、不给操作建议。\n"
    "★推文分三层(让普通人和懂行的都看得懂):\n"
    "  ① 开头一句【大白话结论】:普通人秒懂的当前状态,例如『BTC 短期偏强、价格高位运行』"
    "『ETH 横盘震荡、方向不明』『SIREN 持续走弱』(偏强/偏弱/震荡 = 偏多/偏空/中性 的通俗说法);\n"
    "  ② 中间【专业技术分析】:布林 / MACD / 缠论 / %B 等(给懂行的人,术语该留则留);\n"
    "  ③ 结尾免责:『仅供参考,不构成投资建议』。\n"
    "硬性规则(违者作废 · ★大白话开头和专业部分【一样严】):\n"
    "1. 倾向只能用『偏多/偏空/中性』及通俗版『偏强/偏弱/震荡』,禁『看涨/将涨/突破在即』等预测词;\n"
    "2. 禁止任何买卖引导(买入/卖出/建议/抄底/止损/加仓/布局/上车…)、目标价、收益承诺;\n"
    "3. 禁止未来时态(即将/将会/有望/预计/后市…),只陈述此刻;可如实报 24h 涨跌幅(事实)但不据此预测;\n"
    "4. ★用词偏好(从源头用最中性的说法):空头/多头动能强(而非『做空情绪浓』)、处于低位/运行于下轨"
    "(而非『已跌至低位』)、近上轨/上轨上方(而非『突破』);少碰边界词;\n"
    "5. 不要自己加话题标签 #(由系统统一拼接);整体通俗易懂,中文,300–480 字,结尾必须带免责。"
)


def build_system_prompt() -> str:
    """system prompt(纯函数 · 可单测)。"""
    return _SYSTEM


def _fmt(v: float | None, suffix: str = "", pct: bool = False) -> str:
    if v is None:
        return "—"
    return f"{v:+.2f}%" if pct else f"{v:g}{suffix}"


def build_user_prompt(ctx: TweetContext) -> str:
    """user prompt(纯函数 · 可单测)· 只喂【当前】结构事实,不喂任何预测倾向。"""
    lines = [
        f"币种:{ctx.symbol}(加密永续)",
        f"结构倾向(布林):{ctx.bias}",
        f"当前结构:{ctx.state_label}",
        f"通道位置:{ctx.zone_label}" + (f"(%B={ctx.pct_b:.2f})" if ctx.pct_b is not None else ""),
        f"最新价:{_fmt(ctx.price)}",
        f"24h 涨跌幅:{_fmt(ctx.change_pct_24h, pct=True)}",
    ]
    if ctx.funding_rate is not None:
        lines.append(f"资金费率:{ctx.funding_rate * 100:+.4f}%")
    lines.append("\n据以上【当前事实】写一条合规技术分析推文(遵守 system 全部规则)。")
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
