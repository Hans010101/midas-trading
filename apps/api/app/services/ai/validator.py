"""ValidatorNode · 0012 ADR § disclaimer 强制嵌入 + 祈使句改写。

红线 ②(产品负责人 2026-05-20):
  决策卡里不出现「建议买入/卖出」这种祈使句 · 只做「分析」和「评分」。

实现策略:
  - regex 检测禁用词(「建议买入」「建议卖出」「应该买」「快入场」等)
  - 命中改写为陈述句(「建议买入」→「分析显示买入信号」)
  - LLM 也可能不老实 · 双层兜底:即使 system prompt 让 LLM 别说,
    也要在 Python 这一层拦截一次

测试:test_validator.py 给一段含祈使句的假文本,验证改写正确。
"""

from __future__ import annotations

import re

# 祈使句 → 陈述句替换表
# 按长度降序匹配,长串优先(避免「建议买入」被先替换成「分析显示」+「买入」)
_REPLACEMENTS: list[tuple[str, str]] = [
    # 直接建议类
    ("建议立即买入", "分析显示买入信号已出现"),
    ("建议立即卖出", "分析显示卖出信号已出现"),
    ("建议买入", "分析显示买入信号"),
    ("建议卖出", "分析显示卖出信号"),
    ("建议加仓", "分析显示可能存在加仓机会"),
    ("建议减仓", "分析显示可能存在减仓需求"),
    ("建议持有", "分析显示当前以持有观察为宜"),
    ("建议清仓", "分析显示存在清仓信号"),
    ("建议", "分析显示"),
    # 应该 / 必须 类
    ("应该买入", "可能存在买入机会"),
    ("应该卖出", "可能存在卖出风险"),
    ("应该加仓", "可能存在加仓机会"),
    ("应该减仓", "可能存在减仓需求"),
    ("必须买入", "买入信号显著"),
    ("必须卖出", "卖出信号显著"),
    ("应该", "可能"),
    ("必须", "需要关注"),
    # 紧迫类
    ("快入场", "可关注入场时机"),
    ("快出场", "可关注出场时机"),
    ("立刻买入", "买入信号已现"),
    ("立刻卖出", "卖出信号已现"),
    ("赶紧买", "买入信号已现"),
    ("赶紧卖", "卖出信号已现"),
    # 命令式 · 直接动词开头
    ("快买", "买入信号已现"),
    ("快卖", "卖出信号已现"),
]

# 仅用于 has_imperative 检测的关键词集合 · 不参与替换
_IMPERATIVE_KEYWORDS: tuple[str, ...] = (
    "建议",
    "应该",
    "必须",
    "快入场",
    "快出场",
    "立刻买",
    "立刻卖",
    "赶紧买",
    "赶紧卖",
    "快买",
    "快卖",
)


def has_imperative(text: str) -> bool:
    """检测文本是否含祈使句 · 用于测试断言。"""
    return any(kw in text for kw in _IMPERATIVE_KEYWORDS)


def rewrite_imperatives(text: str) -> str:
    """改写祈使句为陈述句 · 0012 红线 ②。

    幂等 · 多次调用结果一致。
    """
    out = text
    for needle, replace_with in _REPLACEMENTS:
        out = out.replace(needle, replace_with)
    return out


def ensure_disclaimer(text: str) -> str:
    """确保文本末尾带 disclaimer · 给某些场景兜底用(API response 字段是主防线)。"""
    disclaimer = "仅供参考,不构成投资建议"
    if disclaimer in text:
        return text
    return f"{text.rstrip()}\n\n{disclaimer}"


# regex 版本(辅助 · 用于将来扩展更复杂模式)· M1 二波先用上面的简单 str.replace
_VERB_IMPERATIVE_RE = re.compile(
    r"(?<![分析显示可能存在])(?:买入|卖出|清仓|加仓|减仓)(?=[!,。;])",
)


def has_naked_imperative_verb(text: str) -> bool:
    """检测裸动词命令(如「买入!」)· 给 M2+ 复杂检测留口。"""
    return bool(_VERB_IMPERATIVE_RE.search(text))


__all__ = [
    "ensure_disclaimer",
    "has_imperative",
    "has_naked_imperative_verb",
    "rewrite_imperatives",
]
