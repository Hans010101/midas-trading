"""ValidatorNode · 0012 ADR § disclaimer 强制嵌入 + 祈使句改写。

红线 ②(产品负责人 2026-05-20):
  决策卡里不出现「建议买入/卖出」这种祈使句 · 只做「分析」和「评分」。

实现策略:
  - regex 检测禁用词(「建议买入」「建议卖出」「应该买」「快入场」等)
  - 命中改写为陈述句(「建议买入」→「分析显示买入信号」)
  - LLM 也可能不老实 · 双层兜底:即使 system prompt 让 LLM 别说,
    也要在 Python 这一层拦截一次

★i18n(2026-07)· 语言感知(0012 英文对等):所有公开函数加 `language` 参数(默认 'zh')·
  ★zh 路径行为【一字不变】(向后兼容·现有 8 处消费方不传 language 自然走 zh)·
  en 路径走英文禁词/改写表 + case-insensitive 匹配(英文有大小写·中文没有)·
  英文免责固定串 ADVISORY_DISCLAIMER_EN(与 landing footer 统一一套)。

测试:test_validator.py(中文)· test_validator_en.py(英文镜像 + 中文向后兼容)。
"""

from __future__ import annotations

import re

# ============================================================================
# 中文(★现有逻辑·一字不变)
# ============================================================================

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

# 违规营销话术 → 中性表述 · 长串优先匹配
_MARKETING_REPLACEMENTS: list[tuple[str, str]] = [
    ("稳赚不赔", "存在波动风险"),
    ("保证收益", "收益不确定"),
    ("保证盈利", "盈亏不确定"),
    ("一夜暴富", "理性看待收益"),
    ("稳定盈利", "盈亏不确定"),
    ("零风险", "有风险"),
    ("无风险", "有风险"),
    ("稳赚", "有波动"),
    ("保本", "本金有风险"),
    ("包赚", "盈亏自负"),
    ("躺赚", "需自行判断"),
    ("必涨", "可能上涨"),
    ("必跌", "可能下跌"),
    ("百分百", "并非确定"),
]

_MARKETING_KEYWORDS: tuple[str, ...] = tuple(k for k, _ in _MARKETING_REPLACEMENTS)

# ============================================================================
# 英文(★i18n 对等·case-insensitive·长串优先)
# ============================================================================

# ★英文免责固定串(与 landing footer 统一一套·锁死·不让 LLM 自由生成)
ADVISORY_DISCLAIMER_EN = (
    "For informational purposes only and does not constitute investment advice."
)

# 英文祈使 → 陈述(长串优先·case-insensitive 匹配)
_REPLACEMENTS_EN: list[tuple[str, str]] = [
    ("you should buy", "there may be a buy setup"),
    ("you should sell", "there may be a sell setup"),
    ("should buy now", "a buy signal is present"),
    ("should sell now", "a sell signal is present"),
    ("should buy", "a possible buy opportunity"),
    ("should sell", "a possible sell risk"),
    ("must buy", "a strong buy signal"),
    ("must sell", "a strong sell signal"),
    ("buy immediately", "a buy signal has appeared"),
    ("sell immediately", "a sell signal has appeared"),
    ("buy right now", "a buy signal is present"),
    ("sell right now", "a sell signal is present"),
    ("buy now", "a buy signal is present"),
    ("sell now", "a sell signal is present"),
    ("time to buy", "a buy signal is present"),
    ("time to sell", "a sell signal is present"),
    ("go long now", "a long setup is present"),
    ("go short now", "a short setup is present"),
]

_IMPERATIVE_KEYWORDS_EN: tuple[str, ...] = (
    "should buy",
    "should sell",
    "must buy",
    "must sell",
    "buy now",
    "sell now",
    "buy immediately",
    "sell immediately",
    "time to buy",
    "time to sell",
    "go long now",
    "go short now",
)

# 英文违规营销 → 中性(多词短语·避免 moon/pump 裸词误伤)
_MARKETING_REPLACEMENTS_EN: list[tuple[str, str]] = [
    ("guaranteed profit", "returns are uncertain"),
    ("guaranteed profits", "returns are uncertain"),
    ("guaranteed returns", "returns are uncertain"),
    ("guaranteed gains", "gains are uncertain"),
    ("risk-free", "carries risk"),
    ("risk free", "carries risk"),
    ("zero risk", "carries risk"),
    ("no risk", "carries risk"),
    ("sure win", "the outcome is uncertain"),
    ("sure thing", "the outcome is uncertain"),
    ("can't lose", "may incur losses"),
    ("cannot lose", "may incur losses"),
    ("get rich quick", "consider returns rationally"),
    ("easy money", "requires your own judgment"),
    ("to the moon", "may rise"),
    ("guaranteed pump", "may move"),
    ("moonshot", "high-variance"),
]

_MARKETING_KEYWORDS_EN: tuple[str, ...] = tuple(k for k, _ in _MARKETING_REPLACEMENTS_EN)


# ── 英文内部工具(case-insensitive) ──────────────────────────────────────


def _contains_en(text: str, keywords: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(kw in low for kw in keywords)


def _apply_en(text: str, replacements: list[tuple[str, str]]) -> str:
    """case-insensitive 替换(保留替换词原样)· 幂等(替换词不含被替换的禁词)。"""
    out = text
    for needle, repl in replacements:
        out = re.sub(re.escape(needle), repl, out, flags=re.IGNORECASE)
    return out


# ============================================================================
# 公开 API · 语言感知(默认 zh · 向后兼容)
# ============================================================================


def has_imperative(text: str, language: str = "zh") -> bool:
    """检测文本是否含祈使句 · 用于测试断言。language='en' 走英文关键词(case-insensitive)。"""
    if language == "en":
        return _contains_en(text, _IMPERATIVE_KEYWORDS_EN)
    return any(kw in text for kw in _IMPERATIVE_KEYWORDS)


def rewrite_imperatives(text: str, language: str = "zh") -> str:
    """改写祈使句为陈述句 · 0012 红线 ② · 幂等。

    ★zh 路径行为一字不变;en 路径走英文表(case-insensitive)。
    """
    if language == "en":
        return _apply_en(text, _REPLACEMENTS_EN)
    out = text
    for needle, replace_with in _REPLACEMENTS:
        out = out.replace(needle, replace_with)
    return out


# regex 版本(辅助 · 用于将来扩展更复杂模式)· M1 二波先用上面的简单 str.replace
_VERB_IMPERATIVE_RE = re.compile(
    r"(?<![分析显示可能存在])(?:买入|卖出|清仓|加仓|减仓)(?=[!,。;])",
)


def has_naked_imperative_verb(text: str) -> bool:
    """检测裸动词命令(如「买入!」)· 给 M2+ 复杂检测留口。(中文专用·英文暂不需要)"""
    return bool(_VERB_IMPERATIVE_RE.search(text))


def has_marketing_violation(text: str, language: str = "zh") -> bool:
    """检测违规营销话术(稳赚 / 保证收益 / 无风险 / 诱导等)· 任何模式都禁。

    language='en' 走英文营销禁词(guaranteed profit / risk-free / sure win 等 · case-insensitive)。
    """
    if language == "en":
        return _contains_en(text, _MARKETING_KEYWORDS_EN)
    return any(kw in text for kw in _MARKETING_KEYWORDS)


def scrub_marketing(text: str, language: str = "zh") -> str:
    """清除违规营销话术 → 中性表述 · 幂等。★zh 一字不变;en 走英文表(case-insensitive)。"""
    if language == "en":
        return _apply_en(text, _MARKETING_REPLACEMENTS_EN)
    out = text
    for needle, repl in _MARKETING_REPLACEMENTS:
        out = out.replace(needle, repl)
    return out


def validate_advisory(text: str, language: str = "zh") -> str:
    """AI 模拟交易 advisory 模式(0036 批次甲拍板②):

    ★ 放开 actionable —— 不改写祈使句(与 strict 的 rewrite_imperatives 区分);
    但仍清除违规营销话术(红线不放松)。现有只读决策卡 narrator 不走这条、保持 strict。
    language='en' 走英文营销禁词。
    """
    return scrub_marketing(text, language=language)


def ensure_advisory_disclaimer_en(text: str) -> str:
    """英文兜底:确保文本含英文免责固定串·缺则末尾追加(类比中文 boll_state 的免责兜底)。

    ★英文 AI 输出上线前的合规兜底:即使 LLM 没带免责,Python 这层补上固定串。
    """
    if ADVISORY_DISCLAIMER_EN in text or "does not constitute investment advice" in text:
        return text
    sep = "" if text.endswith(("\n", " ")) or not text else " "
    return text + sep + ADVISORY_DISCLAIMER_EN


__all__ = [
    "ADVISORY_DISCLAIMER_EN",
    "ensure_advisory_disclaimer_en",
    "has_imperative",
    "has_marketing_violation",
    "has_naked_imperative_verb",
    "rewrite_imperatives",
    "scrub_marketing",
    "validate_advisory",
]
