"""策略推荐适配层 pytest · 形态A 单元2(ADR 0037 §4 · 纯规则推荐)。

覆盖:
- _pick 纯逻辑各分支(趋势 / 震荡+RSI极值 / 震荡+贴轨 / 兜底)· 优先级正确。
- recommend_strategy 端到端(造 K 线:上升趋势→ma_cross · 数据不足→兜底)。

🔴 红线:推荐是纯函数确定性映射 · 零 LLM · 只读 compute_*(不改 AI 管线 · 不下单)。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.schemas.market import Kline
from app.services.ai.strategy_recommend import _pick, recommend_strategy


def _kl(closes: list[float]) -> list[Kline]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Kline(
            ts=start + timedelta(days=i),
            open=c, high=c + 5, low=max(c - 5, 0.01), close=c,
            volume=1000.0, amount=None,
        )
        for i, c in enumerate(closes)
    ]


# ===== _pick 纯逻辑各分支 =====


def test_pick_uptrend_to_ma_cross():
    """趋势市(up)→ 均线金叉(优先级最高,RSI/贴轨不影响)。"""
    rec = _pick("up", rsi=20.0, pctb=0.05)   # 即便 RSI 超卖 + 贴下轨,趋势优先
    assert rec.strategy == "ma_cross"
    assert "上行趋势" in rec.reason


def test_pick_downtrend_to_ma_cross():
    """趋势市(down)→ 均线死叉。"""
    rec = _pick("down", rsi=80.0, pctb=0.95)
    assert rec.strategy == "ma_cross"
    assert "下行趋势" in rec.reason


def test_pick_sideways_oversold_to_rsi():
    """震荡 + RSI ≤ 35 → RSI 反弹。"""
    rec = _pick("sideways", rsi=30.0, pctb=0.5)
    assert rec.strategy == "rsi_reversal"
    assert "超卖" in rec.reason


def test_pick_sideways_overbought_to_rsi():
    """震荡 + RSI ≥ 65 → RSI 回落。"""
    rec = _pick("sideways", rsi=72.0, pctb=0.5)
    assert rec.strategy == "rsi_reversal"
    assert "超买" in rec.reason


def test_pick_sideways_near_lower_band_to_boll():
    """震荡 + RSI 中性 + 贴下轨(%B ≤ 0.2)→ 布林均值回归。"""
    rec = _pick("sideways", rsi=50.0, pctb=0.1)
    assert rec.strategy == "boll_reversion"
    assert "下轨" in rec.reason


def test_pick_sideways_near_upper_band_to_boll():
    """震荡 + RSI 中性 + 贴上轨(%B ≥ 0.8)→ 布林均值回归。"""
    rec = _pick("sideways", rsi=50.0, pctb=0.9)
    assert rec.strategy == "boll_reversion"
    assert "上轨" in rec.reason


def test_pick_rsi_priority_over_boll():
    """★ 优先级:震荡市 RSI 极值优先于贴轨(同时满足时选 RSI)。"""
    rec = _pick("sideways", rsi=30.0, pctb=0.1)   # 既超卖又贴下轨
    assert rec.strategy == "rsi_reversal"


def test_pick_sideways_neutral_fallback_ma():
    """震荡 + RSI 中性 + 不贴轨 → 兜底均线金叉。"""
    rec = _pick("sideways", rsi=50.0, pctb=0.5)
    assert rec.strategy == "ma_cross"
    assert "无明显极值" in rec.reason


def test_pick_sideways_none_pctb_fallback():
    """布林退化(pctb=None)+ RSI 中性 → 兜底均线。"""
    rec = _pick("sideways", rsi=50.0, pctb=None)
    assert rec.strategy == "ma_cross"


# ===== recommend_strategy 端到端 =====


def test_recommend_uptrend_klines_to_ma_cross():
    """造持续上升 K 线(trend=up)→ 推荐 ma_cross。"""
    closes = [100.0 + i for i in range(40)]   # 单调涨 · 最后 5 日 >2% → up
    rec = recommend_strategy(_kl(closes))
    assert rec.strategy == "ma_cross"
    assert "上行趋势" in rec.reason


def test_recommend_insufficient_bars_fallback():
    """K 线不足 20 根 → 兜底 ma_cross(不在未预热指标上瞎推荐)。"""
    rec = recommend_strategy(_kl([100.0, 101.0, 102.0]))
    assert rec.strategy == "ma_cross"
    assert "数据不足" in rec.reason


def test_recommend_empty_klines_fallback():
    """空 K 线 → 兜底(不崩)。"""
    rec = recommend_strategy([])
    assert rec.strategy == "ma_cross"
