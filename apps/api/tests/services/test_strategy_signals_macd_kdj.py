"""MACD / KDJ 策略信号 pytest · 第一刀扩展(纯逻辑 · 无 DB/LLM · 本地可跑)。

覆盖:
- compute_kdj 计算正确性(标准 9,3,3 · K/D 初值 50 · RSV=100 已知场景手算核对)。
- ★MACD 金叉判定 = DIF 上穿 DEA(不是均线穿越)—— 经 _macd_series 在信号根验证穿越关系。
- KDJ 金叉/死叉触发(K 上穿/下穿 D)。
- dispatcher 分发 macd_cross / kdj_cross;预热不足 → 空。
🔴 红线:只验信号计算 · 不涉及下单/执行/撮合(扫描器只吃 K 线 list)。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.market import Kline
from app.services.ai.indicators import compute_kdj
from app.services.ai.strategy_signals import (
    _macd_series,
    scan_kdj_cross,
    scan_macd_cross,
    scan_signals,
)


def _kl(closes: list[float]) -> list[Kline]:
    """合成 K 线 · close 驱动 · high/low 留 ±5 带(避免非法 OHLC)。"""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Kline(
            ts=start + timedelta(days=i),
            open=c, high=c + 5, low=max(c - 5, 0.01), close=c,
            volume=1000.0, amount=None,
        )
        for i, c in enumerate(closes)
    ]


def _ohlc(rows: list[tuple[float, float, float]]) -> list[Kline]:
    """显式 (high, low, close) 造 K 线 · KDJ 需真实高低。"""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Kline(
            ts=start + timedelta(days=i),
            open=c, high=h, low=lo, close=c, volume=1000.0, amount=None,
        )
        for i, (h, lo, c) in enumerate(rows)
    ]


# ===== compute_kdj 正确性 =====


def test_compute_kdj_insufficient_returns_neutral():
    """不足 n(9)根 → K=D=J=50(中性)。"""
    out = compute_kdj(_kl([10.0] * 5))
    assert out == {"K": 50.0, "D": 50.0, "J": 50.0}


def test_compute_kdj_rsv100_known_case():
    """9 根 · 末根 close==窗口最高 → RSV=100;K/D 初值 50 一次迭代手算核对。

    RSV=100 → K = 2/3·50 + 1/3·100 = 66.667;D = 2/3·50 + 1/3·66.667 = 55.556;J = 3K−2D = 88.889。
    """
    rows = [(10.0, 5.0, 7.0)] * 8 + [(20.0, 5.0, 20.0)]  # 末根 close=high=20=hn · ln=5 → RSV=100
    out = compute_kdj(_ohlc(rows))
    assert out["K"] == pytest.approx(66.667, abs=0.01)
    assert out["D"] == pytest.approx(55.556, abs=0.01)
    assert out["J"] == pytest.approx(88.889, abs=0.01)


# ===== MACD 金叉 = DIF 上穿 DEA(★定义正确性) =====


def test_macd_golden_cross_is_dif_over_dea():
    """先跌后涨(V 形)→ 复苏段出 MACD 金叉 buy;★在信号根验证 DIF 由 ≤DEA 变 >DEA(非均线穿越)。"""
    closes = [100.0 - i for i in range(40)] + [60.0 + i * 1.5 for i in range(40)]
    klines = _kl(closes)
    sigs = scan_macd_cross(klines)
    buys = [s for s in sigs if s.kind == "buy"]
    assert buys, "V 形复苏应至少触发一个 MACD 金叉买点"
    assert "金叉" in buys[0].reason
    assert "DIF" in buys[0].levels
    assert "DEA" in buys[0].levels
    # ★ 在该买点根验证:前一根 DIF≤DEA、当根 DIF>DEA(DIF 上穿 DEA · 不是 MA 穿越)
    series = _macd_series(closes)
    idx = next(i for i, k in enumerate(klines) if k.ts == buys[0].ts)
    prev, cur = series[idx - 1], series[idx]
    assert prev is not None
    assert cur is not None
    assert prev[0] <= prev[1]   # prev DIF ≤ DEA
    assert cur[0] > cur[1]      # cur  DIF > DEA → 上穿


def test_macd_death_cross_sell():
    """先涨后跌 → 出 MACD 死叉 sell(DIF 下穿 DEA)。"""
    closes = [60.0 + i for i in range(40)] + [100.0 - i * 1.5 for i in range(40)]
    sigs = scan_macd_cross(_kl(closes))
    sells = [s for s in sigs if s.kind == "sell"]
    assert sells
    assert "死叉" in sells[0].reason


def test_macd_warmup_insufficient_empty():
    """不足以预热 DEA(< slow+signal 根)→ 空信号。"""
    assert scan_macd_cross(_kl([100.0 + i for i in range(20)])) == []


# ===== KDJ 金叉/死叉触发 =====


def test_kdj_cross_produces_buy_and_sell():
    """深跌后强反弹 → KDJ 金叉 buy;再回落 → 死叉 sell。K 上穿/下穿 D。"""
    closes = (
        [100.0 - i * 2 for i in range(20)]   # 跌
        + [60.0 + i * 2 for i in range(20)]  # 涨(金叉)
        + [100.0 - i * 2 for i in range(20)]  # 再跌(死叉)
    )
    sigs = scan_kdj_cross(_kl(closes))
    buys = [s for s in sigs if s.kind == "buy"]
    sells = [s for s in sigs if s.kind == "sell"]
    assert any("金叉" in s.reason for s in buys)
    assert any("死叉" in s.reason for s in sells)
    # levels 带 K/D/J
    s0 = sigs[0]
    assert {"K", "D", "J"} <= set(s0.levels)


# ===== dispatcher =====


def test_dispatcher_supports_macd_and_kdj():
    closes = [100.0 - i for i in range(40)] + [60.0 + i * 1.5 for i in range(40)]
    klines = _kl(closes)
    assert isinstance(scan_signals(klines, "macd_cross"), list)
    assert isinstance(scan_signals(klines, "kdj_cross"), list)


def test_dispatcher_unknown_still_raises():
    with pytest.raises(ValueError, match="未知策略"):
        scan_signals(_kl([1.0, 2.0, 3.0]), "not_a_strategy")  # type: ignore[arg-type]
