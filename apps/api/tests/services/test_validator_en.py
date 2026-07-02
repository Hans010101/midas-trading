"""validator 语言感知 · 英文镜像 + ★中文向后兼容 · pytest(纯函数·本地秒级)。

覆盖(镜像中文校验场景 → 英文对应):
- 祈使改写(should buy → 陈述)· has_imperative 检测 · 幂等 · case-insensitive
- 营销清除(guaranteed profit/risk-free → 中性)· has_marketing_violation · 幂等
- validate_advisory(en):放开 actionable 仍清营销
- 英文免责固定串 + ensure 兜底(缺则补·幂等·串本身无禁词)
- ★★向后兼容:zh 路径行为一字不变(默认 zh == 显式 zh == 旧行为)
"""

from __future__ import annotations

from app.services.ai import validator as v

# ── 英文:祈使改写 ────────────────────────────────────────────────────


def test_en_rewrite_imperatives_removes_guidance():
    out = v.rewrite_imperatives("You should buy now, must sell later.", language="en")
    assert v.has_imperative(out, language="en") is False
    assert "should buy" not in out.lower()
    assert "must sell" not in out.lower()


def test_en_has_imperative_detects():
    assert v.has_imperative("This is a buy now moment", language="en") is True
    assert v.has_imperative("The RSI reads 72", language="en") is False


def test_en_rewrite_case_insensitive():
    for variant in ("BUY NOW", "Buy Now", "buy now"):
        out = v.rewrite_imperatives(f"Signal: {variant}!", language="en")
        assert "buy now" not in out.lower()


def test_en_rewrite_idempotent():
    once = v.rewrite_imperatives("You should sell immediately.", language="en")
    twice = v.rewrite_imperatives(once, language="en")
    assert once == twice


# ── 英文:营销清除 ────────────────────────────────────────────────────


def test_en_scrub_marketing_neutralizes():
    out = v.scrub_marketing("Guaranteed profit, risk-free, sure win!", language="en")
    assert v.has_marketing_violation(out, language="en") is False
    low = out.lower()
    assert "guaranteed profit" not in low
    assert "risk-free" not in low
    assert "sure win" not in low


def test_en_has_marketing_violation():
    assert v.has_marketing_violation("This is guaranteed profit", language="en") is True
    assert v.has_marketing_violation("Returns are uncertain", language="en") is False


def test_en_scrub_marketing_idempotent():
    once = v.scrub_marketing("No risk, easy money, to the moon", language="en")
    assert v.scrub_marketing(once, language="en") == once


# ── 英文:advisory(放开 actionable · 仍清营销)─────────────────────────


def test_en_validate_advisory_keeps_actionable_scrubs_marketing():
    text = "Consider a long entry near 100. Guaranteed profit."
    out = v.validate_advisory(text, language="en")
    # actionable(long entry)保留 · 营销(guaranteed profit)清除
    assert "long entry" in out.lower()
    assert v.has_marketing_violation(out, language="en") is False


# ── 英文:免责固定串 ──────────────────────────────────────────────────


def test_en_disclaimer_string_is_clean():
    d = v.ADVISORY_DISCLAIMER_EN
    assert "does not constitute investment advice" in d
    # 免责串本身不得含禁词
    assert v.has_imperative(d, language="en") is False
    assert v.has_marketing_violation(d, language="en") is False


def test_en_ensure_disclaimer_appends_when_missing():
    out = v.ensure_advisory_disclaimer_en("RSI reads 72; momentum is bullish.")
    assert v.ADVISORY_DISCLAIMER_EN in out


def test_en_ensure_disclaimer_idempotent():
    once = v.ensure_advisory_disclaimer_en("Momentum is bullish.")
    assert v.ensure_advisory_disclaimer_en(once) == once


# ── ★★中文向后兼容:zh 路径行为一字不变 ──────────────────────────────


def test_zh_backward_compat_default_equals_explicit():
    # 默认(不传 language)== 显式 zh · 且 == 旧固定输出
    assert v.rewrite_imperatives("建议买入") == "分析显示买入信号"
    assert v.rewrite_imperatives("建议买入", language="zh") == "分析显示买入信号"
    assert v.rewrite_imperatives("应该卖出") == "可能存在卖出风险"


def test_zh_backward_compat_marketing():
    assert v.scrub_marketing("稳赚不赔") == "存在波动风险"
    assert v.has_marketing_violation("保证收益") is True
    assert v.has_imperative("建议加仓") is True


def test_zh_backward_compat_advisory():
    # advisory 放开祈使(不改写)· 仍清营销 · 默认 zh
    out = v.validate_advisory("可考虑买入,稳赚不赔")
    assert "买入" in out  # actionable 保留
    assert "稳赚不赔" not in out  # 营销清除
