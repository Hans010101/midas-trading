"""kline 新鲜度 helper 单测(刀A2-1)· fake ch/source 纯内存 · 不需要 PG/CH。

覆盖:阈值映射 · crypto 新鲜不回源 / stale 回源 · 非 crypto 不启新鲜度(行数不足
仍回源 = 原行为)· perp fetch symbol 归一 · 上游失败降级/透传 · source=None 退化。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.schemas.market import Kline
from app.services.clickhouse_client import normalize_kline_symbol
from app.services.data_sources.exceptions import UpstreamUnavailableError
from app.services.kline_freshness import get_fresh_kline, is_stale

NOW = datetime(2026, 6, 11, 12, 0, tzinfo=UTC)


def _k(ts: datetime, close: float = 1.0) -> Kline:
    # OHLC 全用同一价(模型校验 close ∈ [low, high])
    return Kline(ts=ts, open=close, high=close, low=close, close=close, volume=1, amount=1)


class FakeCH:
    """只实现 select/insert_kline 的最小桩(get_fresh_kline 仅用这两个)。"""

    def __init__(self, rows: list[Kline]) -> None:
        self.rows = rows
        self.insert_calls: list[tuple[list[Kline], dict[str, Any]]] = []

    async def select_kline(self, **_kw: Any) -> list[Kline]:
        return self.rows

    async def insert_kline(self, rows: list[Kline], **kw: Any) -> int:
        self.insert_calls.append((rows, kw))
        return len(rows)


class FakeSource:
    def __init__(
        self, rows: list[Kline] | None = None, exc: Exception | None = None,
    ) -> None:
        self.rows = rows or []
        self.exc = exc
        self.calls: list[tuple[str, str, int]] = []

    async def fetch_kline(self, symbol: str, period: str, limit: int = 500) -> list[Kline]:
        self.calls.append((symbol, period, limit))
        if self.exc is not None:
            raise self.exc
        return self.rows


# ── is_stale 阈值映射(period 7 档关键 4 档)─────────────────────────────────


@pytest.mark.parametrize(
    ("period", "seconds"),
    [("15m", 900), ("1h", 3600), ("1d", 86400), ("1w", 604800)],
)
def test_is_stale_thresholds(period: str, seconds: int) -> None:
    within = NOW - timedelta(seconds=seconds)  # 恰好 1×period → 不算过期(> 才算)
    beyond = NOW - timedelta(seconds=seconds + 1)
    assert is_stale(within, period, NOW) is False  # type: ignore[arg-type]
    assert is_stale(beyond, period, NOW) is True  # type: ignore[arg-type]


def test_is_stale_naive_ts_treated_as_utc() -> None:
    naive = (NOW - timedelta(days=3)).replace(tzinfo=None)
    assert is_stale(naive, "1d", NOW) is True


# ── crypto:新鲜不回源 · stale 回源 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_crypto_fresh_no_refetch() -> None:
    ch = FakeCH([_k(NOW - timedelta(hours=2))])  # 1d 末根 2h 前 → 新鲜
    source = FakeSource()
    out = await get_fresh_kline(
        ch, symbol="BTCUSDT", market="crypto", period="1d", limit=1,  # type: ignore[arg-type]
        instrument="perp", source=source, now=NOW,
    )
    assert source.calls == []  # 未回源
    assert ch.insert_calls == []
    assert out == ch.rows


@pytest.mark.asyncio
async def test_crypto_stale_refetch_and_persist() -> None:
    ch = FakeCH([_k(NOW - timedelta(days=3), close=0.09)])  # 1d 末根 3 天前 → stale
    fresh = [_k(NOW - timedelta(hours=1), close=0.18)]
    source = FakeSource(rows=fresh)
    out = await get_fresh_kline(
        ch, symbol="BTCUSDT", market="crypto", period="1d", limit=1,  # type: ignore[arg-type]
        instrument="perp", source=source, now=NOW,
    )
    assert len(source.calls) == 1  # 回源了
    assert len(ch.insert_calls) == 1  # persist 了
    assert out == fresh


@pytest.mark.asyncio
async def test_crypto_perp_fetch_symbol_normalized() -> None:
    """上游 fetch 用 Binance 无斜杠形态(BTC/USDT → BTCUSDT)。"""
    ch = FakeCH([_k(NOW - timedelta(days=3))])
    source = FakeSource(rows=[_k(NOW)])
    await get_fresh_kline(
        ch, symbol="BTC/USDT", market="crypto", period="1d", limit=1,  # type: ignore[arg-type]
        instrument="perp", source=source, now=NOW,
    )
    assert source.calls[0][0] == "BTCUSDT"


# ── 非 crypto:不启新鲜度 · 行数不足仍回源(原行为保留)───────────────────────


@pytest.mark.asyncio
async def test_non_crypto_old_but_full_no_refetch() -> None:
    """cn 末根 30 天前但行数足 → 不回源(采集任务保新鲜 · 避免周末无谓打上游)。"""
    ch = FakeCH([_k(NOW - timedelta(days=30))])
    source = FakeSource(rows=[_k(NOW)])
    out = await get_fresh_kline(
        ch, symbol="600519", market="cn", period="1d", limit=1,  # type: ignore[arg-type]
        source=source, now=NOW,
    )
    assert source.calls == []
    assert out == ch.rows


@pytest.mark.asyncio
async def test_non_crypto_insufficient_rows_refetch() -> None:
    """cn 行数不足 limit → 回源(改造前行为 · 首访回填不变)。"""
    ch = FakeCH([])
    source = FakeSource(rows=[_k(NOW)])
    out = await get_fresh_kline(
        ch, symbol="600519", market="cn", period="1d", limit=1,  # type: ignore[arg-type]
        source=source, now=NOW,
    )
    assert len(source.calls) == 1
    assert out == source.rows


# ── 上游失败:有缓存降级 · 空缓存透传 · source=None 退化 ─────────────────────


@pytest.mark.asyncio
async def test_degrade_to_cache_on_upstream_error() -> None:
    cached = [_k(NOW - timedelta(days=3))]
    ch = FakeCH(cached)
    source = FakeSource(exc=UpstreamUnavailableError("boom", market="crypto", symbol="X"))
    out = await get_fresh_kline(
        ch, symbol="XUSDT", market="crypto", period="1d", limit=1,  # type: ignore[arg-type]
        instrument="perp", source=source, now=NOW,
    )
    assert out == cached  # 降级返回缓存 · 不抛


@pytest.mark.asyncio
async def test_raise_on_upstream_error_with_empty_cache() -> None:
    ch = FakeCH([])
    source = FakeSource(exc=UpstreamUnavailableError("boom", market="crypto", symbol="X"))
    with pytest.raises(UpstreamUnavailableError):
        await get_fresh_kline(
            ch, symbol="XUSDT", market="crypto", period="1d", limit=1,  # type: ignore[arg-type]
            instrument="perp", source=source, now=NOW,
        )


@pytest.mark.asyncio
async def test_source_none_pure_cache() -> None:
    """source=None(测试/无 lifespan)→ 即便 stale 也纯读缓存 = 改造前行为。"""
    cached = [_k(NOW - timedelta(days=9))]
    ch = FakeCH(cached)
    out = await get_fresh_kline(
        ch, symbol="BTCUSDT", market="crypto", period="1d", limit=1,  # type: ignore[arg-type]
        instrument="perp", source=None, now=NOW,
    )
    assert out == cached


# ── symbol 归一纯函数 ────────────────────────────────────────────────────────


def test_normalize_kline_symbol() -> None:
    assert normalize_kline_symbol("BTC/USDT", "crypto", "perp") == "BTCUSDT"
    assert normalize_kline_symbol("BTCUSDT", "crypto", "perp") == "BTCUSDT"  # 已归一不变
    assert normalize_kline_symbol("BTC/USDT", "crypto", "spot") == "BTC/USDT"  # spot 不动
    assert normalize_kline_symbol("600519", "cn", "spot") == "600519"  # 股票不动
