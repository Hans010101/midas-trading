"""yfinance us_source 单元测试(mock SDK,不打外网)。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.services.data_sources.exceptions import SymbolNotFoundError, UpstreamUnavailableError
from app.services.data_sources.us_source import YFinanceUsSource

ET = ZoneInfo("America/New_York")


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())


class _FakeTicker:
    """伪 yf.Ticker,只暴露 history()。"""

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def history(self, **kwargs: object) -> pd.DataFrame:  # noqa: ARG002
        return self._df


def _patch_yf(monkeypatch: pytest.MonkeyPatch, df: pd.DataFrame) -> None:
    """让 yf.Ticker(symbol) 返回我们的 _FakeTicker。"""
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", lambda _symbol: _FakeTicker(df))


@pytest.fixture
def src() -> YFinanceUsSource:
    return YFinanceUsSource()


class TestDailyMapping:
    async def test_basic(self, src: YFinanceUsSource, monkeypatch: pytest.MonkeyPatch) -> None:
        idx = pd.DatetimeIndex(
            [datetime(2025, 5, 5, tzinfo=ET), datetime(2025, 5, 6, tzinfo=ET)],
            name="Date",
        )
        df = pd.DataFrame(
            {
                "Open": [100.0, 101.0],
                "High": [105.0, 106.0],
                "Low": [99.0, 100.0],
                "Close": [104.0, 105.0],
                "Volume": [1_000_000.0, 1_200_000.0],
                "Dividends": [0.0, 0.0],
                "Stock Splits": [0.0, 0.0],
            },
            index=idx,
        )
        _patch_yf(monkeypatch, df)

        rows = await src.fetch_kline("NVDA", "1d", limit=10)
        assert len(rows) == 2
        # ET 午夜 → UTC(EDT 早 4 小时)
        assert rows[0].ts == datetime(2025, 5, 5, 4, 0, tzinfo=UTC)
        assert rows[0].open == 100.0
        assert rows[0].volume == 1_000_000.0
        # yfinance 不提供成交额
        assert rows[0].amount is None


class TestEmptyResponse:
    async def test_empty_df_raises_symbol_not_found(
        self, src: YFinanceUsSource, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_yf(monkeypatch, pd.DataFrame())
        with pytest.raises(SymbolNotFoundError):
            await src.fetch_kline("XYZNOTREAL", "1d", limit=10)


class TestNetworkError:
    async def test_connection_error_mapped(
        self, src: YFinanceUsSource, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import yfinance as yf

        def _raise_ticker(_sym: str) -> object:
            class _BoomTicker:
                def history(self, **kwargs: object) -> pd.DataFrame:  # noqa: ARG002
                    raise ConnectionError("Yahoo down")

            return _BoomTicker()

        monkeypatch.setattr(yf, "Ticker", _raise_ticker)
        with pytest.raises(UpstreamUnavailableError):
            await src.fetch_kline("NVDA", "1d", limit=10)


class TestListSymbols:
    async def test_demo_list(self, src: YFinanceUsSource) -> None:
        metas = await src.list_symbols()
        assert len(metas) == 10
        symbols = {m.symbol for m in metas}
        assert "NVDA" in symbols
        assert "SPY" in symbols
        assert "QQQ" in symbols
