"""结构快照 service 单测 · mock CH 读层(零真实 CH/Redis · 本地可跑)。

覆盖:7 因子聚合形状 + window 口径字段 + 单因子缺失不崩 + symbol 归一。
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

import app.services.structure.snapshot as snap_mod
from app.schemas.crypto import (
    DEPTH_LEVELS,
    FearGreedPoint,
    FundingRate,
    LongShortRatio,
    MarketOverview,
    OpenInterest,
    OrderbookDepth,
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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" btc/usdt ", "BTCUSDT"),
        ("ETH-USDT", "ETHUSDT"),
        # symbol 模糊输入刀:无后缀补 USDT(Hans 实证 "eth" 查空的根治)
        ("eth", "ETHUSDT"),
        ("ETHUSDT", "ETHUSDT"),  # 已规范 → 原样
        ("btcusdc", "BTCUSDC"),  # 已带其它 quote 后缀 → 不误补(诚实 null 路径)
        ("ETH/USDT", "ETHUSDT"),
        ("usdc", "USDCUSDT"),  # 纯 quote 词不算带后缀(len 不大于后缀)→ 补 USDT(币安真有此对)
    ],
)
def test_normalize_symbol(raw: str, expected: str) -> None:
    assert normalize_symbol(raw) == expected


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


# ── 二批刀3 · 第 12 因子盘口深度(spread/imbalance)──────────────────────────────


@pytest.mark.asyncio
async def test_snapshot_depth_factor_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """有盘口数据 → depth 因子出格(spread/imbalance 由纯函数算 · window=latest)。"""
    _patch_all(monkeypatch)
    depth = OrderbookDepth(
        symbol="BTCUSDT", ts=_TS,
        bids=tuple((100.0, 3.0) for _ in range(DEPTH_LEVELS)),  # Σbid=30
        asks=tuple((102.0, 1.0) for _ in range(DEPTH_LEVELS)),  # Σask=10 → imbalance=3
    )

    async def fake_depth(client: Any, symbol: str) -> OrderbookDepth:  # noqa: ARG001
        return depth

    monkeypatch.setattr(snap_mod, "select_latest_depth", fake_depth)
    snap = await build_structure_snapshot(object(), "BTCUSDT")
    assert snap.depth is not None
    assert snap.depth.window == "latest"
    assert snap.depth.value["imbalance"] == 3.0          # Σbid/Σask=30/10
    assert abs(snap.depth.value["spread_pct"] - (2.0 / 101.0)) < 1e-5  # (102-100)/101


@pytest.mark.asyncio
async def test_snapshot_depth_missing_leaves_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """无盘口数据(select 返 None)→ depth 留白 None(如实不伪造)。"""
    _patch_all(monkeypatch)

    async def no_depth(client: Any, symbol: str) -> None:  # noqa: ARG001
        return None

    monkeypatch.setattr(snap_mod, "select_latest_depth", no_depth)
    snap = await build_structure_snapshot(object(), "BTCUSDT")
    assert snap.depth is None
    assert snap.account_long_short is not None  # 其余因子不受影响
