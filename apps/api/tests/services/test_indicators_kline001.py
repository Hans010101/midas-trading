"""KLINE-001 新增指标单测:ATR + 量比(对标 CryptoSharp 标题)。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.schemas.market import Kline
from app.services.ai.indicators import compute_atr, compute_volume_ratio

_BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _k(i: int, o: float, h: float, low: float, c: float, v: float) -> Kline:
    return Kline(ts=_BASE + timedelta(days=i), open=o, high=h, low=low, close=c, volume=v)


def test_atr_flat_series_is_zero() -> None:
    """完全平的序列(OHLC 全等)· TR 恒 0 → ATR=0。"""
    ks = [_k(i, 100, 100, 100, 100, 1000) for i in range(20)]
    assert compute_atr(ks) == 0.0


def test_atr_volatile_positive_and_scales() -> None:
    """波动序列 ATR>0,且波动更大 → ATR 更大。"""
    small = [_k(i, 100, 101, 99, 100, 1000) for i in range(20)]  # 日内幅 ~2
    big = [_k(i, 100, 110, 90, 100, 1000) for i in range(20)]  # 日内幅 ~20
    atr_small = compute_atr(small)
    atr_big = compute_atr(big)
    assert atr_small > 0
    assert atr_big > atr_small


def test_atr_insufficient_data_zero() -> None:
    assert compute_atr([_k(0, 100, 101, 99, 100, 1000)]) == 0.0
    assert compute_atr([]) == 0.0


def test_volume_ratio_doubled() -> None:
    """前 5 根均量 1000 · 最新 2000 → 量比 ≈ 2.0。"""
    ks = [_k(i, 100, 101, 99, 100, 1000.0) for i in range(5)]
    ks.append(_k(5, 100, 101, 99, 100, 2000.0))
    assert abs(compute_volume_ratio(ks, period=5) - 2.0) < 1e-9


def test_volume_ratio_flat_is_one() -> None:
    ks = [_k(i, 100, 101, 99, 100, 1500.0) for i in range(10)]
    assert abs(compute_volume_ratio(ks, period=5) - 1.0) < 1e-9


def test_volume_ratio_insufficient_zero() -> None:
    ks = [_k(i, 100, 101, 99, 100, 1000.0) for i in range(3)]
    assert compute_volume_ratio(ks, period=5) == 0.0
