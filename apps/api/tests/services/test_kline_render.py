"""KLINE-001 K线图渲染单测 · RSI/MACD 序列 + render_kline_png 冒烟(出 PNG)+ 数据不足兜底。

★ 不验中文不豆腐(那靠 docker slim + fonts-noto-cjk · 见 docs/decisions/KLINE-001 + CI 跑在 ubuntu
   无 CJK 字体只验「能出 PNG 无异常」· 字体是生产 docker 的事)。
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from app.schemas.market import Kline
from app.services.charting.kline_render import (
    _macd_series,
    _rsi_series,
    render_kline_png,
)

_BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _synthetic_klines(n: int) -> list[Kline]:
    """合成 n 根 K线(确定性锯齿走势 · 无随机 · OHLC 一致)。"""
    out: list[Kline] = []
    price = 100.0
    for i in range(n):
        drift = 0.02 if i % 3 == 0 else (-0.015 if i % 3 == 1 else 0.005)
        close = max(1.0, price * (1 + drift))
        openp = price
        hi = max(openp, close) * 1.008
        lo = min(openp, close) * 0.992
        out.append(Kline(ts=_BASE + timedelta(days=i), open=round(openp, 4),
                         high=round(hi, 4), low=round(lo, 4), close=round(close, 4),
                         volume=1000.0 + i))
        price = close
    return out


def test_rsi_series_bounded_and_warmup_nan() -> None:
    close = pd.Series([k.close for k in _synthetic_klines(60)])
    rsi = _rsi_series(close, period=14)
    assert len(rsi) == 60
    assert rsi.iloc[:14].isna().all()  # 暖机段 NaN
    valid = rsi.dropna()
    assert ((valid >= 0) & (valid <= 100)).all()  # RSI 恒在 [0,100]


def test_macd_series_shape() -> None:
    close = pd.Series([k.close for k in _synthetic_klines(60)])
    dif, dea, hist = _macd_series(close)
    assert len(dif) == len(dea) == len(hist) == 60
    # hist = (dif - dea) * 2 · 取最后一根校验关系
    assert math.isclose(hist.iloc[-1], (dif.iloc[-1] - dea.iloc[-1]) * 2, rel_tol=1e-9)


def test_render_kline_png_returns_png_bytes() -> None:
    """合成 120 根 → 渲染出 PNG(magic header)· 不抛异常。"""
    png = render_kline_png(
        symbol="600519", name="贵州茅台", market="cn", klines=_synthetic_klines(120),
    )
    assert isinstance(png, bytes)
    assert len(png) > 1000
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # PNG 魔数


def test_render_insufficient_data_raises() -> None:
    """数据不足(< 30 根)→ ValueError(端点据此回退网页链接)。"""
    with pytest.raises(ValueError, match="数据不足"):
        render_kline_png(
            symbol="X", name="X", market="cn", klines=_synthetic_klines(10),
        )
