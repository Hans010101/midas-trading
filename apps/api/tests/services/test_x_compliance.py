"""X 推文合规门禁单测(阶段2 核心)· ★违禁必拦 + 合规必过 + 事实涨跌不误杀 + 营销对原文。"""

from __future__ import annotations

import pytest

from app.services.x_marketing.compliance import validate_tweet
from app.services.x_marketing.tweet_gen import (
    TweetContext,
    build_system_prompt,
    build_user_prompt,
)

# 合规范例(开头币种+结构 · 中间技术 · 结尾免责 · 含 24h涨跌幅【事实】· 无预测/买卖/收益)
_OK = (
    "$BTC 当前布林结构偏多,三线齐上呈上升结构,价格运行于上轨附近(%B=0.92)。"
    "MACD 红柱温和、DIF 在零轴上方;缠论笔向上、中枢上沿。24h 涨跌幅 +3.20%。"
    "以上为当前结构描述。仅供参考,不构成投资建议。"
)


def test_compliant_tweet_passes() -> None:
    r = validate_tweet(_OK)
    assert r.passed, r.reasons


def test_factual_change_not_over_blocked() -> None:
    # ★关键:含「24h 涨跌幅 +5.2%」「下跌 2%」等【事实】涨跌字样,不该被误杀(没拉黑裸 涨/跌)
    t = (
        "$ETH 当前结构中性,三线走平呈震荡结构,价格近中轨(%B=0.48)。"
        "24h 涨跌幅 -2.10%,资金费率 +0.0100%。以上为当前结构。仅供参考,不构成投资建议。"
    )
    assert validate_tweet(t).passed, validate_tweet(t).reasons


@pytest.mark.parametrize(
    ("bad", "kw"),
    [
        ("$BTC 偏多,建议逢低买入,止损设在下轨。仅供参考,不构成投资建议。", "买入"),
        ("$ETH 偏多,可关注布局机会,适合上车。仅供参考,不构成投资建议。", "布局"),
    ],
)
def test_action_words_blocked(bad: str, kw: str) -> None:
    r = validate_tweet(bad)
    assert not r.passed
    assert any("买卖引导" in x for x in r.reasons)
    assert any(kw in x for x in r.reasons)


@pytest.mark.parametrize(
    "bad",
    [
        "$ETH 即将突破前高,看涨。仅供参考,不构成投资建议。",
        "$BTC 偏多,预计后市冲高,目标上看 7 万。仅供参考,不构成投资建议。",
        "$SOL 短线将涨,涨到 200 概率大。仅供参考,不构成投资建议。",
    ],
)
def test_prediction_words_blocked(bad: str) -> None:
    r = validate_tweet(bad)
    assert not r.passed
    assert any("预测未来" in x for x in r.reasons)


def test_breakout_statement_not_blocked() -> None:
    # ★门禁微调:陈述性「无突破/未突破/突破信号」是当前事实 · 不该被预测词误杀(ETHUSDT 翻车修复)
    for t in (
        "$ETH 当前结构中性,三线走平,暂无突破信号,价格近中轨。仅供参考,不构成投资建议。",
        "$BTC 偏多,价格运行于上轨上方,目前未突破前高区间。以上为现状。仅供参考,不构成投资建议。",
        "$SOL 偏空,带宽收口,尚未现突破。仅供参考,不构成投资建议。",
    ):
        r = validate_tweet(t)
        assert r.passed, (t, r.reasons)


@pytest.mark.parametrize(
    "bad",
    [
        "$ETH 偏多,即将突破前高。仅供参考,不构成投资建议。",
        "$BTC 偏多,向上突破在即。仅供参考,不构成投资建议。",
        "$SOL 偏多,有望突破上方阻力。仅供参考,不构成投资建议。",
    ],
)
def test_predictive_breakout_still_blocked(bad: str) -> None:
    # ★放宽不能漏放:未来/在即语境的突破仍一票否决
    r = validate_tweet(bad)
    assert not r.passed
    assert any("预测未来" in x for x in r.reasons)


def test_profit_promise_blocked() -> None:
    r = validate_tweet("$DOGE 偏多,持有有望翻倍,躺赚。仅供参考,不构成投资建议。")
    assert not r.passed
    assert any("收益承诺" in x for x in r.reasons) or any("营销违规" in x for x in r.reasons)


def test_missing_disclaimer_blocked() -> None:
    r = validate_tweet("$BTC 当前结构偏多,三线齐上,价格近上轨。以上为当前结构描述。")
    assert not r.passed
    assert any("免责声明" in x for x in r.reasons)


def test_marketing_checked_on_raw() -> None:
    # ★学做T教训:营销违规对【原文】检测 —— 即便带了免责声明,「稳赚不赔」仍一票否决
    r = validate_tweet("$BTC 偏多,稳赚不赔,放心拿。仅供参考,不构成投资建议。")
    assert not r.passed
    assert any("营销违规" in x for x in r.reasons)


def test_empty_blocked() -> None:
    assert validate_tweet("").passed is False
    assert validate_tweet("   ").passed is False


def test_multiple_reasons_collected() -> None:
    # 多维同时踩 → 全列出来(便于审计)
    r = validate_tweet("$BTC 建议买入,即将暴涨翻倍稳赚")  # 买卖+预测+收益+营销+无声明
    assert not r.passed
    assert len(r.reasons) >= 4


def test_prompt_builders() -> None:
    # system 含关键约束;user 含喂进去的当前事实
    sys = build_system_prompt()
    assert "偏多/偏空/中性" in sys
    assert "仅供参考" in sys
    assert "不预测" in sys or "绝不预测" in sys
    ctx = TweetContext(
        symbol="BTCUSDT", price=61744.1, change_pct_24h=3.2, bias="偏多",
        state_label="三线齐上·上升结构", zone_label="近上轨", pct_b=0.92, funding_rate=0.0001,
    )
    user = build_user_prompt(ctx)
    assert "BTCUSDT" in user
    assert "偏多" in user
    assert "三线齐上·上升结构" in user
    assert "+3.20%" in user
