"""X 推文真 DeepSeek 验证 · ★自包含版(不依赖 app.services.x_marketing,可在生产 api 容器直接跑)。

x_marketing 模块只在分支、没进生产容器(跑 main)→ 原 x_tweet_poc.py import 报 ModuleNotFound。
本脚本把【门禁 / prompt / 形态数据】全内联(= 分支 x_marketing 逻辑逐字拷贝),只 import 容器 main 已有的
ai.llm(ainvoke/is_mock_mode · 真 DeepSeek)+ ai.validator(has_marketing_violation)→ 真生成 + 真门禁,
★不往容器塞模块、跑完即净、不碰 main/部署。运行命令见任务回复(git show → docker cp → exec)。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.services.ai.llm import ainvoke, is_mock_mode
from app.services.ai.validator import has_marketing_violation

# ════════ 门禁(内联 · = x_marketing/compliance.py validate_tweet)════════
_ACTION_WORDS: tuple[str, ...] = (
    "建议", "买入", "卖出", "买进", "卖掉", "抄底", "逃顶", "目标价", "目标位",
    "止损", "止盈", "做多", "做空", "加仓", "减仓", "建仓", "清仓", "梭哈", "满仓",
    "重仓", "上车", "布局", "吸纳", "可关注", "入场", "进场", "离场", "埋伏", "潜伏",
    "buy", "sell", "long", "short",
)
_PREDICTION_WORDS: tuple[str, ...] = (
    "暴涨", "暴跌", "大涨", "大跌", "将涨", "将跌", "会涨", "会跌", "要涨", "要跌",
    "看涨", "看跌", "续涨", "续跌", "补涨", "涨到", "跌到", "涨至", "跌至", "上看", "下看",
    "突破", "破位", "拉升", "冲高", "冲顶", "探底", "启动", "翻倍", "新高", "新低",
    "即将", "将要", "将会", "有望", "料将", "预计", "后市", "下一步", "未来", "接下来",
)
_PROFIT_WORDS: tuple[str, ...] = (
    "翻倍", "稳赚", "保本", "收益率", "回报率", "躺赚", "财富自由", "一夜暴富", "百倍", "十倍",
)
_DISCLAIMERS: tuple[str, ...] = (
    "仅供参考", "不构成投资建议", "非投资建议", "风险自担", "自行决策",
)
_MAX_LEN = 700


def _hits(text: str, words: tuple[str, ...]) -> list[str]:
    return [w for w in words if w in text]


def validate_tweet(text: str) -> tuple[bool, list[str]]:
    """= compliance.validate_tweet · 返回 (passed, reasons)。营销+声明查原文,其余查剥声明后 body。"""
    raw = (text or "").strip()
    reasons: list[str] = []
    if not raw:
        return False, ["空文本"]
    if has_marketing_violation(raw):
        reasons.append("营销违规话术(稳赚/保证收益/无风险等)")
    if not any(d in raw for d in _DISCLAIMERS):
        reasons.append("缺免责声明(需含 仅供参考 / 不构成投资建议)")
    body = raw
    for disc in _DISCLAIMERS:
        body = body.replace(disc, "")
    if hits := _hits(body, _ACTION_WORDS):
        reasons.append(f"买卖引导词:{'/'.join(hits)}")
    if hits := _hits(body, _PREDICTION_WORDS):
        reasons.append(f"预测未来走势词:{'/'.join(hits)}")
    if hits := _hits(body, _PROFIT_WORDS):
        reasons.append(f"收益承诺词:{'/'.join(hits)}")
    if len(raw) > _MAX_LEN:
        reasons.append(f"过长({len(raw)} 字 · 超 {_MAX_LEN})")
    return not reasons, reasons


# ════════ prompt + 形态数据(内联 · = x_marketing/tweet_gen.py)════════
_SYSTEM = (
    "你是加密永续技术分析编辑,为点金 Midas 写中文 X(推特)帖。"
    "你【只】客观描述给定的【当前】技术结构事实,绝不预测未来、不给操作建议。\n"
    "硬性规则(违者作废):\n"
    "1. 倾向只能用『偏多/偏空/中性』三档(对齐布林口径),不得用『看涨/将涨/突破在即』等预测词;\n"
    "2. 禁止任何买卖引导(买入/卖出/建议/抄底/止损/加仓/布局/上车…)、目标价、收益承诺;\n"
    "3. 禁止未来时态主导(即将/将会/有望/预计/后市…),只陈述此刻结构;\n"
    "4. 可如实报 24h 涨跌幅(事实),但不得据此预测后续涨跌;\n"
    "5. 结尾必须附一句免责:『仅供参考,不构成投资建议』;\n"
    "6. 简洁专业,中文,280–460 字,开头点币种+核心结构,中间技术要点,结尾免责。"
)


@dataclass(frozen=True)
class Ctx:
    symbol: str
    price: float
    change_pct_24h: float
    bias: str
    state_label: str
    zone_label: str
    pct_b: float
    funding_rate: float


def build_user_prompt(c: Ctx) -> str:
    return (
        f"币种:{c.symbol}(加密永续)\n"
        f"结构倾向(布林):{c.bias}\n"
        f"当前结构:{c.state_label}\n"
        f"通道位置:{c.zone_label}(%B={c.pct_b:.2f})\n"
        f"最新价:{c.price:g}\n"
        f"24h 涨跌幅:{c.change_pct_24h:+.2f}%\n"
        f"资金费率:{c.funding_rate * 100:+.4f}%\n"
        "\n据以上【当前事实】写一条合规技术分析推文(遵守 system 全部规则)。"
    )


# 形态数据(mock · 重点是真 DeepSeek 生成 + 真门禁;3 种倾向各一)
_CTX = [
    Ctx("BTCUSDT", 61744.1, 3.2, "偏多", "三线齐上·上升结构", "近上轨", 0.92, 0.0001),
    Ctx("ETHUSDT", 2980.5, -2.1, "中性", "三线走平·震荡结构", "近中轨", 0.48, -0.00005),
    Ctx("SIRENUSDT", 0.0362, -8.4, "偏空", "带宽开口·向下", "破下轨", 0.0, 0.0003),
]


async def main() -> None:
    mode = "MOCK(★容器没读到 DEEPSEEK_API_KEY!)" if is_mock_mode() else "真 DeepSeek"
    print(f"LLM 模式:{mode}\n" + "=" * 70)
    for c in _CTX:
        resp = await ainvoke(build_user_prompt(c), system=_SYSTEM)
        passed, reasons = validate_tweet(resp.content)
        verdict = "✅ 通过" if passed else f"❌ 否决 · {' | '.join(reasons)}"
        src = "mock" if resp.is_mock else "DeepSeek"
        print(f"\n── {c.symbol}({c.bias} · {c.state_label})  [{src}]")
        print(f"  推文:{resp.content}")
        print(f"  门禁:{verdict}")


if __name__ == "__main__":
    asyncio.run(main())
