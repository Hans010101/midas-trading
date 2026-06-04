"""KLINE-001 K线图 PNG 端点测试 · GET /api/v1/chart/kline.png(fetch-on-miss)。

fake CH + fake 数据源(不连真库/真上游)· 覆盖:
- CH 已有足量 → 直接画(不回源)
- ★CH 不足 → 回源(fetch-on-miss)→ 出图(非预存符号也能画 · 修复大面积 404)
- 回源后仍不足(冷门无数据)→ 404(调用方 bot 回退网页链接 · fallback 保留)
- crypto 走 perp(binance_futures 源)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.api.deps import (
    get_binance_futures_source,
    get_clickhouse,
    get_cn_source,
    get_hk_source,
    get_us_source,
)
from app.main import app
from app.schemas.market import Kline

_BASE = datetime(2026, 1, 1, tzinfo=UTC)
_SRC_GETTERS = (get_cn_source, get_us_source, get_hk_source, get_binance_futures_source)


def _klines(n: int) -> list[Kline]:
    out: list[Kline] = []
    price = 100.0
    for i in range(n):
        drift = 0.02 if i % 3 == 0 else (-0.015 if i % 3 == 1 else 0.005)
        close = max(1.0, price * (1 + drift))
        out.append(Kline(ts=_BASE + timedelta(days=i), open=round(price, 4),
                         high=round(max(price, close) * 1.008, 4),
                         low=round(min(price, close) * 0.992, 4),
                         close=round(close, 4), volume=1000.0 + i))
        price = close
    return out


class _FakeCH:
    def __init__(self, cached: list[Kline]) -> None:
        self._cached = cached

    async def select_kline(self, **_kwargs: Any) -> list[Kline]:  # noqa: ANN401
        return self._cached

    async def insert_kline(self, *_a: Any, **_k: Any) -> int:  # noqa: ANN401
        return 0  # 回源写库 no-op


class _FakeSource:
    def __init__(self, klines: list[Kline]) -> None:
        self._klines = klines

    async def fetch_kline(self, _symbol: str, _period: str, *, limit: int) -> list[Kline]:
        return self._klines[:limit]


def _override(cached: list[Kline], upstream: list[Kline]) -> None:
    app.dependency_overrides[get_clickhouse] = lambda: _FakeCH(cached)
    fake_src = _FakeSource(upstream)
    for getter in _SRC_GETTERS:
        app.dependency_overrides[getter] = lambda fs=fake_src: fs


@pytest.fixture(autouse=True)
def _clear() -> Any:  # noqa: ANN401
    yield
    for g in (get_clickhouse, *_SRC_GETTERS):
        app.dependency_overrides.pop(g, None)


@pytest.mark.asyncio
async def test_chart_cached_sufficient_returns_png(client: AsyncClient) -> None:
    """CH 已有足量 → 直接画(不回源)→ 200 image/png。"""
    _override(cached=_klines(120), upstream=[])
    r = await client.get("/api/v1/chart/kline.png?market=cn&symbol=600519&name=贵州茅台")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_chart_fetch_on_miss_renders(client: AsyncClient) -> None:
    """★CH 不足 → 回源 → 出图(非预存符号也能画 · 不再 404 fallback)。"""
    _override(cached=_klines(5), upstream=_klines(120))
    r = await client.get("/api/v1/chart/kline.png?market=cn&symbol=000001&name=平安银行")
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_chart_crypto_fetch_on_miss_perp(client: AsyncClient) -> None:
    """★crypto 不足 → 回源(binance_futures perp)→ 出图。"""
    _override(cached=[], upstream=_klines(120))
    r = await client.get("/api/v1/chart/kline.png?market=crypto&symbol=BTC/USDT&name=比特币")
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_chart_insufficient_after_fetch_404(client: AsyncClient) -> None:
    """回源后仍不足(冷门无数据)→ 404(bot 回退网页链接 · fallback 保留)。"""
    _override(cached=_klines(5), upstream=_klines(5))
    r = await client.get("/api/v1/chart/kline.png?market=cn&symbol=ZZZZ&name=冷门")
    assert r.status_code == 404
