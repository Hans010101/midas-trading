"""智能交易 · 各指标方向分(±1/0)计算 service(智能交易 PR-1 信号生产层)。

★PR-0 §1·B 确认:方向分用 indicators.compute_*(返回当前值),不是 scan_signals 信号点序列
(信号点是"事件",共振打分要"持续方向")。布林方向分【不在此】(权重 2.0 · PR-3 从
boll:snapshot:latest 读 bias)· extreme 方向另从 scan_extreme 取(extreme_direction)。
🔴 纯计算 · 信号生产层不下单 · 供 worker 每 15min 算 + PR-3 打分引擎读。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.services.ai.indicators import (
    compute_atr,
    compute_kdj,
    compute_ma,
    compute_macd,
    compute_rsi,
)

if TYPE_CHECKING:
    from app.schemas.market import Kline
    from app.schemas.strategy import StrategySignal

MIN_BARS = 26  # ★最小 K 线数(macd 预热最苛刻 · 不足跳过该币)


def _dir(diff: float, eps: float = 0.0) -> int:
    """方向分:+1 偏多 / −1 偏空 / 0 中性(diff 在 ±eps 内 = 中性带)。"""
    if diff > eps:
        return 1
    if diff < -eps:
        return -1
    return 0


def compute_indicator_directions(klines: list[Kline]) -> dict[str, Any]:
    """各技术指标当前值 → 方向分(MA/MACD/RSI/KDJ · ±1/0)+ ATR + 指标当前值。

    ★布林方向分【不在此】(权重 2.0 · PR-3 从 boll:snapshot:latest 读 bias · 零重算)。
    返回字段进 intelligent:signals:latest 快照,供 PR-3 打分 + 看板/复盘展示。
    """
    ma = compute_ma(klines)
    macd = compute_macd(klines)
    rsi = compute_rsi(klines).get(14, 50.0)
    kdj = compute_kdj(klines)
    atr = compute_atr(klines, 14)
    return {
        "ma_dir": _dir(ma[5] - ma[20]),               # MA5 vs MA20(多头排列=偏多)
        "macd_dir": _dir(macd["dif"] - macd["dea"]),  # DIF vs DEA(金叉态=偏多)
        "rsi_dir": _dir(rsi - 50.0),                  # RSI vs 50
        "kdj_dir": _dir(kdj["K"] - kdj["D"]),         # K vs D(金叉=偏多)
        # ── 指标当前值(看板 / PR-7 复盘展示用)──
        "rsi": round(rsi, 1),
        "ma5": round(ma[5], 6),
        "ma20": round(ma[20], 6),
        "macd_dif": round(macd["dif"], 6),
        "macd_dea": round(macd["dea"], 6),
        "kdj_k": round(kdj["K"], 1),
        "kdj_d": round(kdj["D"], 1),
        "atr": round(atr, 8),                          # ★PR-3 止损用(2×ATR)
    }


def extreme_direction(signals: list[StrategySignal]) -> int:
    """extreme 方向分:最新极端信号 buy→+1 / sell→−1 / 无→0。

    ★反向情绪口径已在 scan_extreme 内(正费率高=多头拥挤→sell)· 此处只取最新信号 kind。
    """
    if not signals:
        return 0
    return 1 if signals[-1].kind == "buy" else -1
