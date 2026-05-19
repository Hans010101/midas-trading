"""加密数据源适配器(ccxt Binance 现货)。

设计:
- ccxt async exchange 由外部(FastAPI lifespan / worker init)创建并注入,
  适配器**不负责生命周期**(不调 close)
- 这样多个请求共享一个 aiohttp ClientSession,避免每请求建/拆连接
- worker 侧 task per process 自己建/关 exchange(Celery 没有 lifespan)

时区:
- ccxt 返回 Unix milliseconds(UTC epoch),直接转 UTC datetime

成交额 amount:
- ccxt 标准 OHLCV 不含 quote volume → amount 字段固定 None
- 显示侧用 "—" 占位,不要在适配器里估算(产品负责人 2026-05-19 拍板)

symbol 格式:**统一用 ccxt 风格 `BTC/USDT`**(带斜杠)。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ccxt.base.errors import (
    BadSymbol,
    ExchangeError,
    NetworkError,
    RateLimitExceeded,
)

from app.schemas.market import Kline, Period, SymbolMeta
from app.services.data_sources.base import BaseDataSource
from app.services.data_sources.exceptions import (
    DataFormatError,
    RateLimitError,
    SymbolNotFoundError,
    UpstreamUnavailableError,
)

if TYPE_CHECKING:
    import ccxt.async_support as ccxt_async

logger = logging.getLogger(__name__)

# ccxt 的 timeframe 字符串和我们的 Period 一致,直接传
_VALID_PERIODS: set[Period] = {"1m", "5m", "15m", "30m", "1h", "1d", "1w"}

# M0 demo 列表(Binance 高流动性现货)
_DEMO_SYMBOLS: list[tuple[str, str]] = [
    ("BTC/USDT", "Bitcoin"),
    ("ETH/USDT", "Ethereum"),
    ("SOL/USDT", "Solana"),
    ("BNB/USDT", "BNB"),
    ("XRP/USDT", "Ripple"),
    ("DOGE/USDT", "Dogecoin"),
    ("ADA/USDT", "Cardano"),
    ("AVAX/USDT", "Avalanche"),
    ("TRX/USDT", "Tron"),
    ("LINK/USDT", "Chainlink"),
]


class CcxtBinanceCryptoSource(BaseDataSource):
    """加密数据源(Binance 现货,通过 ccxt 异步)。

    需要外部传入已经初始化好的 `ccxt.async_support.binance` 实例。
    `close()` 由外部调用方负责。
    """

    name = "ccxt-binance"
    market = "crypto"

    def __init__(self, exchange: ccxt_async.binance) -> None:
        self._exchange = exchange

    async def fetch_kline(
        self,
        symbol: str,
        period: Period,
        *,
        limit: int = 500,
    ) -> list[Kline]:
        if period not in _VALID_PERIODS:
            msg = f"ccxt 不支持的周期:{period}"
            raise DataFormatError(msg, market="crypto", symbol=symbol, upstream="ccxt-binance")

        async def _do() -> list[Kline]:
            return await self._fetch_async(symbol, period, limit)

        return await self._retry(op="fetch_kline", symbol=symbol, coro_factory=_do)

    async def list_symbols(self) -> list[SymbolMeta]:
        # M0:demo 列表,不打外网
        now_utc = datetime.now(tz=UTC)
        return [
            SymbolMeta(
                symbol=sym,
                market="crypto",
                name=name,
                name_en=name,
                updated_at=now_utc,
            )
            for sym, name in _DEMO_SYMBOLS
        ]

    # ===========================
    # 内部异步实现
    # ===========================

    async def _fetch_async(self, symbol: str, period: Period, limit: int) -> list[Kline]:
        try:
            ohlcv = await self._exchange.fetch_ohlcv(symbol, timeframe=period, limit=limit)
        except RateLimitExceeded as e:
            raise RateLimitError(
                str(e), market="crypto", symbol=symbol, upstream="ccxt-binance",
            ) from e
        except BadSymbol as e:
            raise SymbolNotFoundError(
                str(e), market="crypto", symbol=symbol, upstream="ccxt-binance",
            ) from e
        except NetworkError as e:
            raise UpstreamUnavailableError(
                str(e), market="crypto", symbol=symbol, upstream="ccxt-binance",
            ) from e
        except ExchangeError as e:
            raise UpstreamUnavailableError(
                f"ccxt ExchangeError: {e}",
                market="crypto",
                symbol=symbol,
                upstream="ccxt-binance",
            ) from e

        if not ohlcv:
            raise SymbolNotFoundError(
                f"Binance 未返回 {symbol} 任何数据",
                market="crypto",
                symbol=symbol,
                upstream="ccxt-binance",
            )

        klines: list[Kline] = []
        for row in ohlcv:
            try:
                ts_ms, open_, high, low, close, volume = row
                ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC)
                k = Kline(
                    ts=ts,
                    open=float(open_),
                    high=float(high),
                    low=float(low),
                    close=float(close),
                    volume=float(volume),
                    amount=None,  # ccxt 标准 OHLCV 不含成交额
                )
            except (ValueError, KeyError, TypeError, IndexError) as e:
                raise DataFormatError(
                    f"ccxt 行映射失败:row={row};{e}",
                    market="crypto",
                    symbol=symbol,
                    upstream="ccxt-binance",
                ) from e
            klines.append(k)

        klines.sort(key=lambda k: k.ts)
        return klines
