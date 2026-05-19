"""AKShare cn_source 单元测试(mock SDK,不打外网)。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from app.services.data_sources.cn_source import AKShareCnSource, _to_sina_symbol
from app.services.data_sources.exceptions import (
    DataFormatError,
    SymbolNotFoundError,
    UpstreamUnavailableError,
)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())


@pytest.fixture
def src() -> AKShareCnSource:
    return AKShareCnSource()


class TestSymbolPrefix:
    def test_sh_prefix(self) -> None:
        assert _to_sina_symbol("600519") == "sh600519"
        assert _to_sina_symbol("688981") == "sh688981"

    def test_sz_prefix(self) -> None:
        assert _to_sina_symbol("000001") == "sz000001"
        assert _to_sina_symbol("300750") == "sz300750"

    def test_invalid_prefix(self) -> None:
        with pytest.raises(SymbolNotFoundError, match="无法识别"):
            _to_sina_symbol("999999")
        with pytest.raises(SymbolNotFoundError):
            _to_sina_symbol("ABCDEF")


class TestSinaDailyFetch:
    @pytest.fixture
    def _patch_sina(self, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
        calls: list[dict[str, object]] = []

        def _fake_daily(*, symbol: str, adjust: str, **kwargs: object) -> pd.DataFrame:
            calls.append({"symbol": symbol, "adjust": adjust, **kwargs})
            return pd.DataFrame(
                {
                    "date": ["2025-05-01", "2025-05-02", "2025-05-05"],
                    "open": [100.0, 102.0, 105.0],
                    "high": [105.0, 107.0, 110.0],
                    "low": [99.0, 101.0, 104.0],
                    "close": [103.0, 104.0, 108.0],
                    "volume": [5000.0, 6000.0, 7000.0],  # Sina 单位:股
                    "amount": [515000.0, 624000.0, 756000.0],
                    "outstanding_share": [1e9, 1e9, 1e9],
                    "turnover": [0.001, 0.001, 0.001],
                },
            )

        import akshare
        monkeypatch.setattr(akshare, "stock_zh_a_daily", _fake_daily)
        return calls

    async def test_daily_mapping(
        self, src: AKShareCnSource, _patch_sina: list[dict[str, object]],
    ) -> None:
        rows = await src.fetch_kline("600519", "1d", limit=10)
        assert len(rows) == 3
        # ts:Sina 日期 + 15:00 CN → 07:00 UTC
        assert rows[0].ts == datetime(2025, 5, 1, 7, 0, tzinfo=UTC)
        # OHLC
        assert rows[0].open == 100.0
        assert rows[0].close == 103.0
        # Sina 股 → 手:除 100
        assert rows[0].volume == 50.0
        assert rows[0].amount == 515000.0

    async def test_sina_called_with_sh_prefix(
        self,
        src: AKShareCnSource,
        _patch_sina: list[dict[str, object]],
    ) -> None:
        await src.fetch_kline("600519", "1d", limit=10)
        assert _patch_sina[0]["symbol"] == "sh600519"
        assert _patch_sina[0]["adjust"] == "qfq"

    async def test_empty_sina_response(
        self, src: AKShareCnSource, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import akshare
        monkeypatch.setattr(
            akshare, "stock_zh_a_daily", lambda **_: pd.DataFrame(),
        )
        with pytest.raises(SymbolNotFoundError):
            await src.fetch_kline("600519", "1d", limit=10)

    async def test_sina_connection_error(
        self, src: AKShareCnSource, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import akshare

        def _raise(**kw: object) -> pd.DataFrame:  # noqa: ARG001
            raise ConnectionError("EM down")

        monkeypatch.setattr(akshare, "stock_zh_a_daily", _raise)
        with pytest.raises(UpstreamUnavailableError):
            await src.fetch_kline("600519", "1d", limit=10)


class TestEmMinuteFetch:
    @pytest.fixture
    def _patch_em_minute(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _fake_min(*, symbol: str, period: str, adjust: str) -> pd.DataFrame:  # noqa: ARG001
            return pd.DataFrame(
                {
                    "时间": ["2025-05-05 10:00:00", "2025-05-05 11:00:00"],
                    "开盘": [100.0, 101.0],
                    "收盘": [101.0, 102.0],
                    "最高": [102.0, 103.0],
                    "最低": [99.0, 100.5],
                    "成交量": [500.0, 600.0],  # EM 已经是 手
                    "成交额": [50000.0, 61200.0],
                    "涨跌幅": [1.0, 1.0],
                    "涨跌额": [1.0, 1.0],
                    "振幅": [3.0, 2.5],
                    "换手率": [0.001, 0.001],
                },
            )

        import akshare
        monkeypatch.setattr(akshare, "stock_zh_a_hist_min_em", _fake_min)

    async def test_em_minute_mapping(
        self, src: AKShareCnSource, _patch_em_minute: None,
    ) -> None:
        rows = await src.fetch_kline("600519", "1h", limit=10)
        assert len(rows) == 2
        # ts:naive CN → UTC,10:00 CN = 02:00 UTC
        assert rows[0].ts == datetime(2025, 5, 5, 2, 0, tzinfo=UTC)
        # 成交量保持 手(EM 原始单位,不再除 100)
        assert rows[0].volume == 500.0


class TestUnsupportedPeriod:
    async def test_unsupported(self, src: AKShareCnSource) -> None:
        # 类型上不该走到这里,但运行时仍要保护
        with pytest.raises(DataFormatError):
            await src.fetch_kline("600519", "bogus", limit=10)  # type: ignore[arg-type]
