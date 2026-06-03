"""技术指标计算 · 纯 Python · 无 TA-lib / pandas-ta 依赖。

为什么不用 TA-lib:
  - C 扩展安装 friction 太大(M1/M2 chip 各种坑)
  - 我们只需 4 个指标快照,不需要全量历史值
  - 纯 Python 实现 200 根 K 线 ~3ms 足够

输出 · 都是 dict 形式 · 喂给 TechnicalSnapshot Pydantic model。
"""

from __future__ import annotations

from typing import Literal

from app.schemas.market import Kline


def _ema(values: list[float], period: int) -> float:
    """EMA · 指数移动均线 · 返回最后一个值。"""
    if len(values) < period:
        return values[-1] if values else 0.0
    alpha = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = alpha * v + (1 - alpha) * ema
    return ema


def _sma(values: list[float], period: int) -> float:
    """SMA · 简单移动均线 · 返回最后一个值。"""
    if len(values) < period:
        return sum(values) / max(len(values), 1)
    return sum(values[-period:]) / period


def _stdev(values: list[float], period: int) -> float:
    """样本标准差(period 窗口)。"""
    if len(values) < period:
        period = len(values)
    if period < 2:
        return 0.0
    window = values[-period:]
    mean = sum(window) / period
    var = sum((v - mean) ** 2 for v in window) / (period - 1)
    return float(var ** 0.5)


def compute_ma(klines: list[Kline]) -> dict[int, float]:
    """MA · 5 / 20 / 60 三档收盘均线。"""
    closes = [float(k.close) for k in klines]
    return {
        5: _sma(closes, 5),
        20: _sma(closes, 20),
        60: _sma(closes, 60),
    }


def compute_macd(klines: list[Kline]) -> dict[str, float]:
    """MACD(12, 26, 9)· 返回 dif / dea / macd 三个最新值。"""
    closes = [float(k.close) for k in klines]
    if len(closes) < 26:
        return {"dif": 0.0, "dea": 0.0, "macd": 0.0}

    # EMA12 / EMA26 序列(整段)· 计算 DIF 需要历史值才能算 DEA 的 EMA9
    def _ema_series(values: list[float], period: int) -> list[float]:
        if len(values) < period:
            return [values[-1]] if values else [0.0]
        alpha = 2.0 / (period + 1)
        seed = sum(values[:period]) / period
        out = [seed]
        for v in values[period:]:
            out.append(alpha * v + (1 - alpha) * out[-1])
        return out

    ema12 = _ema_series(closes, 12)
    ema26 = _ema_series(closes, 26)
    # 对齐尾部
    n = min(len(ema12), len(ema26))
    dif_series = [ema12[-n:][i] - ema26[-n:][i] for i in range(n)]
    dea_series = _ema_series(dif_series, 9)
    dif = dif_series[-1]
    dea = dea_series[-1]
    macd_hist = (dif - dea) * 2
    return {"dif": dif, "dea": dea, "macd": macd_hist}


def compute_rsi(klines: list[Kline], period: int = 14) -> dict[int, float]:
    """RSI(14)· 经典 Wilder 平滑。"""
    closes = [float(k.close) for k in klines]
    if len(closes) < period + 1:
        return {period: 50.0}

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    # 初始均值
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Wilder smoothing
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - 100 / (1 + rs)
    return {period: rsi}


def compute_boll(
    klines: list[Kline], period: int = 20, k: float = 2.0,
) -> dict[str, float]:
    """布林带(20, 2)· 上中下三轨。"""
    closes = [float(k.close) for k in klines]
    mid = _sma(closes, period)
    sd = _stdev(closes, period)
    return {
        "upper": mid + k * sd,
        "mid": mid,
        "lower": mid - k * sd,
    }


def compute_trend_5d(klines: list[Kline]) -> Literal["up", "down", "sideways"]:
    """近 5 根 K 线趋势 · 收盘价 5 日斜率简单判断。"""
    if len(klines) < 5:
        return "sideways"
    closes = [float(k.close) for k in klines[-5:]]
    change = (closes[-1] - closes[0]) / closes[0]
    if change > 0.02:    # +2% 以上
        return "up"
    if change < -0.02:
        return "down"
    return "sideways"
