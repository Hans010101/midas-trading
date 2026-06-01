"""策略信号 + 推荐 只读 API pytest · 形态A 单元2(ADR 0037 §5.1)。

直接调端点函数(类比 test_ai_order · 传 fake CH · 不走 HTTP),fake CH 返回 ≥30 根
K 线避免触发回源(sources 传 None 不会被调)。

覆盖:
- GET /strategy-signals:返回信号序列 + current_triggered + last_signal · 四市场。
- GET /strategy-recommend:返回推荐策略 + 理由 · 四市场回显。
- perp + 非 crypto → 400。

🔴 红线:端点只读 select_kline(fake)+ 纯计算 · 不下单 / 不执行 / 不打实时。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import HTTPException

from app.api.v1.analysis import get_strategy_recommend, get_strategy_signals
from app.schemas.market import Kline


class _FakeCH:
    """只实现 select_kline 的假 CH(只读)· 返回预置 K 线。"""

    def __init__(self, klines: list[Kline]) -> None:
        self._klines = klines
        self._client = object()

    async def select_kline(self, **_kwargs: Any) -> list[Kline]:
        return list(self._klines)


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


# ===== /strategy-signals =====


@pytest.mark.asyncio
async def test_strategy_signals_returns_buy_signal():
    """30 根平盘后转涨(金叉)→ ma_cross 返回 buy 信号。"""
    ch = _FakeCH(_kl([10.0] * 30 + [11.0, 12.0, 13.0, 14.0, 15.0]))
    resp = await get_strategy_signals(
        ch, None, None, None, None,  # type: ignore[arg-type]
        symbol="NVDA", market="us", period="1d", limit=300,
        instrument="spot", strategy="ma_cross",
    )
    assert resp.strategy == "ma_cross"
    assert resp.market == "us"
    assert resp.bar_count == 35
    assert any(s.kind == "buy" for s in resp.signals)
    assert "金叉" in resp.signals[0].reason
    # 金叉在 index30(非最后一根 index34)→ 当前未触发
    assert resp.current_triggered is False
    assert resp.last_signal is not None


@pytest.mark.asyncio
async def test_strategy_signals_current_triggered_true():
    """最后一根触发信号 → current_triggered=True(布林触下轨在最后一根)。"""
    # 30 根震荡(σ>0)+ 最后一根急跌穿下轨
    base = [100.0, 102.0, 98.0, 101.0, 99.0] * 6   # 30 根
    ch = _FakeCH(_kl(base + [80.0]))               # index30 = 最后一根触发
    resp = await get_strategy_signals(
        ch, None, None, None, None,  # type: ignore[arg-type]
        symbol="600519", market="cn", period="1d", limit=300,
        instrument="spot", strategy="boll_reversion",
    )
    assert resp.current_triggered is True
    assert resp.last_signal is not None
    assert resp.last_signal.kind == "buy"
    assert resp.signals[-1].ts == resp.last_signal.ts


@pytest.mark.asyncio
async def test_strategy_signals_crypto_perp():
    """crypto + perp(拍板⑦ 跟随详情页)· instrument 回显。"""
    ch = _FakeCH(_kl([20.0] * 30 + [19.0, 18.0, 17.0, 16.0, 15.0]))
    resp = await get_strategy_signals(
        ch, None, None, None, None,  # type: ignore[arg-type]
        symbol="BTCUSDT", market="crypto", period="1h", limit=300,
        instrument="perp", strategy="ma_cross",
    )
    assert resp.instrument == "perp"
    assert resp.market == "crypto"
    assert any(s.kind == "sell" for s in resp.signals)   # 死叉


@pytest.mark.asyncio
async def test_strategy_signals_no_signal_empty_list():
    """单调上涨(无金叉穿越)→ 空信号 · current_triggered=False · last_signal=None。"""
    ch = _FakeCH(_kl([100.0 + i for i in range(40)]))
    resp = await get_strategy_signals(
        ch, None, None, None, None,  # type: ignore[arg-type]
        symbol="NVDA", market="us", period="1d", limit=300,
        instrument="spot", strategy="ma_cross",
    )
    # 单调涨:MA5 一直在 MA20 上方,无穿越 → 无信号
    assert resp.signals == []
    assert resp.current_triggered is False
    assert resp.last_signal is None


# ===== /strategy-recommend =====


@pytest.mark.asyncio
async def test_strategy_recommend_uptrend_ma_cross():
    """上升趋势 → 推荐 ma_cross。"""
    ch = _FakeCH(_kl([100.0 + i for i in range(40)]))
    resp = await get_strategy_recommend(
        ch, None, None, None, None,  # type: ignore[arg-type]
        symbol="NVDA", market="us", period="1d", limit=300, instrument="spot",
    )
    assert resp.recommended_strategy == "ma_cross"
    assert "趋势" in resp.reason
    assert resp.market == "us"


@pytest.mark.asyncio
async def test_strategy_recommend_four_markets_echo():
    """四市场回显 market/instrument(同一份 K 线,验市场参数透传)。"""
    ch = _FakeCH(_kl([100.0 + i for i in range(40)]))
    for market, inst in (("cn", "spot"), ("us", "spot"), ("crypto", "perp")):
        resp = await get_strategy_recommend(
            ch, None, None, None, None,  # type: ignore[arg-type]
            symbol="X", market=market, period="1d", limit=300, instrument=inst,  # type: ignore[arg-type]
        )
        assert resp.market == market
        assert resp.instrument == inst


# ===== perp 市场校验 =====


@pytest.mark.asyncio
async def test_strategy_signals_perp_non_crypto_rejected():
    """instrument=perp + 非 crypto → 400(与 chan/decision-card 同校验)。"""
    ch = _FakeCH(_kl([10.0] * 35))
    with pytest.raises(HTTPException) as exc:
        await get_strategy_signals(
            ch, None, None, None, None,  # type: ignore[arg-type]
            symbol="NVDA", market="us", period="1d", limit=300,
            instrument="perp", strategy="ma_cross",
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_strategy_recommend_perp_non_crypto_rejected():
    """recommend 同样校验 perp 只允许 crypto。"""
    ch = _FakeCH(_kl([10.0] * 35))
    with pytest.raises(HTTPException) as exc:
        await get_strategy_recommend(
            ch, None, None, None, None,  # type: ignore[arg-type]
            symbol="600519", market="cn", period="1d", limit=300, instrument="perp",
        )
    assert exc.value.status_code == 400
