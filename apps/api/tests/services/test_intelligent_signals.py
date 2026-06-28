"""智能交易 PR-1 · 方向分纯函数测(compute_indicator_directions + extreme_direction)。

★PR-0 §1·B:方向分用 indicators.compute_*(当前值)· 上涨趋势 → 各指标偏多(+1) · 下跌 → 偏空(−1)。
纯函数 · 本地无需 PG 可跑(吸取连续接缝教训:本地能跑必真跑)。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.schemas.market import Kline
from app.schemas.strategy import StrategySignal
from app.services.ai import intelligent_signals as isig

_BASE = datetime(2026, 6, 1, tzinfo=UTC)


def _kline(i: int, close: float) -> Kline:
    # OHLC 满足几何约束(low ≤ open/close ≤ high)
    return Kline(
        ts=_BASE + timedelta(minutes=15 * i),
        open=close * 0.999, high=close * 1.002, low=close * 0.998,
        close=close, volume=100.0,
    )


def _trend_klines(n: int, step: float) -> list[Kline]:
    """单调趋势 K 线 · step>1 上涨 / step<1 下跌。"""
    out: list[Kline] = []
    price = 100.0
    for i in range(n):
        price *= step
        out.append(_kline(i, price))
    return out


def test_dir_helper() -> None:
    assert isig._dir(1.0) == 1
    assert isig._dir(-1.0) == -1
    assert isig._dir(0.0) == 0
    assert isig._dir(0.5, eps=1.0) == 0  # ★中性带:±eps 内 = 0


def test_directions_uptrend() -> None:
    # 单调上涨 → MA5>MA20 · DIF>DEA · RSI>50 · K>D 全偏多
    dirs = isig.compute_indicator_directions(_trend_klines(40, 1.01))
    assert dirs["ma_dir"] == 1
    assert dirs["macd_dir"] == 1
    assert dirs["rsi_dir"] == 1
    assert dirs["kdj_dir"] == 1
    assert dirs["atr"] > 0
    assert dirs["rsi"] > 50


def test_directions_downtrend() -> None:
    # 匀速下跌 → MA/RSI/KDJ 偏空 · ★MACD 不强求 −1:匀速跌时 DIF 高于滞后 DEA(动能减弱=金叉态)
    #   是 MACD 真实行为(死叉需加速下跌 · 见 test_macd_bearish_cross)。
    dirs = isig.compute_indicator_directions(_trend_klines(40, 0.99))
    assert dirs["ma_dir"] == -1
    assert dirs["rsi_dir"] == -1
    assert dirs["kdj_dir"] == -1
    assert dirs["rsi"] < 50


def test_macd_bearish_cross() -> None:
    # ★横盘后下跌 → MACD 死叉(DIF 快速转负穿 DEA)→ macd_dir=−1(验 MACD 能取 −1)
    out = [_kline(i, 100.0 if i < 25 else 100.0 * 0.98 ** (i - 24)) for i in range(50)]
    assert isig.compute_indicator_directions(out)["macd_dir"] == -1


def test_extreme_direction() -> None:
    assert isig.extreme_direction([]) == 0  # 无极端信号 → 中性
    buy = StrategySignal(ts=_BASE, price=100.0, kind="buy", reason="极端反向偏多")
    sell = StrategySignal(ts=_BASE, price=100.0, kind="sell", reason="极端反向偏空")
    assert isig.extreme_direction([buy]) == 1
    assert isig.extreme_direction([sell]) == -1
