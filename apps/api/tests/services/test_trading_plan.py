"""交易计划三价位规则算价 pytest · 纯函数(无 DB/Redis/LLM · 本地可跑)。

★ 重点:价位由规则算、不依赖 LLM;多/空价位有序;中性优雅 None;盈亏比计算正确。
"""

from __future__ import annotations

import pytest

from app.services.ai.trading_plan import compute_trading_plan, template_note

# 典型 crypto 小价标的(0.08 量级)· 布林 + 中枢 + ATR 齐全
_BOLL = {"upper": 0.095, "mid": 0.082, "lower": 0.070}
_KW = {
    "last_close": 0.085,
    "boll": _BOLL,
    "atr": 0.004,
    "zhongshu_high": 0.090,
    "zhongshu_low": 0.075,
}


def test_long_plan_prices_ordered():
    """看多(score≥20):入场区间 < 现价、止损 < 入场下沿、目标递增、盈亏比>0。"""
    plan = compute_trading_plan(score=65, **_KW)
    assert plan.direction == "long"
    assert plan.entry_low < plan.entry_high <= _KW["last_close"] + 1e-9  # 不追现价
    assert plan.stop < plan.entry_low                                    # 失效价在下方
    entry = (plan.entry_low + plan.entry_high) / 2
    assert plan.target1 > entry                                         # 目标在上方
    assert plan.target2 > plan.target1                                  # 双目标递增
    assert plan.risk_reward is not None
    assert plan.risk_reward > 0


def test_short_plan_prices_ordered():
    """看空(score≤-20):入场区间 > 现价、止损 > 入场上沿、目标递减、盈亏比>0。"""
    plan = compute_trading_plan(score=-65, **_KW)
    assert plan.direction == "short"
    assert plan.entry_high > plan.entry_low >= _KW["last_close"] - 1e-9  # 反弹进场
    assert plan.stop > plan.entry_high                                  # 失效价在上方
    entry = (plan.entry_low + plan.entry_high) / 2
    assert plan.target1 < entry                                         # 目标在下方
    assert plan.target2 < plan.target1                                  # 双目标递减
    assert plan.risk_reward is not None
    assert plan.risk_reward > 0


def test_neutral_plan_no_prices():
    """中性(-20<score<20):不给三价位(全 None)· 前端优雅降级。"""
    plan = compute_trading_plan(score=5, **_KW)
    assert plan.direction == "neutral"
    assert plan.entry_low is None
    assert plan.stop is None
    assert plan.target1 is None
    assert plan.risk_reward is None


def test_risk_reward_matches_formula():
    """盈亏比 = |(target1 - entry) / (entry - stop)|。"""
    plan = compute_trading_plan(score=70, **_KW)
    entry = (plan.entry_low + plan.entry_high) / 2
    expected = abs((plan.target1 - entry) / (entry - plan.stop))
    assert plan.risk_reward == pytest.approx(expected, abs=0.05)


def test_atr_zero_does_not_crash():
    """ATR=0(数据不足)→ 用现价 2% 兜底 · 不除零不崩。"""
    plan = compute_trading_plan(
        score=40, last_close=100.0, boll={"upper": 110, "mid": 100, "lower": 90},
        atr=0.0, zhongshu_high=None, zhongshu_low=None,
    )
    assert plan.direction == "long"
    assert plan.entry_low is not None
    assert plan.stop < plan.entry_low


def test_missing_zhongshu_falls_back_to_boll():
    """无中枢(None)→ 用布林轨/ATR 兜底 · 仍产出有序计划。"""
    plan = compute_trading_plan(
        score=-50, last_close=50.0, boll={"upper": 55, "mid": 50, "lower": 45},
        atr=1.0, zhongshu_high=None, zhongshu_low=None,
    )
    assert plan.direction == "short"
    assert plan.stop > plan.entry_high > plan.entry_low


def test_template_note_mentions_prices_and_no_imperative():
    """模板兜底解释:含真实价位 + 无祈使句(陈述)。"""
    plan = compute_trading_plan(score=65, **_KW)
    note = template_note(plan)
    assert str(plan.entry_low) in note
    assert str(plan.stop) in note
    for bad in ("建议买入", "建议卖出", "应该买", "快入场", "立刻下单"):
        assert bad not in note


def test_template_note_neutral():
    """中性模板:观望措辞 · 不崩。"""
    plan = compute_trading_plan(score=0, **_KW)
    assert "观望" in template_note(plan)
