"""盘口深度因子纯函数单测(沙盘三期第二批 · 刀2)· 不依赖 CH。

🔴 红线:只读盘口结构算因子 · 不撮合不预测价格。
口径钉死:spread=(ask1-bid1)/mid · imbalance=Σbid_qty/Σask_qty(全 10 档)·
脏数据(0 价/缺档/单边空)如实留白 None,不伪造不除零。
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.schemas.crypto import DEPTH_LEVELS, OrderbookDepth
from app.services.structure.depth_factors import (
    best_bid_ask,
    imbalance,
    spread_pct,
)

_TS = datetime(2026, 6, 14, 0, 0, 0, tzinfo=UTC)


def _depth(
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    symbol: str = "BTCUSDT",
) -> OrderbookDepth:
    """造 depth · bids/asks 补 (0,0) 到 DEPTH_LEVELS 档(模拟解析层定长)。"""
    def pad(levels: list[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
        out = list(levels[:DEPTH_LEVELS])
        while len(out) < DEPTH_LEVELS:
            out.append((0.0, 0.0))
        return tuple(out)

    return OrderbookDepth(symbol=symbol, ts=_TS, bids=pad(bids), asks=pad(asks))


# ── spread ───────────────────────────────────────────────────────────────────


def test_spread_pct_basic() -> None:
    """(102-100)/((102+100)/2) = 2/101。"""
    d = _depth([(100.0, 1.0)], [(102.0, 1.0)])
    v = spread_pct(d)
    assert v is not None
    assert abs(v - (2.0 / 101.0)) < 1e-12


def test_spread_pct_tight_book_near_zero() -> None:
    """买一卖一贴合 → spread → 0(流动性好)。"""
    d = _depth([(100.0, 5.0)], [(100.01, 5.0)])
    v = spread_pct(d)
    assert v is not None
    assert 0 < v < 0.001


def test_spread_pct_missing_side_none() -> None:
    """单边空(asks 全 0)→ None(脏数据留白)。"""
    assert spread_pct(_depth([(100.0, 1.0)], [])) is None
    assert spread_pct(_depth([], [(102.0, 1.0)])) is None  # bid 空


def test_spread_pct_zero_price_none() -> None:
    """bid1/ask1 价为 0 → None。"""
    assert spread_pct(_depth([(0.0, 1.0)], [(102.0, 1.0)])) is None
    assert spread_pct(_depth([(100.0, 1.0)], [(0.0, 1.0)])) is None


# ── imbalance ─────────────────────────────────────────────────────────────────


def test_imbalance_bid_heavy() -> None:
    """Σbid_qty=5 / Σask_qty=2 = 2.5(买盘厚 >1)· 全 10 档求和。"""
    d = _depth([(100.0, 3.0), (99.0, 2.0)], [(102.0, 1.0), (103.0, 1.0)])
    v = imbalance(d)
    assert v is not None
    assert abs(v - 2.5) < 1e-12


def test_imbalance_ask_heavy_below_one() -> None:
    """Σbid=1 / Σask=4 = 0.25(卖盘厚 <1)。"""
    d = _depth([(100.0, 1.0)], [(102.0, 1.0), (103.0, 3.0)])
    v = imbalance(d)
    assert v is not None
    assert abs(v - 0.25) < 1e-12


def test_imbalance_pad_zero_levels_equivalent_to_valid_only() -> None:
    """补 0 档贡献 0 → 全 10 档求和 == 只算有效档(口径自洽)。"""
    d = _depth([(100.0, 3.0)], [(102.0, 6.0)])
    v = imbalance(d)
    assert v is not None
    assert abs(v - 0.5) < 1e-12


def test_imbalance_missing_side_none() -> None:
    """单边空 / 0 价 → None(best_bid_ask 拦 · 不除零)。"""
    assert imbalance(_depth([(100.0, 1.0)], [])) is None       # ask 空
    assert imbalance(_depth([], [(102.0, 1.0)])) is None       # bid 空
    assert imbalance(_depth([(0.0, 1.0)], [(102.0, 1.0)])) is None  # bid1 价 0


# ── best_bid_ask ──────────────────────────────────────────────────────────────


def test_best_bid_ask_valid_and_dirty() -> None:
    assert best_bid_ask(_depth([(100.0, 1.0)], [(102.0, 1.0)])) == (100.0, 102.0)
    assert best_bid_ask(_depth([(0.0, 0.0)], [(102.0, 1.0)])) is None
    assert best_bid_ask(_depth([], [])) is None
