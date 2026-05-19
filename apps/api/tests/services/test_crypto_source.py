"""ccxt crypto_source 单元测试(mock SDK,不打外网)。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from ccxt.base.errors import BadSymbol, NetworkError, RateLimitExceeded

from app.services.data_sources.crypto_source import CcxtBinanceCryptoSource
from app.services.data_sources.exceptions import (
    RateLimitError,
    SymbolNotFoundError,
    UpstreamUnavailableError,
)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())


class _FakeBinance:
    """伪 ccxt async binance,fetch_ohlcv 返回 fixture 数据,close 是 no-op。"""

    def __init__(
        self,
        ohlcv: list[list[float]] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._ohlcv = ohlcv or []
        self._exc = exc
        self.fetch_called_with: tuple | None = None

    async def fetch_ohlcv(self, symbol: str, *, timeframe: str, limit: int) -> list[list[float]]:
        self.fetch_called_with = (symbol, timeframe, limit)
        if self._exc is not None:
            raise self._exc
        return self._ohlcv

    async def close(self) -> None:
        pass


def _patch_ccxt(monkeypatch: pytest.MonkeyPatch, fake: _FakeBinance) -> None:
    import ccxt.async_support as ccxt_async
    monkeypatch.setattr(ccxt_async, "binance", lambda _kwargs=None: fake)


@pytest.fixture
def src() -> CcxtBinanceCryptoSource:
    return CcxtBinanceCryptoSource()


class TestOhlcvMapping:
    async def test_basic(
        self, src: CcxtBinanceCryptoSource, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # ccxt 返回 [ts_ms, O, H, L, C, V]
        ohlcv = [
            [1_715_000_000_000, 100.0, 105.0, 99.0, 104.0, 1.5],
            [1_715_086_400_000, 104.0, 110.0, 103.0, 108.0, 2.0],
        ]
        fake = _FakeBinance(ohlcv=ohlcv)
        _patch_ccxt(monkeypatch, fake)

        rows = await src.fetch_kline("BTC/USDT", "1d", limit=10)
        assert len(rows) == 2
        # ms → UTC datetime
        assert rows[0].ts == datetime.fromtimestamp(1_715_000_000, tz=UTC)
        assert rows[0].open == 100.0
        assert rows[0].volume == 1.5
        # ccxt 不提供 quote volume
        assert rows[0].amount is None

    async def test_fetch_passes_timeframe(
        self, src: CcxtBinanceCryptoSource, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake = _FakeBinance(ohlcv=[[1_715_000_000_000, 1.0, 2.0, 0.5, 1.5, 10.0]])
        _patch_ccxt(monkeypatch, fake)
        await src.fetch_kline("BTC/USDT", "1h", limit=42)
        assert fake.fetch_called_with == ("BTC/USDT", "1h", 42)


class TestErrorMapping:
    async def test_bad_symbol(
        self, src: CcxtBinanceCryptoSource, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake = _FakeBinance(exc=BadSymbol("binance does not have market symbol XYZ/USDT"))
        _patch_ccxt(monkeypatch, fake)
        with pytest.raises(SymbolNotFoundError):
            await src.fetch_kline("XYZ/USDT", "1d", limit=5)

    async def test_rate_limit(
        self, src: CcxtBinanceCryptoSource, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake = _FakeBinance(exc=RateLimitExceeded("429"))
        _patch_ccxt(monkeypatch, fake)
        with pytest.raises(RateLimitError):
            await src.fetch_kline("BTC/USDT", "1d", limit=5)

    async def test_network_error(
        self, src: CcxtBinanceCryptoSource, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake = _FakeBinance(exc=NetworkError("connection refused"))
        _patch_ccxt(monkeypatch, fake)
        with pytest.raises(UpstreamUnavailableError):
            await src.fetch_kline("BTC/USDT", "1d", limit=5)

    async def test_empty_ohlcv(
        self, src: CcxtBinanceCryptoSource, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake = _FakeBinance(ohlcv=[])
        _patch_ccxt(monkeypatch, fake)
        with pytest.raises(SymbolNotFoundError):
            await src.fetch_kline("BTC/USDT", "1d", limit=5)


class TestListSymbols:
    async def test_demo_list(self, src: CcxtBinanceCryptoSource) -> None:
        metas = await src.list_symbols()
        assert len(metas) == 10
        symbols = {m.symbol for m in metas}
        assert "BTC/USDT" in symbols
        assert "ETH/USDT" in symbols
