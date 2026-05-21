"""BinanceFuturesSource 单元测试 · 全部用 httpx.MockTransport 不打外网。

M2-A 范围:核心解析路径 + 错误映射 · 7 个测试。
M2-B 联调时:补集成测试(打真 fapi.binance.com)。
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.data_sources.binance_futures_source import (
    BinanceFuturesSource,
    _merge_long_short,
    _to_binance_symbol,
    _to_ccxt_symbol,
)
from app.services.data_sources.exceptions import (
    DataFormatError,
    RateLimitError,
    SymbolNotFoundError,
    UpstreamUnavailableError,
)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """禁止 BaseDataSource._retry 真睡眠 · 加速测试。"""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())


def _make_source(handler: Any) -> BinanceFuturesSource:
    """用 MockTransport 注入响应 · 不打外网。"""
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return BinanceFuturesSource(client=client)


# ============================================================================
# 1 · fetch_kline 成功路径
# ============================================================================


@pytest.mark.asyncio
async def test_fetch_kline_parses_binance_array_response() -> None:
    """Binance fapi/v1/klines 返回 array of arrays · 字段顺序固定。"""
    def handler(req: httpx.Request) -> httpx.Response:
        assert "klines" in str(req.url)
        # 2 根 K · 字段:[openTime, open, high, low, close, volume, closeTime,
        # quoteVolume, trades, takerBuyBase, takerBuyQuote, ignore]
        return httpx.Response(200, json=[
            [1716230400000, "60000", "60100", "59900", "60050", "100", 1716230459999, "6005000", 1234, "50", "3000000", "0"],
            [1716230460000, "60050", "60200", "60000", "60150", "120", 1716230519999, "7218000", 1500, "60", "3600000", "0"],
        ])

    src = _make_source(handler)
    try:
        klines = await src.fetch_kline("BTCUSDT", "1m", limit=2)
        assert len(klines) == 2
        assert klines[0].close == 60050
        assert klines[1].high == 60200
        # ts 必须 tz-aware UTC
        assert klines[0].ts.tzinfo is not None
    finally:
        await src.close()


# ============================================================================
# 2 · fetch_funding_rate 解析
# ============================================================================


@pytest.mark.asyncio
async def test_fetch_funding_rate_parses_dict_response() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[
            {"symbol": "BTCUSDT", "fundingTime": 1716230400000, "fundingRate": "0.0001", "markPrice": "60000.5"},
            {"symbol": "BTCUSDT", "fundingTime": 1716259200000, "fundingRate": "0.00012", "markPrice": "60100.0"},
        ])

    src = _make_source(handler)
    try:
        rates = await src.fetch_funding_rate("BTCUSDT", limit=2)
        assert len(rates) == 2
        assert rates[0].rate == 0.0001
        assert rates[1].mark_price == 60100.0
    finally:
        await src.close()


# ============================================================================
# 3 · 错误映射 · 429 → RateLimitError
# ============================================================================


@pytest.mark.asyncio
async def test_429_maps_to_rate_limit_error() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too Many Requests")

    src = _make_source(handler)
    try:
        with pytest.raises(RateLimitError):
            await src.fetch_kline("BTCUSDT", "1m", limit=10)
    finally:
        await src.close()


# ============================================================================
# 4 · 错误映射 · 404 → SymbolNotFoundError(终态 · 不重试)
# ============================================================================


@pytest.mark.asyncio
async def test_404_maps_to_symbol_not_found() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Invalid symbol")

    src = _make_source(handler)
    try:
        with pytest.raises(SymbolNotFoundError):
            await src.fetch_kline("FAKECOIN", "1m", limit=10)
    finally:
        await src.close()


# ============================================================================
# 5 · 错误映射 · 5xx → UpstreamUnavailableError
# ============================================================================


@pytest.mark.asyncio
async def test_500_maps_to_upstream_unavailable() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    src = _make_source(handler)
    try:
        with pytest.raises(UpstreamUnavailableError):
            await src.fetch_kline("BTCUSDT", "1m", limit=10)
    finally:
        await src.close()


# ============================================================================
# 6 · long_short merge · 三 endpoint timestamp 对齐
# ============================================================================


def test_merge_long_short_aligns_by_timestamp() -> None:
    """三 endpoint 返回不完全对齐时 · 应该只取三者交集 ts。"""
    account = [
        {"timestamp": 1000, "longAccount": "0.6", "shortAccount": "0.4", "longShortRatio": "1.5"},
        {"timestamp": 2000, "longAccount": "0.7", "shortAccount": "0.3", "longShortRatio": "2.3"},
    ]
    position = [
        {"timestamp": 1000, "longAccount": "0.55", "shortAccount": "0.45", "longShortRatio": "1.2"},
        # 缺 timestamp=2000 · 这条不应出现在结果里
    ]
    taker = [
        {"timestamp": 1000, "buyVol": "100", "sellVol": "80", "buySellRatio": "1.25"},
        {"timestamp": 2000, "buyVol": "200", "sellVol": "150", "buySellRatio": "1.33"},
    ]
    result = _merge_long_short(
        account=account, position=position, taker=taker, symbol="BTCUSDT",
    )
    assert len(result) == 1
    assert result[0].top_account_long == 0.6
    assert result[0].top_position_long == 0.55


# ============================================================================
# 7 · symbol 格式互转
# ============================================================================


def test_symbol_format_conversion() -> None:
    assert _to_ccxt_symbol("BTCUSDT") == "BTC/USDT"
    assert _to_ccxt_symbol("ETHUSDC") == "ETH/USDC"
    assert _to_ccxt_symbol("WEIRDCOIN") == "WEIRDCOIN"  # 不认识的 quote · 退回原值
    assert _to_binance_symbol("BTC/USDT") == "BTCUSDT"


# ============================================================================
# 8 · ticker_24h 返回 ccxt 风格 symbol
# ============================================================================


@pytest.mark.asyncio
async def test_ticker_24h_returns_ccxt_symbol() -> None:
    """Binance fapi/v1/ticker/24hr 返 BTCUSDT · adapter 应转 BTC/USDT。"""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[
            {
                "symbol": "BTCUSDT", "lastPrice": "60000",
                "priceChangePercent": "2.5", "highPrice": "61000",
                "lowPrice": "59000", "volume": "10000", "quoteVolume": "600000000",
                "count": 12345,
            },
        ])

    src = _make_source(handler)
    try:
        tickers = await src.fetch_ticker_24h()
        assert len(tickers) == 1
        assert tickers[0].symbol == "BTC/USDT"   # ccxt 风格
        assert tickers[0].instrument == "perp"
        assert tickers[0].last_price == 60000
        assert tickers[0].change_pct_24h == 2.5
    finally:
        await src.close()
