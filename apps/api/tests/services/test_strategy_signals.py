"""策略信号序列扫描器 pytest · 形态A 单元1(ADR 0037 §2/§3)。

覆盖:
- 序列指标正确性(_sma_series / _rsi_series / _boll_series)。
- 三策略穿越逻辑(造确定性 K 线触发精确的 buy/sell 信号点):
  · ma_cross 金叉/死叉
  · rsi_reversal 上穿30买 / 下穿70卖(反弹确认式 · 拍板①)
  · boll_reversion 收盘价触下轨买 / 触上轨卖(均值回归 · 收盘价穿越 · 拍板②)
- 预热不足 / 空序列 → 空信号。
- dispatcher 分发 + 未知策略 ValueError。
- ★ 纯 OHLCV 四市场通用(扫描器不读 market)。

🔴 红线:本测试只验信号计算 · 不涉及下单/执行/撮合/实时上游(扫描器只吃 K 线 list)。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.market import Kline
from app.schemas.strategy import StrategySignal
from app.services.ai.strategy_signals import (
    _boll_series,
    _rsi_series,
    _sma_series,
    scan_boll_reversion,
    scan_ma_cross,
    scan_rsi_reversal,
    scan_signals,
)


def _kl(closes: list[float]) -> list[Kline]:
    """合成 K 线 · 只 close 有意义(策略纯收盘价)· high/low 留足避免非法 OHLC。"""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Kline(
            ts=start + timedelta(days=i),
            # 策略只看 close;low 取 max(c-5, 0.01) 保证 Kline 正价格校验(low>0)
            open=c, high=c + 5, low=max(c - 5, 0.01), close=c,
            volume=1000.0, amount=None,
        )
        for i, c in enumerate(closes)
    ]


# ===== 序列指标正确性 =====


def test_sma_series_warmup_and_values():
    """SMA 序列:前 period-1 位 None,之后为窗口均值。"""
    out = _sma_series([1.0, 2.0, 3.0, 4.0, 5.0], 3)
    assert out[0] is None
    assert out[1] is None
    assert out[2] == pytest.approx(2.0)   # (1+2+3)/3
    assert out[3] == pytest.approx(3.0)   # (2+3+4)/3
    assert out[4] == pytest.approx(4.0)   # (3+4+5)/3


def test_rsi_series_all_up_is_100_all_down_is_0():
    """RSI 序列:纯涨 → 100(无亏损);纯跌 → 0(无盈利)。"""
    up = _rsi_series([float(x) for x in range(1, 30)], 14)     # 单调涨
    down = _rsi_series([float(x) for x in range(30, 1, -1)], 14)  # 单调跌
    # 预热位 None
    assert up[13] is None
    assert up[14] == pytest.approx(100.0)
    assert down[14] == pytest.approx(0.0)


def test_boll_series_mid_is_sma_and_bands_symmetric():
    """布林序列:mid == SMA;upper/lower 关于 mid 对称(±k·σ)。"""
    closes = [100.0, 102.0, 98.0, 101.0, 99.0, 100.0]
    out = _boll_series(closes, 5, 2.0)
    assert out[3] is None              # 预热(需 5 根)
    band = out[4]
    assert band is not None
    mid, upper, lower = band
    assert mid == pytest.approx(_sma_series(closes, 5)[4])
    assert upper - mid == pytest.approx(mid - lower)   # 对称
    assert upper > mid > lower


# ===== 策略1 · 均线金叉/死叉 =====


def test_ma_cross_golden_cross_buy():
    """20 根平盘(MA5=MA20)后转涨 → MA5 上穿 MA20 = 金叉买点。"""
    closes = [10.0] * 20 + [11.0, 12.0, 13.0, 14.0, 15.0]
    sigs = scan_ma_cross(_kl(closes))
    assert len(sigs) == 1
    assert sigs[0].kind == "buy"
    assert "金叉" in sigs[0].reason
    # 信号落在第一根上涨 K(index 20)
    assert sigs[0].ts == _kl(closes)[20].ts
    assert sigs[0].price == pytest.approx(11.0)


def test_ma_cross_death_cross_sell():
    """20 根平盘后转跌 → MA5 下穿 MA20 = 死叉卖点。"""
    closes = [20.0] * 20 + [19.0, 18.0, 17.0, 16.0, 15.0]
    sigs = scan_ma_cross(_kl(closes))
    assert len(sigs) == 1
    assert sigs[0].kind == "sell"
    assert "死叉" in sigs[0].reason


def test_ma_cross_insufficient_bars_no_signal():
    """不足 slow(20)根 → 无信号。"""
    assert scan_ma_cross(_kl([10.0, 11.0, 12.0])) == []


# ===== 策略2 · RSI 超卖反弹/超买回落(反弹确认式 · 拍板①)=====


def test_rsi_reversal_oversold_bounce_buy():
    """持续下跌(RSI→0,超卖)后一根强反弹 → RSI 上穿 30 = 买点。"""
    # 16 根单调跌(RSI 在 index14/15 = 0 < 30),index16 一根 +12 强反弹
    closes = [100.0 - 2.0 * i for i in range(16)] + [82.0, 84.0, 86.0]
    sigs = scan_rsi_reversal(_kl(closes))
    buys = [s for s in sigs if s.kind == "buy"]
    assert len(buys) >= 1
    # 第一个买点是上穿 30 那根(反弹确认 · index16)· 不是「一进超卖就买」
    assert buys[0].ts == _kl(closes)[16].ts
    assert "超卖反弹" in buys[0].reason
    # 单调跌→反弹,不应出现 sell
    assert all(s.kind == "buy" for s in sigs)


def test_rsi_reversal_overbought_pullback_sell():
    """持续上涨(RSI→100,超买)后一根回落 → RSI 下穿 70 = 卖点。"""
    closes = [100.0 + 2.0 * i for i in range(16)] + [118.0]
    sigs = scan_rsi_reversal(_kl(closes))
    sells = [s for s in sigs if s.kind == "sell"]
    assert len(sells) >= 1
    assert sells[0].ts == _kl(closes)[16].ts
    assert "超买回落" in sells[0].reason


def test_rsi_reversal_not_triggered_when_stays_oversold():
    """★ 反弹确认式关键:持续超卖(RSI 一直 <30,未回升)→ 不刷点(避免连续噪音)。"""
    closes = [100.0 - 2.0 * i for i in range(20)]   # 一路跌到底,RSI 一直 0
    sigs = scan_rsi_reversal(_kl(closes))
    assert sigs == []   # 没有「上穿 30」事件 → 零信号


# ===== 策略3 · 布林带均值回归(收盘价穿越 · 拍板②)=====


def test_boll_reversion_touch_lower_buy():
    """震荡(σ>0)后收盘价急跌穿下轨 → 均值回归买点。"""
    base = [100.0, 102.0, 98.0, 101.0, 99.0] * 4   # 20 根震荡
    closes = base + [80.0]                          # index20 急跌穿下轨
    sigs = scan_boll_reversion(_kl(closes))
    assert len(sigs) == 1
    assert sigs[0].kind == "buy"
    assert sigs[0].ts == _kl(closes)[20].ts
    assert "下轨" in sigs[0].reason


def test_boll_reversion_touch_upper_sell():
    """震荡后收盘价急涨穿上轨 → 均值回归卖点。"""
    base = [100.0, 102.0, 98.0, 101.0, 99.0] * 4
    closes = base + [120.0]                         # index20 急涨穿上轨
    sigs = scan_boll_reversion(_kl(closes))
    assert len(sigs) == 1
    assert sigs[0].kind == "sell"
    assert "上轨" in sigs[0].reason


# ===== 形态A 批2 · ⑤关键价位(全策略)+ ⑥成色(rsi/boll · ma_cross 不做)=====


def test_ma_cross_levels_no_strength():
    """⑤ ma_cross 透出 MA5/MA20 关键价位 · ⑥ 成色不做(strength=None · ★不空塞)。"""
    closes = [10.0] * 20 + [11.0, 12.0, 13.0, 14.0, 15.0]
    sig = scan_ma_cross(_kl(closes))[0]
    assert set(sig.levels) == {"MA5", "MA20"}          # 透出两条均线值
    assert sig.levels["MA5"] > sig.levels["MA20"]      # 金叉:MA5 已上穿 MA20
    assert sig.strength is None                        # ma_cross 成色不做(产品负责人定)
    assert sig.strength_note is None                   # ★ 不空塞误导


def test_rsi_reversal_levels_and_strength():
    """⑤ rsi 透出 RSI 值 + 超卖线 · ⑥ 成色=超卖深度(回穿前 RSI 越低越强)。"""
    closes = [100.0 - 2.0 * i for i in range(16)] + [82.0, 84.0, 86.0]
    buy = next(s for s in scan_rsi_reversal(_kl(closes)) if s.kind == "buy")
    assert "RSI" in buy.levels
    assert buy.levels["超卖线"] == pytest.approx(30.0)
    assert buy.strength is not None
    assert buy.strength > 0                            # 探底深度 > 0
    assert buy.strength_note is not None
    assert "超卖深度" in buy.strength_note


def test_boll_reversion_levels_and_strength():
    """⑤ boll 透出 上/中/下轨 · ⑥ 成色=偏离轨道幅度(越远越极端)。"""
    closes = [100.0, 102.0, 98.0, 101.0, 99.0] * 4 + [80.0]
    sig = scan_boll_reversion(_kl(closes))[0]
    assert set(sig.levels) == {"上轨", "中轨", "下轨"}
    assert sig.levels["上轨"] > sig.levels["中轨"] > sig.levels["下轨"]
    assert sig.strength is not None
    assert sig.strength > 0                            # 偏离下轨 > 0
    assert sig.strength_note is not None
    assert "偏离下轨" in sig.strength_note


# ===== dispatcher + 通用性 =====


def test_scan_signals_dispatch_matches_direct():
    """dispatcher 分发结果 == 直接调用对应扫描器。"""
    closes = [10.0] * 20 + [11.0, 12.0, 13.0]
    kl = _kl(closes)
    assert scan_signals(kl, "ma_cross") == scan_ma_cross(kl)


def test_scan_signals_unknown_strategy_raises():
    """未知策略 → ValueError(端点/调用方兜底)。"""
    with pytest.raises(ValueError, match="未知策略"):
        scan_signals(_kl([1.0, 2.0]), "not_a_strategy")  # type: ignore[arg-type]


def test_scan_signals_empty_klines():
    """空 K 线 → 空信号(不崩)。"""
    for strat in ("ma_cross", "rsi_reversal", "boll_reversion"):
        assert scan_signals([], strat) == []  # type: ignore[arg-type]


def test_signals_are_strategy_signal_type_and_sorted():
    """返回类型 StrategySignal · ts 升序(自然遍历顺序)。"""
    closes = [20.0] * 20 + [19.0, 18.0, 17.0] + [18.0, 19.0, 20.0, 21.0, 22.0, 23.0]
    sigs = scan_ma_cross(_kl(closes))
    assert all(isinstance(s, StrategySignal) for s in sigs)
    assert [s.ts for s in sigs] == sorted(s.ts for s in sigs)


def test_pure_ohlcv_market_agnostic():
    """★ 纯 OHLCV:扫描器只吃 close,与 market 无关 → 四市场同一份 K 线产同一信号。

    (Kline 本身不含 market 字段,信号只由收盘价序列决定 —— 天然四市场通用。)
    """
    closes = [10.0] * 20 + [11.0, 12.0]
    kl = _kl(closes)
    # 同一序列重复扫描结果稳定且确定(纯函数)
    assert scan_ma_cross(kl) == scan_ma_cross(kl)
