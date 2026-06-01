"""策略信号序列扫描器 · 模拟交易第二层形态A 单元1(ADR 0037 §2/§3)。

═══════════════════════════════════════════════════════════════════════════
🔴 红线(焊死):
   - 只算信号 · 不下单 · 不执行 · 不撮合 · 不碰任何 virtual_trading 引擎。
   - 只读 K 线(调用方从 select_kline 拿历史 K 线传入)· 绝不打实时上游。
   - 复用 indicators.py 数学基础(_sma / _stdev / Wilder RSI 逻辑),
     但【不改任何现有 compute_* 契约】—— 现有 AI 决策卡指标零回归。
   - 不碰现有 AI 管线(workflow / technical agent)/ 缠论 / 第一层。
═══════════════════════════════════════════════════════════════════════════

三策略(穿越式离散信号 · 拍板①②③ · 纯 OHLCV 四市场通用):
- ma_cross       · MA5 上穿 MA20 = buy / 下穿 = sell(金叉/死叉)
- rsi_reversal   · RSI(14) 上穿 30 = buy / 下穿 70 = sell(反弹确认式 · 拍板①)
- boll_reversion · 收盘价下穿布林下轨 = buy / 上穿上轨 = sell(均值回归 · 收盘价穿越 · 拍板②)

为什么穿越式(crossover)而非状态式:穿越只在「状态切换的那一根」标一个点,天然离散,
不会在 RSI 持续 < 30 / 价格持续在轨外时连续刷点,完美匹配 K 线信号点标注(midas-fractal)。
"""

from __future__ import annotations

from collections.abc import Callable

from app.schemas.market import Kline
from app.schemas.strategy import StrategyKind, StrategySignal

# ★ 复用 indicators 的纯数学基础(不改其对外 compute_* 契约 · 现有指标零回归)
from app.services.ai.indicators import _sma, _stdev

# ===== 默认参数(拍板⑤ · MVP 固定)=====
_MA_FAST = 5
_MA_SLOW = 20
_RSI_PERIOD = 14
_RSI_OVERSOLD = 30.0
_RSI_OVERBOUGHT = 70.0
_BOLL_PERIOD = 20
_BOLL_K = 2.0


# ===== 序列指标(复用 indicators 数学 · 吐整段序列 · 未预热位 = None)=====


def _sma_series(closes: list[float], period: int) -> list[float | None]:
    """逐根 SMA 序列 · 前 period-1 位未预热为 None · 之后复用 indicators._sma。"""
    out: list[float | None] = []
    for i in range(len(closes)):
        if i + 1 < period:
            out.append(None)
        else:
            # _sma 取 window[-period:],此处 window=closes[:i+1] 末 period 根即该位窗口
            out.append(_sma(closes[: i + 1], period))
    return out


def _boll_series(
    closes: list[float], period: int, k: float,
) -> list[tuple[float, float, float] | None]:
    """逐根布林带序列 (mid, upper, lower) · 未预热 None · 复用 _sma + _stdev。"""
    out: list[tuple[float, float, float] | None] = []
    for i in range(len(closes)):
        if i + 1 < period:
            out.append(None)
        else:
            window = closes[: i + 1]
            mid = _sma(window, period)
            sd = _stdev(window, period)
            out.append((mid, mid + k * sd, mid - k * sd))
    return out


def _rsi_series(closes: list[float], period: int) -> list[float | None]:
    """逐根 Wilder RSI 序列 · 逻辑与 indicators.compute_rsi 一致(同 Wilder 平滑)。

    一次遍历产全序列(避免逐根调 compute_rsi 的 O(n²) 重算)。
    前 period 位未预热为 None(需 period+1 根收盘价才有第一个 RSI)。
    """
    n = len(closes)
    out: list[float | None] = [None] * n
    if n < period + 1:
        return out

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, n):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    def _rsi(avg_gain: float, avg_loss: float) -> float:
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - 100 / (1 + rs)

    # 初始均值(前 period 个 gain/loss)· 第一个 RSI 落在 closes 索引 period
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = _rsi(avg_gain, avg_loss)

    # Wilder 平滑 · gains[i] 对应 closes[i+1]
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = _rsi(avg_gain, avg_loss)
    return out


# ===== 穿越检测(相邻两根) =====


def _crosses_up(prev_a: float, prev_b: float, cur_a: float, cur_b: float) -> bool:
    """a 上穿 b:前一根 a ≤ b 且 当前根 a > b。"""
    return prev_a <= prev_b and cur_a > cur_b


def _crosses_down(prev_a: float, prev_b: float, cur_a: float, cur_b: float) -> bool:
    """a 下穿 b:前一根 a ≥ b 且 当前根 a < b。"""
    return prev_a >= prev_b and cur_a < cur_b


# ===== 三策略扫描器 =====


def scan_ma_cross(
    klines: list[Kline], fast: int = _MA_FAST, slow: int = _MA_SLOW,
) -> list[StrategySignal]:
    """均线金叉/死叉:MA_fast 上穿 MA_slow = buy / 下穿 = sell。"""
    closes = [float(k.close) for k in klines]
    ma_f = _sma_series(closes, fast)
    ma_s = _sma_series(closes, slow)
    signals: list[StrategySignal] = []
    for i in range(1, len(klines)):
        pf, ps, cf, cs = ma_f[i - 1], ma_s[i - 1], ma_f[i], ma_s[i]
        if pf is None or ps is None or cf is None or cs is None:
            continue
        if _crosses_up(pf, ps, cf, cs):
            signals.append(StrategySignal(
                ts=klines[i].ts, price=closes[i], kind="buy",
                reason=f"MA{fast} 上穿 MA{slow}(金叉)",
            ))
        elif _crosses_down(pf, ps, cf, cs):
            signals.append(StrategySignal(
                ts=klines[i].ts, price=closes[i], kind="sell",
                reason=f"MA{fast} 下穿 MA{slow}(死叉)",
            ))
    return signals


def scan_rsi_reversal(
    klines: list[Kline],
    period: int = _RSI_PERIOD,
    oversold: float = _RSI_OVERSOLD,
    overbought: float = _RSI_OVERBOUGHT,
) -> list[StrategySignal]:
    """RSI 超卖反弹/超买回落(反弹确认式 · 拍板①):

    RSI 上穿 oversold(30)= buy(超卖后回升确认反弹);
    RSI 下穿 overbought(70)= sell(超买后回落)。
    """
    closes = [float(k.close) for k in klines]
    rsi = _rsi_series(closes, period)
    signals: list[StrategySignal] = []
    for i in range(1, len(klines)):
        prev, cur = rsi[i - 1], rsi[i]
        if prev is None or cur is None:
            continue
        # 上穿超卖线 → 反弹买点
        if prev < oversold and cur >= oversold:
            signals.append(StrategySignal(
                ts=klines[i].ts, price=closes[i], kind="buy",
                reason=f"RSI 上穿 {oversold:.0f}(超卖反弹)",
            ))
        # 下穿超买线 → 回落卖点
        elif prev > overbought and cur <= overbought:
            signals.append(StrategySignal(
                ts=klines[i].ts, price=closes[i], kind="sell",
                reason=f"RSI 下穿 {overbought:.0f}(超买回落)",
            ))
    return signals


def scan_boll_reversion(
    klines: list[Kline], period: int = _BOLL_PERIOD, k: float = _BOLL_K,
) -> list[StrategySignal]:
    """布林带均值回归(收盘价穿越 · 拍板② · ★非突破追涨):

    收盘价下穿下轨 = buy(博回归中轨);收盘价上穿上轨 = sell。
    用收盘价 C 穿越(稳健 · 不被插针/影线误触发)。
    """
    closes = [float(k.close) for k in klines]
    boll = _boll_series(closes, period, k)
    signals: list[StrategySignal] = []
    for i in range(1, len(klines)):
        prev_band, cur_band = boll[i - 1], boll[i]
        if prev_band is None or cur_band is None:
            continue
        _, prev_up, prev_low = prev_band
        _, cur_up, cur_low = cur_band
        prev_c, cur_c = closes[i - 1], closes[i]
        # 收盘价下穿下轨 → 均值回归买点
        if prev_c > prev_low and cur_c <= cur_low:
            signals.append(StrategySignal(
                ts=klines[i].ts, price=cur_c, kind="buy",
                reason="收盘触布林下轨(均值回归买点)",
            ))
        # 收盘价上穿上轨 → 均值回归卖点
        elif prev_c < prev_up and cur_c >= cur_up:
            signals.append(StrategySignal(
                ts=klines[i].ts, price=cur_c, kind="sell",
                reason="收盘触布林上轨(均值回归卖点)",
            ))
    return signals


# ===== dispatcher =====

_SCANNERS: dict[StrategyKind, Callable[[list[Kline]], list[StrategySignal]]] = {
    "ma_cross": scan_ma_cross,
    "rsi_reversal": scan_rsi_reversal,
    "boll_reversion": scan_boll_reversion,
}


def scan_signals(klines: list[Kline], strategy: StrategyKind) -> list[StrategySignal]:
    """按策略 key 分发扫描器 · 返回 ts 升序的信号点序列(空 K 线返回空)。

    ★ 只读纯计算 · 不下单 · 不执行 · 不打实时。strategy 非法 → ValueError(由调用方/端点兜底)。
    """
    scanner = _SCANNERS.get(strategy)
    if scanner is None:
        raise ValueError(f"未知策略:{strategy}")
    return scanner(klines)


__all__ = [
    "scan_boll_reversion",
    "scan_ma_cross",
    "scan_rsi_reversal",
    "scan_signals",
]
