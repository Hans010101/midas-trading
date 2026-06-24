"""布林做T状态机 M1 单测:状态分类 + 结构倾向 + ★红线措辞 + ★影子门禁 spy/never。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.market import Kline
from app.services.ai.boll_state import (
    _FORBIDDEN_PUSH_WORDS,
    _ZONE_LABEL,
    DETAIL_URL,
    STRUCTURE_DISCLAIMER,
    BollSnapshot,
    BollState,
    _zone,
    build_session_message,
    build_transition_digest,
    classify,
    push_strength,
    render_card,
    select_for_push,
    state_label,
    to_snapshot_row,
    validate_shadow_push,
)


def _snap(pct_b: float, *, state: BollState = BollState.RANGE) -> BollSnapshot:
    """造任意 %B 的结构快照(M2-1 频率/文案测用 · 价位字段占位,只关心 pct_b/state)。"""
    return BollSnapshot(
        state=state, bias="中性", pct_b=pct_b, bandwidth=0.04, zone=_zone(pct_b),
        close=100.0, mid=100.0, upper=102.0, lower=98.0,
    )


def _klines(closes: list[float]) -> list[Kline]:
    """从收盘价序列造 Kline(boll 只用 close · high/low/open 取 close 邻域 · ts 递增)。"""
    base = datetime(2026, 6, 22, 0, 0, tzinfo=UTC)
    out: list[Kline] = []
    for i, c in enumerate(closes):
        out.append(
            Kline(
                ts=base + timedelta(minutes=15 * i),
                open=c, high=c * 1.001, low=c * 0.999, close=c, volume=1.0,
            ),
        )
    return out


# ── 状态分类 ────────────────────────────────────────────────────────────────

def test_trend_up() -> None:
    snap = classify(_klines([100 + i * 0.6 for i in range(28)]))
    assert snap is not None
    assert snap.state is BollState.TREND_UP
    assert snap.bias == "偏多"


def test_trend_down() -> None:
    snap = classify(_klines([120 - i * 0.6 for i in range(28)]))
    assert snap is not None
    assert snap.state is BollState.TREND_DOWN
    assert snap.bias == "偏空"


def test_range_flat() -> None:
    # 围绕 100 窄幅震荡 · 中轨走平 + 带宽平稳 → RANGE
    closes = [100 + (0.5 if i % 2 else -0.5) for i in range(28)]
    snap = classify(_klines(closes))
    assert snap is not None
    assert snap.state is BollState.RANGE


def test_squeeze() -> None:
    # 前 20 根宽幅(±4)→ 后 8 根几乎不动 → 近 20 窗口 std 收缩 → 带宽收口 → SQUEEZE
    wide = [100 + (4 if i % 2 else -4) for i in range(20)]
    tight = [100.0] * 8
    snap = classify(_klines([*wide, *tight]))
    assert snap is not None
    assert snap.state is BollState.SQUEEZE
    assert snap.bias == "中性"


def test_insufficient_bars_returns_none() -> None:
    assert classify(_klines([100.0] * 10)) is None


# ── ★红线:措辞无买卖词 ──────────────────────────────────────────────────────

def test_render_card_has_no_trade_words() -> None:
    snap = classify(_klines([100 + i * 0.6 for i in range(28)]))
    assert snap is not None
    card = render_card("BTCUSDT", snap)
    for word in _FORBIDDEN_PUSH_WORDS:
        assert word not in card, f"结构卡不得含买卖/预测词:{word}"
    # 倾向标签只用偏多/偏空/中性
    assert any(b in card for b in ("偏多", "偏空", "中性"))


# ── ★影子门禁 validate_shadow_push:spy(拒)/ never(正常放行)────────────────

def test_gate_rejects_buy_imperative() -> None:
    # ★含合规声明(结构描述非建议)但正文有买卖词 → 仍一票否决(剔声明后「建议/买入」仍在)
    bad = f"【BTCUSDT】三线齐上 · 建议买入抄底\n{STRUCTURE_DISCLAIMER}"
    with pytest.raises(ValueError, match="买卖祈使"):
        validate_shadow_push(bad)


def test_gate_rejects_missing_disclaimer() -> None:
    # ★【门禁没改松铁证】完全无任何合规声明(无「仅供参考」也无「结构描述非建议」)→ 一票否决
    with pytest.raises(ValueError, match="声明"):
        validate_shadow_push("【BTCUSDT】三线齐上·上升结构 · 结构倾向:偏多")


def test_gate_accepts_juyongcankao() -> None:
    # ★精简后:含「仅供参考」即视为有合规声明 → 通过(不再要求末尾固定「结构描述非建议」行)
    ok = "BTCUSDT｜结构倾向:偏多\n状态转换:三线走平·震荡结构 → 带宽开口·向上 · 仅供参考"
    out = validate_shadow_push(ok)
    assert "仅供参考" in out
    assert "结构描述非建议" not in out  # ★末尾不再有重复声明行


def test_gate_still_accepts_legacy_structure_disclaimer() -> None:
    # 兼容:旧的「结构描述非建议」仍被认可为合规声明(不破历史文案)
    ok = f"【BTCUSDT】三线齐上·上升结构\n{STRUCTURE_DISCLAIMER}"
    assert "结构描述非建议" in validate_shadow_push(ok)


def test_gate_rejects_marketing() -> None:
    bad = f"【BTCUSDT】稳赚不赔的结构\n{STRUCTURE_DISCLAIMER}"
    with pytest.raises(ValueError, match="营销"):
        validate_shadow_push(bad)


# ── 做T A-1 快照行 to_snapshot_row ────────────────────────────────────────────

def test_snapshot_row_keys_and_no_trade_words() -> None:
    snap = classify(_klines([100 + i * 0.6 for i in range(28)]))
    assert snap is not None
    row = to_snapshot_row(
        "BTCUSDT", snap, change_pct_24h=5.0, funding_rate=0.0001,
        transition=True, prev_state="range",
    )
    # ★键集合与 schemas.crypto.BollScanItem 字段一一对应(extra=forbid · A-2 加 zone_label/bandwidth/funding_rate)
    assert set(row) == {
        "symbol", "state", "state_label", "bias", "pct_b", "zone_label", "bandwidth",
        "close", "mid", "upper", "lower", "change_pct_24h", "funding_rate",
        "transition", "transition_from",
    }
    assert row["transition_from"] == "三线走平·震荡结构"  # prev=range 的中文口诀
    assert row["bias"] in ("偏多", "偏空", "中性")
    assert row["funding_rate"] == 0.0001
    assert isinstance(row["bandwidth"], float)
    assert row["zone_label"] in ("破上轨", "近上轨", "近中轨", "近下轨", "破下轨", "中间")
    blob = f"{row}"
    for word in _FORBIDDEN_PUSH_WORDS:
        assert word not in blob, f"快照行不得含买卖/预测词:{word}"


def test_snapshot_row_no_transition_from_when_stable() -> None:
    snap = classify(_klines([100 + i * 0.6 for i in range(28)]))
    assert snap is not None
    row = to_snapshot_row(
        "BTCUSDT", snap, change_pct_24h=None, funding_rate=None,
        transition=False, prev_state="trend_up",
    )
    assert row["transition"] is False
    assert row["transition_from"] is None
    assert row["change_pct_24h"] is None
    assert row["funding_rate"] is None  # 无 funding 数据 → 降级 None(不崩)


def test_zone_overshoot_labels() -> None:
    # ★越界标注(P2):%B>1 破上轨 · %B<0 破下轨 · 同改 TG 影子 + 接口快照(单源 _zone)
    assert _zone(1.2) == "over_upper"
    assert _zone(-0.1) == "over_lower"
    assert _zone(0.9) == "upper"
    assert _zone(0.1) == "lower"
    assert _zone(0.5) == "mid"
    assert _ZONE_LABEL["over_upper"] == "破上轨"
    assert _ZONE_LABEL["over_lower"] == "破下轨"


def test_build_session_message_ok() -> None:
    # 推送卡都带转换行(候选都是转换)→ 含「仅供参考」声明
    snaps = [classify(_klines([100 + i * 0.6 for i in range(28)]))]
    cards = [render_card("BTCUSDT", s, transition_from="三线走平·震荡结构")
             for s in snaps if s is not None]
    msg = build_session_message(cards)
    # ★精简后:声明在转换行「仅供参考」· 末尾不再有重复的「结构描述非建议」行
    assert "仅供参考" in msg
    assert STRUCTURE_DISCLAIMER not in msg
    # ★正文(剔除合规声明短语后)无买卖/预测词
    body = msg.replace("仅供参考", "").replace("结构描述非建议", "")
    for word in _FORBIDDEN_PUSH_WORDS:
        assert word not in body


# ── M2-1 频率控制(推送强度排序 + 批量上限 + 每日上限)──────────────────────────

def test_push_strength_ranks_by_channel_extremity() -> None:
    # |%B−0.5| 越大(越破轨)强度越高:破上轨 1.2 > 近上轨 0.85 > 中轨 0.5
    assert push_strength(_snap(1.2)) > push_strength(_snap(0.85))
    assert push_strength(_snap(0.85)) > push_strength(_snap(0.5))
    # 破下轨与破上轨对称(都远离中轨 → 强)
    assert push_strength(_snap(-0.1)) == pytest.approx(push_strength(_snap(1.1)))


def test_select_for_push_batch_cap_takes_strongest() -> None:
    # 6 个候选、批量上限 3 → 取 |%B−0.5| 最强的 3 个(破轨的优先)
    cands = [(f"C{i}USDT", _snap(p), "三线走平·震荡结构")
             for i, p in enumerate([0.5, 0.55, 0.95, 1.3, 0.1, 0.45])]
    out = select_for_push(cands, batch_max=3, daily_remaining=99)
    assert len(out) == 3
    picked = {c[0] for c in out}
    # 最强三个:%B=1.3(0.8)、0.95(0.45)、0.1(0.4)
    assert picked == {"C3USDT", "C2USDT", "C4USDT"}


def test_select_for_push_daily_cap_limits() -> None:
    cands = [(f"C{i}USDT", _snap(0.9), "x") for i in range(5)]
    # 每日剩余 2 < 批量 5 → 只取 2(每日上限收紧)
    assert len(select_for_push(cands, batch_max=5, daily_remaining=2)) == 2
    # 每日剩余 0 → 一条都不推
    assert select_for_push(cands, batch_max=5, daily_remaining=0) == []
    # 候选少于两个上限 → 全推
    assert len(select_for_push(cands[:1], batch_max=5, daily_remaining=9)) == 1


# ── M2-1 定稿方案B 文案 ───────────────────────────────────────────────────────

def test_render_card_plan_b_format() -> None:
    snap = _snap(0.88, state=BollState.BREAKOUT_UP)
    # 无转换:含 倾向/状态/通道位置/现价/轨道,★无「状态转换」「仅供参考」行
    card = render_card("BTCUSDT", snap)
    for k in ("结构倾向:", "状态:", "通道位置:", "现价 ", "轨道 "):
        assert k in card
    assert "状态转换" not in card
    # 有转换:追加「状态转换:X → Y · 仅供参考」(免责缀转换行 · 不占独立行)
    card2 = render_card("BTCUSDT", snap, transition_from="三线走平·震荡结构")
    assert "状态转换:三线走平·震荡结构 → " in card2
    assert card2.rstrip().endswith("· 仅供参考")
    # ★措辞红线:无买卖/预测词
    for word in _FORBIDDEN_PUSH_WORDS:
        assert word not in card2


def test_build_session_message_plan_b() -> None:
    cards = [
        render_card("BTCUSDT", _snap(0.9, state=BollState.BREAKOUT_UP),
                    transition_from=state_label(BollState.RANGE)),
        render_card("ETHUSDT", _snap(0.1, state=BollState.BREAKDOWN),
                    transition_from=state_label(BollState.RANGE)),
    ]
    msg = build_session_message(cards)
    assert msg.startswith("📊 布林做T信号 · 15m永续")   # 方案B 头
    assert "————————" in msg                           # 分隔线
    # ★精简后:声明在转换行「仅供参考」(每卡一处)· ★末尾无重复的「结构描述非建议」行
    assert "· 仅供参考" in msg
    assert STRUCTURE_DISCLAIMER not in msg
    # 正文(剔除合规声明短语后)无买卖/预测词
    body = msg.replace("仅供参考", "").replace("结构描述非建议", "")
    for word in _FORBIDDEN_PUSH_WORDS:
        assert word not in body


# ── 做T M2-3b · 转换合并简版列表 build_transition_digest(≥2 转换 → 一条)──────────

def _psnap(bias: str, state: BollState, pct_b: float) -> BollSnapshot:
    return BollSnapshot(
        state=state, bias=bias, pct_b=pct_b, bandwidth=0.04, zone=_zone(pct_b),
        close=100.0, mid=100.0, upper=102.0, lower=98.0,
    )


def test_transition_digest_merges_multiple() -> None:
    pushed = [
        ("BTCUSDT", _psnap("偏多", BollState.BREAKOUT_UP, 0.9), "三线走平·震荡结构"),
        ("ADAUSDT", _psnap("偏空", BollState.BREAKDOWN, 0.1), "三线走平·震荡结构"),
        ("WLFIUSDT", _psnap("中性", BollState.SQUEEZE, 0.5), "三线齐上·上升结构"),
    ]
    msg = build_transition_digest(pushed)
    # ★合并成一条 · 头含个数
    assert msg.startswith("📊 布林做T · 转换提醒(3个)")
    # ★方向 emoji 📈/📉/➖(非红绿)· 每币一行
    assert "📈 [BTCUSDT]" in msg
    assert "📉 [ADAUSDT]" in msg
    assert "➖ [WLFIUSDT]" in msg
    # ★超链接 Markdown 指向详情页
    assert f"[BTCUSDT]({DETAIL_URL}?symbol=BTCUSDT)" in msg
    # ★转{倾向}(只偏多/偏空/中性)+ 结构转换路径 + %B
    assert "转偏多" in msg
    assert "三线走平·震荡结构 → 带宽开口·向上" in msg
    assert "%B=0.90" in msg


def test_transition_digest_disclaimer_and_no_trade_words() -> None:
    pushed = [
        ("BTCUSDT", _psnap("偏多", BollState.TREND_UP, 0.8), "三线走平·震荡结构"),
        ("ETHUSDT", _psnap("偏空", BollState.TREND_DOWN, 0.2), "带宽开口·向上"),
    ]
    msg = build_transition_digest(pushed)
    # ★末尾唯一「· 仅供参考」过门禁
    assert msg.rstrip().endswith("· 仅供参考")
    # ★正文(剔合规声明)无买卖/预测词(转换方向用结构口诀,非买卖词)
    body = msg.replace("仅供参考", "").replace("结构描述非建议", "")
    for word in _FORBIDDEN_PUSH_WORDS:
        assert word not in body


def test_transition_digest_single_card_still_plan_b() -> None:
    # 对照:单个转换不走 digest · 走方案B 完整卡(build_session_message · 多行三轨)
    card = render_card(
        "BTCUSDT", _psnap("偏多", BollState.BREAKOUT_UP, 0.9),
        transition_from="三线走平·震荡结构",
    )
    msg = build_session_message([card])
    assert msg.startswith("📊 布林做T信号 · 15m永续")  # 方案B 头(非合并头)
    assert "转换提醒" not in msg  # 不是简版合并
    assert "· 仅供参考" in msg
