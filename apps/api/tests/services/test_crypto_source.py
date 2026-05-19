"""ccxt crypto_source 单元测试(fake exchange 注入,不打外网)。"""

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


class _FakeExchange:
    """伪 ccxt async exchange。

    `close()` 故意是 no-op —— 适配器不应该 close 它(lifespan 负责)。
    """

    def __init__(
        self,
        ohlcv: list[list[float]] | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._ohlcv = ohlcv or []
        self._exc = exc
        self.fetch_called_with: tuple | None = None
        self.close_called = False

    async def fetch_ohlcv(
        self, symbol: str, *, timeframe: str, limit: int,
    ) -> list[list[float]]:
        self.fetch_called_with = (symbol, timeframe, limit)
        if self._exc is not None:
            raise self._exc
        return self._ohlcv

    async def close(self) -> None:
        self.close_called = True


class TestOhlcvMapping:
    async def test_basic(self) -> None:
        ohlcv = [
            [1_715_000_000_000, 100.0, 105.0, 99.0, 104.0, 1.5],
            [1_715_086_400_000, 104.0, 110.0, 103.0, 108.0, 2.0],
        ]
        fake = _FakeExchange(ohlcv=ohlcv)
        src = CcxtBinanceCryptoSource(exchange=fake)  # type: ignore[arg-type]

        rows = await src.fetch_kline("BTC/USDT", "1d", limit=10)
        assert len(rows) == 2
        assert rows[0].ts == datetime.fromtimestamp(1_715_000_000, tz=UTC)
        assert rows[0].open == 100.0
        assert rows[0].volume == 1.5
        assert rows[0].amount is None

    async def test_fetch_passes_timeframe(self) -> None:
        fake = _FakeExchange(ohlcv=[[1_715_000_000_000, 1.0, 2.0, 0.5, 1.5, 10.0]])
        src = CcxtBinanceCryptoSource(exchange=fake)  # type: ignore[arg-type]
        await src.fetch_kline("BTC/USDT", "1h", limit=42)
        assert fake.fetch_called_with == ("BTC/USDT", "1h", 42)

    async def test_does_not_close_exchange(self) -> None:
        """适配器不能调 exchange.close() —— 那是 lifespan 的活。"""
        fake = _FakeExchange(ohlcv=[[1_715_000_000_000, 1.0, 2.0, 0.5, 1.5, 10.0]])
        src = CcxtBinanceCryptoSource(exchange=fake)  # type: ignore[arg-type]
        await src.fetch_kline("BTC/USDT", "1h", limit=5)
        assert fake.close_called is False


class TestErrorMapping:
    async def test_bad_symbol(self) -> None:
        fake = _FakeExchange(exc=BadSymbol("binance does not have market symbol XYZ/USDT"))
        src = CcxtBinanceCryptoSource(exchange=fake)  # type: ignore[arg-type]
        with pytest.raises(SymbolNotFoundError):
            await src.fetch_kline("XYZ/USDT", "1d", limit=5)

    async def test_rate_limit(self) -> None:
        fake = _FakeExchange(exc=RateLimitExceeded("429"))
        src = CcxtBinanceCryptoSource(exchange=fake)  # type: ignore[arg-type]
        with pytest.raises(RateLimitError):
            await src.fetch_kline("BTC/USDT", "1d", limit=5)

    async def test_network_error(self) -> None:
        fake = _FakeExchange(exc=NetworkError("connection refused"))
        src = CcxtBinanceCryptoSource(exchange=fake)  # type: ignore[arg-type]
        with pytest.raises(UpstreamUnavailableError):
            await src.fetch_kline("BTC/USDT", "1d", limit=5)

    async def test_empty_ohlcv(self) -> None:
        fake = _FakeExchange(ohlcv=[])
        src = CcxtBinanceCryptoSource(exchange=fake)  # type: ignore[arg-type]
        with pytest.raises(SymbolNotFoundError):
            await src.fetch_kline("BTC/USDT", "1d", limit=5)


class TestListSymbols:
    async def test_demo_list(self) -> None:
        fake = _FakeExchange()
        src = CcxtBinanceCryptoSource(exchange=fake)  # type: ignore[arg-type]
        metas = await src.list_symbols()
        assert len(metas) == 10
        symbols = {m.symbol for m in metas}
        assert "BTC/USDT" in symbols
        assert "ETH/USDT" in symbols
