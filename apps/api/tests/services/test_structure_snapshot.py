"""结构快照 service 单测 · mock CH 读层(零真实 CH/Redis · 本地可跑)。

覆盖:7 因子聚合形状 + window 口径字段 + 单因子缺失不崩 + symbol 归一。
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

import app.services.structure.snapshot as snap_mod
from app.schemas.crypto import (
    FearGreedPoint,
    FundingRate,
    LongShortRatio,
    MarketOverview,
    OpenInterest,
    PremiumIndex,
)
from app.services.structure.snapshot import build_structure_snapshot, normalize_symbol

_TS = datetime(2026, 6, 10, 8, 0, tzinfo=UTC)


def _lsr(ratio: float, pos: float, taker: float) -> LongShortRatio:
    return LongShortRatio(
        symbol="BTCUSDT", ts=_TS,
        top_account_long=0.6, top_account_short=0.4, top_account_ratio=ratio,
        top_position_long=0.55, top_position_short=0.45, top_position_ratio=pos,
        taker_buy_vol=100.0, taker_sell_vol=80.0, taker_ratio=taker,
    )


def _patch_all(monkeypatch: pytest.MonkeyPatch, *, funding_empty: bool = False) -> None:
    """六个读层函数全 mock(funding 可置空 · 验证单因子缺失不崩)。"""

    async def fake_lsr(client: Any, symbol: str, *, limit: int) -> list[LongShortRatio]:  # noqa: ARG001
        return [_lsr(1.0, 1.4, 0.9), _lsr(2.0, 1.6, 1.1)]

    async def fake_oi(client: Any, symbol: str, *, limit: int) -> list[OpenInterest]:  # noqa: ARG001
        return [
            OpenInterest(symbol="BTCUSDT", ts=_TS, oi_coin=90_000.0, oi_usd=100.0),
            OpenInterest(symbol="BTCUSDT", ts=_TS, oi_coin=95_000.0, oi_usd=110.0),
        ]

    async def fake_funding(client: Any, symbol: str, *, limit: int) -> list[FundingRate]:  # noqa: ARG001
        if funding_empty:
            return []
        return [
            FundingRate(symbol="BTCUSDT", ts=_TS, rate=0.0001, mark_price=105_000.0),
            FundingRate(symbol="BTCUSDT", ts=_TS, rate=0.0003, mark_price=105_100.0),
        ]

    async def fake_premium(client: Any, symbol: str) -> PremiumIndex:  # noqa: ARG001
        return PremiumIndex(
            symbol="BTCUSDT", ts=_TS, mark_price=101.0, index_price=100.0,
            last_funding_rate=0.0001, next_funding_time=_TS, funding_interval_hours=8,
        )

    async def fake_overview(client: Any) -> MarketOverview:  # noqa: ARG001
        return MarketOverview(
            ts=_TS, total_market_cap_usd=3e12, total_volume_24h_usd=1e11,
            btc_dominance=54.32, eth_dominance=17.0,
            fear_greed_value=0, fear_greed_classification="",
        )

    async def fake_fgi(client: Any, *, limit: int) -> list[FearGreedPoint]:  # noqa: ARG001
        return [FearGreedPoint(ts=_TS, value=30, classification="Fear")]

    monkeypatch.setattr(snap_mod, "select_long_short", fake_lsr)
    monkeypatch.setattr(snap_mod, "select_open_interest", fake_oi)
    monkeypatch.setattr(snap_mod, "select_funding_rates", fake_funding)
    monkeypatch.setattr(snap_mod, "select_latest_premium_index", fake_premium)
    monkeypatch.setattr(snap_mod, "select_latest_overview", fake_overview)
    monkeypatch.setattr(snap_mod, "select_fear_greed_series", fake_fgi)


def test_normalize_symbol() -> None:
    assert normalize_symbol(" btc/usdt ") == "BTCUSDT"
    assert normalize_symbol("ETH-USDT") == "ETHUSDT"


@pytest.mark.asyncio
async def test_snapshot_full_seven_factors(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_all(monkeypatch)
    snap = await build_structure_snapshot(object(), "btc/usdt")

    assert snap.symbol == "BTCUSDT"  # 归一
    # 7 因子全在
    assert snap.account_long_short is not None
    assert snap.position_long_short is not None
    assert snap.taker_flow is not None
    assert snap.open_interest is not None
    assert snap.funding_rate is not None
    assert snap.basis is not None
    assert snap.sentiment is not None

    # window 口径字段(TTL 约束产品化)逐因子断言
    assert snap.account_long_short.window == "24h"
    assert snap.position_long_short.window == "24h"
    assert snap.taker_flow.window == "24h"
    assert snap.open_interest.window == "24h"
    assert snap.funding_rate.window == "7d"
    assert snap.basis.window == "latest"
    assert snap.sentiment.window == "latest"

    # 聚合数值抽查
    assert snap.account_long_short.value["latest"] == 2.0
    assert snap.account_long_short.value["avg_24h"] == 1.5
    assert snap.open_interest.value["change_pct_24h"] == 10.0  # 100→110
    assert snap.funding_rate.value["latest"] == 0.0003
    assert snap.funding_rate.value["max_7d"] == 0.0003
    assert snap.funding_rate.value["min_7d"] == 0.0001
    assert snap.basis.value["basis"] == 1.0
    assert snap.basis.value["basis_pct"] == 1.0
    assert snap.sentiment.value["fear_greed"] == 30.0
    assert snap.sentiment.value["btc_dominance"] == 54.32
    assert snap.sentiment.text == "Fear"


@pytest.mark.asyncio
async def test_snapshot_partial_missing_does_not_break(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """funding 查空 → 该因子 None,其余 6 因子照常(单因子缺失不阻塞整体)。"""
    _patch_all(monkeypatch, funding_empty=True)
    snap = await build_structure_snapshot(object(), "BTCUSDT")
    assert snap.funding_rate is None
    assert snap.account_long_short is not None
    assert snap.open_interest is not None
    assert snap.basis is not None
    assert snap.sentiment is not None


@pytest.mark.asyncio
async def test_snapshot_factor_exception_degrades_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """读层抛异常 → 该因子 None 不上抛(_safe 兜底)。"""
    _patch_all(monkeypatch)

    async def boom(client: Any, symbol: str, *, limit: int) -> list[OpenInterest]:  # noqa: ARG001
        msg = "CH down"
        raise RuntimeError(msg)

    monkeypatch.setattr(snap_mod, "select_open_interest", boom)
    snap = await build_structure_snapshot(object(), "BTCUSDT")
    assert snap.open_interest is None
    assert snap.account_long_short is not None  # 其余不受影响
