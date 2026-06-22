"""binance_futures ticker 解析容错单测(fix/ticker-scan-quotevolume-keyerror)。

★根因:某币偶发缺 quoteVolume → _parse_ticker_row 硬取 row["quoteVolume"] KeyError →
原列表推导「全有或全无」→ fetch_ticker_24h 整体崩(在 insert 之前)→ crypto_ticker_24h
唯一写者永不执行 → universe / 涨跌榜冻结在上一好轮。
修:量字段 .get 默认 0(ge=0 安全 · 保留该币、成交额垫底)+ fetch 单行 try 跳过 + warn。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.data_sources.binance_futures_source import (
    BinanceFuturesSource,
    _parse_ticker_row,
)


def _full_row(symbol: str = "BTCUSDT") -> dict[str, object]:
    return {
        "symbol": symbol, "lastPrice": "68500.0", "priceChangePercent": "2.5",
        "highPrice": "69000.0", "lowPrice": "67000.0",
        "volume": "12345.6", "quoteVolume": "840000000.0", "count": 100,
    }


class TestParseTickerRow:
    def test_full_row(self) -> None:
        t = _parse_ticker_row(_full_row(), instrument="perp")
        assert t.symbol == "BTC/USDT"
        assert t.last_price == 68500.0
        assert t.quote_volume_24h == 840000000.0

    def test_missing_quote_volume_defaults_zero(self) -> None:
        # ★根因复现:缺 quoteVolume → 不再 KeyError,以 0 量入库
        row = _full_row()
        del row["quoteVolume"]
        t = _parse_ticker_row(row, instrument="perp")
        assert t.quote_volume_24h == 0.0
        assert t.last_price == 68500.0  # 其余字段正常解析

    def test_missing_volume_defaults_zero(self) -> None:
        row = _full_row()
        del row["volume"]
        assert _parse_ticker_row(row, instrument="perp").volume_24h == 0.0

    def test_missing_price_raises(self) -> None:
        # 价字段(schema gt=0)缺 → 抛错(由 fetch 单行 try 跳过该币 · 默认 0 会撞 gt=0)
        row = _full_row()
        del row["lastPrice"]
        with pytest.raises(KeyError):
            _parse_ticker_row(row, instrument="perp")

    def test_missing_symbol_raises(self) -> None:
        # 错误对象 {code,msg} 无 symbol → 抛错(由 fetch 单行 try 跳过)
        row = _full_row()
        del row["symbol"]
        with pytest.raises(KeyError):
            _parse_ticker_row(row, instrument="perp")


class TestFetchTickerResilience:
    async def test_one_bad_row_does_not_kill_fetch(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # 混合:2 好 + 1 缺 quoteVolume(现以 0 入)+ 1 缺价(跳过)+ 1 错误对象(跳过)
        no_qv = _full_row("TNSRUSDT")
        del no_qv["quoteVolume"]
        no_price = _full_row("BADUSDT")
        del no_price["lastPrice"]
        err_obj = {"code": -1003, "msg": "rate limited"}
        rows = [_full_row("BTCUSDT"), _full_row("ETHUSDT"), no_qv, no_price, err_obj]

        source = BinanceFuturesSource()
        monkeypatch.setattr(source, "_get_json", AsyncMock(return_value=rows))
        try:
            tickers = await source.fetch_ticker_24h()
        finally:
            await source.close()

        syms = {t.symbol for t in tickers}
        # ★好的 + 缺 quoteVolume 的(0 量)都入库;缺价 / 错误对象被跳过,整轮不崩
        assert syms == {"BTC/USDT", "ETH/USDT", "TNSR/USDT"}
        tnsr = next(t for t in tickers if t.symbol == "TNSR/USDT")
        assert tnsr.quote_volume_24h == 0.0
