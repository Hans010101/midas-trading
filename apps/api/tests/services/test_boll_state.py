"""布林做T状态机 M1 单测:状态分类 + 结构倾向 + ★红线措辞 + ★影子门禁 spy/never。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.market import Kline
from app.services.ai.boll_state import (
    _FORBIDDEN_PUSH_WORDS,
    _ZONE_LABEL,
    STRUCTURE_DISCLAIMER,
    BollState,
    _zone,
    build_session_message,
    classify,
    render_card,
    to_snapshot_row,
    validate_shadow_push,
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
    bad = f"【BTCUSDT】三线齐上 · 建议买入抄底\n{STRUCTURE_DISCLAIMER}"
    with pytest.raises(ValueError, match="买卖祈使"):
        validate_shadow_push(bad)


def test_gate_rejects_missing_disclaimer() -> None:
    with pytest.raises(ValueError, match="免责"):
        validate_shadow_push("【BTCUSDT】三线齐上·上升结构 · 结构倾向:偏多")


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
    snaps = [classify(_klines([100 + i * 0.6 for i in range(28)]))]
    cards = [render_card("BTCUSDT", s) for s in snaps if s is not None]
    msg = build_session_message(cards)
    # ★末尾恰好一行免责
    assert msg.rstrip().endswith(STRUCTURE_DISCLAIMER)
    assert msg.count(STRUCTURE_DISCLAIMER) == 1
    # ★正文(末尾免责行之外)无买卖/预测词(免责「非建议」含「建议」属正常,只查正文)
    body = msg.rstrip()[: -len(STRUCTURE_DISCLAIMER)]
    for word in _FORBIDDEN_PUSH_WORDS:
        assert word not in body
