"""极端信号 scan_extreme pytest · 第二刀(★仅 crypto perp · 纯逻辑 · 无 DB/LLM · 本地可跑)。

覆盖:
- 资金费率正向过高 → 偏空(sell · 多头拥挤反向);负向过低 → 偏多(buy · 空头拥挤反向)。
- 多空比偏高 → 偏空;偏低 → 偏多(过度一边倒反向)。
- OI 急增 / 急减 触发(情绪转折)· 仅 OI 异动时方向逆近期价格。
- 三者都不极端 → 不触发(空);数据缺失(None)优雅降级不报错。
- reason 写明哪项走极端 + levels 带数值;dispatcher 不处理 extreme(端点专路)。
🔴 红线:只验信号计算 · scan_extreme 只吃 K 线 + 标量数据 · 不涉及下单/执行/撮合/engine。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.market import Kline
from app.services.ai.strategy_signals import scan_extreme, scan_signals


def _kl(closes: list[float]) -> list[Kline]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Kline(
            ts=start + timedelta(hours=i),
            open=c, high=c + 5, low=max(c - 5, 0.01), close=c,
            volume=1000.0, amount=None,
        )
        for i, c in enumerate(closes)
    ]


_FLAT = _kl([100.0] * 20)  # 价格平 · 给"仅某项极端"的场景用


# ===== 资金费率(★方向口径:正费率=多头付空头=多头拥挤→偏空)=====


def test_funding_positive_high_is_sell() -> None:
    """正费率过高 = 多头过度拥挤 → 反向偏空(sell)。"""
    sigs = scan_extreme(_FLAT, funding_rate=0.001)  # 0.1% > 0.05% 阈值
    assert len(sigs) == 1
    assert sigs[0].kind == "sell"
    assert "资金费率正向偏高" in sigs[0].reason
    assert sigs[0].levels["资金费率%"] == pytest.approx(0.1, abs=1e-6)


def test_funding_negative_low_is_buy() -> None:
    """负费率过低 = 空头过度拥挤 → 反向偏多(buy)。"""
    sigs = scan_extreme(_FLAT, funding_rate=-0.001)
    assert len(sigs) == 1
    assert sigs[0].kind == "buy"
    assert "资金费率负向偏低" in sigs[0].reason


def test_funding_normal_no_trigger() -> None:
    """常态费率(0.01%)不触发。"""
    assert scan_extreme(_FLAT, funding_rate=0.0001) == []


# ===== 多空比(偏高=过度做多→偏空 · 偏低=过度做空→偏多)=====


def test_long_short_high_is_sell() -> None:
    sigs = scan_extreme(_FLAT, long_short_ratio=2.5)  # > 2.0
    assert len(sigs) == 1
    assert sigs[0].kind == "sell"
    assert "多空比偏高" in sigs[0].reason
    assert sigs[0].levels["多空比"] == pytest.approx(2.5)


def test_long_short_low_is_buy() -> None:
    sigs = scan_extreme(_FLAT, long_short_ratio=0.3)  # < 0.5
    assert len(sigs) == 1
    assert sigs[0].kind == "buy"
    assert "多空比偏低" in sigs[0].reason


def test_long_short_normal_no_trigger() -> None:
    assert scan_extreme(_FLAT, long_short_ratio=1.2) == []


# ===== OI 异动(情绪转折 · 仅 OI 时方向逆近期价格)=====


def test_oi_surge_triggers() -> None:
    """OI 急增 ≥10% → 触发 · 价升 → 逆向 sell。"""
    rising = _kl([100.0 + i for i in range(15)])  # 近期价格上行
    oi = [100.0] * 10 + [130.0]  # +30%
    sigs = scan_extreme(rising, oi_usd_series=oi)
    assert len(sigs) == 1
    assert "OI急增" in sigs[0].reason
    assert sigs[0].kind == "sell"  # 仅 OI 异动 + 价升 → 反向偏空
    assert sigs[0].levels["OI变动%"] == pytest.approx(30.0, abs=0.1)


def test_oi_drop_triggers() -> None:
    falling = _kl([130.0 - i for i in range(15)])  # 近期价格下行
    oi = [130.0] * 10 + [100.0]  # -23%
    sigs = scan_extreme(falling, oi_usd_series=oi)
    assert len(sigs) == 1
    assert "OI急减" in sigs[0].reason
    assert sigs[0].kind == "buy"  # 仅 OI 异动 + 价跌 → 反向偏多


def test_oi_stable_no_trigger() -> None:
    oi = [100.0, 101.0, 99.0, 100.0, 102.0]  # 波动 < 10%
    assert scan_extreme(_FLAT, oi_usd_series=oi) == []


# ===== 不触发 / 优雅降级 =====


def test_no_data_no_trigger() -> None:
    """三项全 None(数据缺) → 不触发,不报错。"""
    assert scan_extreme(_FLAT) == []


def test_partial_missing_still_triggers_on_present() -> None:
    """OI/多空比缺(None)· 仅资金费率极端 → 仍按资金费率触发(优雅降级)。"""
    sigs = scan_extreme(_FLAT, funding_rate=0.001, oi_usd_series=None, long_short_ratio=None)
    assert len(sigs) == 1
    assert sigs[0].kind == "sell"


def test_empty_klines_no_trigger() -> None:
    assert scan_extreme([], funding_rate=0.001) == []


# ===== 多项叠加 + 信号点位置 =====


def test_multiple_extremes_combined_one_signal() -> None:
    """资金费率正高 + 多空比偏高(同偏空)→ 合并为【一个】sell 信号 · 标在最新一根。"""
    sigs = scan_extreme(_FLAT, funding_rate=0.001, long_short_ratio=2.5)
    assert len(sigs) == 1
    assert sigs[0].kind == "sell"
    assert sigs[0].ts == _FLAT[-1].ts
    assert sigs[0].price == pytest.approx(100.0)
    assert sigs[0].strength == 2.0  # 2 项走极端
    assert sigs[0].strength_note is not None
    assert "极端" in sigs[0].strength_note


# ===== dispatcher:extreme 不入通用 _SCANNERS(端点专路调 scan_extreme)=====


def test_dispatcher_rejects_extreme() -> None:
    """scan_signals 不处理 extreme(需合约数据)→ 抛错;端点对 crypto perp 特判直调。"""
    with pytest.raises((ValueError, KeyError)):
        scan_signals(_FLAT, "extreme")  # type: ignore[arg-type]
