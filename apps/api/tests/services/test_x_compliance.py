"""X 推文合规门禁单测(阶段2 核心)· ★违禁必拦 + 合规必过 + 事实涨跌不误杀 + 营销对原文。"""

from __future__ import annotations

import pytest

from app.services.x_marketing.compliance import has_body_url, validate_tweet
from app.services.x_marketing.tweet_gen import (
    TweetContext,
    append_tags,
    build_system_prompt,
    build_user_prompt,
    coin_tag,
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


def test_hedge_statement_not_blocked() -> None:
    # ★放宽:做空/做多 的【陈述市场状态】放行(做空情绪/空头动能/做多仓位)
    for t in (
        "$BTC 偏空,空头动能强、做空情绪升温,价格运行于下轨。仅供参考,不构成投资建议。",
        "$ETH 中性,多空力量均衡、做多仓位略增。以上为现状。仅供参考,不构成投资建议。",
    ):
        assert validate_tweet(t).passed, (t, validate_tweet(t).reasons)


@pytest.mark.parametrize(
    "bad",
    [
        "$BTC 偏空,建议做空。仅供参考,不构成投资建议。",
        "$ETH 偏空,可以做空,做空机会来了。仅供参考,不构成投资建议。",
        "$SOL 偏多,适合做多入场。仅供参考,不构成投资建议。",
    ],
)
def test_hedge_action_still_blocked(bad: str) -> None:
    # ★放宽不漏放:引导动作(建议做空/做空机会/适合做多)仍拦
    r = validate_tweet(bad)
    assert not r.passed
    assert any("做空/做多" in x or "买卖引导" in x for x in r.reasons)


def test_price_reached_statement_not_blocked() -> None:
    # ★放宽:已发生/当前的 跌至/涨至 放行(已跌至/回落至/运行至)
    for t in (
        "$SIREN 偏空,已跌至下轨附近,空头动能强。仅供参考,不构成投资建议。",
        "$BTC 偏多,价格回落至中轨后企稳。以上为现状。仅供参考,不构成投资建议。",
    ):
        assert validate_tweet(t).passed, (t, validate_tweet(t).reasons)


@pytest.mark.parametrize(
    "bad",
    [
        "$ETH 偏空,或跌至 2500。仅供参考,不构成投资建议。",
        "$BTC 偏多,有望涨至 7 万。仅供参考,不构成投资建议。",
    ],
)
def test_price_target_still_blocked(bad: str) -> None:
    # ★放宽不漏放:预测/目标的 跌至/涨至(或跌至/有望涨至)仍拦
    r = validate_tweet(bad)
    assert not r.passed
    assert any("涨至/跌至" in x or "预测未来" in x for x in r.reasons)


def test_tags_appended_and_pass_gate() -> None:
    # ★标签:#币种(去USDT)+ #点金Midas · 末尾拼接 · 不触发门禁
    base = "$BTC 当前偏多,三线齐上,近上轨。以上为现状。仅供参考,不构成投资建议。"
    tagged = append_tags(base, "BTCUSDT")
    assert tagged.endswith("#BTC #点金Midas")
    assert coin_tag("ETHUSDT") == "#ETH"
    assert coin_tag("SIRENUSDT") == "#SIREN"
    assert validate_tweet(tagged).passed, validate_tweet(tagged).reasons  # 标签不触发门禁


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


# ── 刀2:扩数据(5 新字段)prompt 渲染 + 优雅降级 ──────────────────────────
def test_build_user_prompt_extra_fields() -> None:
    """5 扩字段有值 → prompt 各自渲染(OI 亿/万单位·OI变化%·多空比·15m涨跌·量比)。"""
    ctx = TweetContext(
        symbol="GWEIUSDT", price=0.09, change_pct_24h=-28.0, bias="偏空",
        state_label="三线齐跌·下降结构", zone_label="近下轨", pct_b=0.08, funding_rate=0.00005,
        oi_usd=123_450_000, oi_change_pct_24h=-2.1, long_short_ratio=0.70,
        change_pct_15m=-3.5, volume_ratio=5.2,
    )
    u = build_user_prompt(ctx)
    assert "OI 持仓量:1.23 亿美元" in u
    assert "-2.1%" in u                          # OI 24h 变化
    assert "多空比(全市场人数):0.70" in u
    assert "15 分钟涨跌:-3.50%" in u
    assert "5.2 倍" in u


def test_build_user_prompt_extra_none_graceful() -> None:
    """★扩字段全 None → 不喂那几行(优雅降级·不显「—」·不报错)。"""
    ctx = TweetContext(
        symbol="XUSDT", price=1.0, change_pct_24h=1.0, bias="中性",
        state_label="三线走平·震荡结构", zone_label="中间", pct_b=0.5,
    )
    u = build_user_prompt(ctx)
    assert "OI 持仓量" not in u
    assert "多空比" not in u
    assert "15 分钟" not in u


@pytest.mark.asyncio
async def test_fetch_extra_metrics_enrich_and_graceful(monkeypatch) -> None:  # noqa: ANN001
    """★刀2 富化:A 币全查到 → 5 字段齐;B 币全查不到 → 原样(优雅降级·不崩)。做T零碰。"""
    from datetime import UTC, datetime  # noqa: PLC0415
    from types import SimpleNamespace  # noqa: PLC0415

    from app.schemas.market import Kline  # noqa: PLC0415
    from app.services.x_marketing import generate as gen  # noqa: PLC0415

    async def _batch(
        _client: object, *, symbols: list[str],
    ) -> dict[str, dict[str, float]]:
        return {s: {"oi_change_pct_24h": -2.1} for s in symbols if s == "AUSDT"}  # A 有 · B 无

    async def _oi(_client: object, symbol: str, *, limit: int = 1) -> list[object]:  # noqa: ARG001
        if symbol == "AUSDT":
            return [SimpleNamespace(oi_usd=1.0e8)]
        raise RuntimeError("no oi")  # B 查失败 → 降级

    async def _ls(_client: object, symbol: str, *, limit: int = 1) -> list[object]:  # noqa: ARG001
        return [SimpleNamespace(global_account_ratio=0.7)] if symbol == "AUSDT" else []

    monkeypatch.setattr(gen, "select_futures_metrics_batch", _batch)
    monkeypatch.setattr(gen, "select_open_interest", _oi)
    monkeypatch.setattr(gen, "select_long_short", _ls)

    def _k(close: float, vol: float) -> Kline:
        return Kline(
            ts=datetime(2026, 1, 1, tzinfo=UTC),
            open=close, high=close, low=close, close=close, volume=vol,
        )
    klines = [_k(100.0 + i, 10.0) for i in range(20)] + [_k(103.5, 50.0)]  # 21 根·末根量 5×

    class _FakeCH:
        _client = object()

        async def select_kline(self, **kw: object) -> list[Kline]:
            return klines if kw.get("symbol") == "AUSDT" else []

    a = TweetContext(symbol="AUSDT", price=1.0, change_pct_24h=0.0, bias="偏空",
                     state_label="s", zone_label="z", pct_b=0.1)
    b = TweetContext(symbol="BUSDT", price=1.0, change_pct_24h=0.0, bias="中性",
                     state_label="s", zone_label="z", pct_b=0.5)
    out = await gen.fetch_extra_metrics(_FakeCH(), [a, b])

    assert out[0].oi_usd == 1.0e8
    assert out[0].oi_change_pct_24h == -2.1
    assert out[0].long_short_ratio == 0.7
    assert out[0].change_pct_15m is not None
    assert round(out[0].volume_ratio, 1) == 5.0    # 50 / (20 根均量 10)
    # ★B 全查不到 → 原样 None(优雅降级·不崩)
    assert out[1].oi_usd is None
    assert out[1].long_short_ratio is None
    assert out[1].change_pct_15m is None
    assert out[1].volume_ratio is None


# ── ★正文 URL 成本警告(warn-only · 与门禁否决正交)──────────────────────────────
def test_has_body_url_detects_links() -> None:
    """检出正文 URL(X 含链接推贵十几倍 · 前端据此提醒)。"""
    assert has_body_url("详见 https://midastrade.asia/cn") is True
    assert has_body_url("http://x.com/foo") is True
    assert has_body_url("访问 www.midastrade.asia") is True
    assert has_body_url("midastrade.asia 有更多") is True
    assert has_body_url("go example.io now") is True


def test_has_body_url_no_false_positive_on_normal_tweet() -> None:
    """正常分析推文(数字/百分比/币种/标签)不误报。"""
    assert has_body_url("BTC 24h 跌 3.5%,%B 0.82,近上轨。仅供参考,不构成投资建议") is False
    assert has_body_url("ETH 破位 1.20 支撑 #ETH #点金Midas") is False
    assert has_body_url("") is False


def test_has_body_url_orthogonal_to_gate() -> None:
    """★含 URL 不影响门禁 passed(URL 是成本提醒不是否决项)· 合规带免责的推仍过。"""
    text = "BTC 走强,近上轨。详见 midastrade.asia。仅供参考,不构成投资建议"
    assert has_body_url(text) is True
    assert validate_tweet(text).passed is True  # 有 URL 但无买卖/预测/收益词 + 带免责 → 仍过


# ── ★step1:分平台 style(X 短推 vs 币安长文)────────────────────────────────────
def test_x_short_style_prompt_differs_and_falls_back() -> None:
    """x_short 取短推 system prompt(≤110·体检口吻)· 未知 style 回退 default。"""
    default_p = build_system_prompt("default")
    x_p = build_system_prompt("x_short")
    assert x_p != default_p
    assert "110" in x_p            # 短推特征:≤110 字上限在 prompt
    assert "体检" in x_p           # 冷静体检口吻
    assert "绝不放任何链接" in x_p  # ★X 无链接红线在 prompt
    assert build_system_prompt("unknown") == default_p  # 未知 style 回退 default(向后兼容)
    assert build_system_prompt() == default_p           # 缺省 = default


def test_x_short_style_uses_topic_tag() -> None:
    """default → #点金Midas(品牌);x_short → #加密货币(话题·利 X 传播)· 都不含链接。"""
    body = "BTC 结构偏空,贴下轨。仅供参考,不构成投资建议"
    assert append_tags(body, "BTCUSDT", "default").endswith("#BTC #点金Midas")
    assert append_tags(body, "BTCUSDT", "x_short").endswith("#BTC #加密货币")
    # ★门禁平台无关:X 短推同样过同一门禁(带免责·无买卖词)
    assert validate_tweet(append_tags(body, "BTCUSDT", "x_short")).passed is True
