"""加密数据源适配器(ccxt Binance 现货)。

实现:
- 用 `ccxt.async_support.binance()` 异步 client(原生 async,不用 to_thread)
- fetch_ohlcv 返回 [ts_ms, O, H, L, C, V],V 是 base 货币数量
- ccxt 抛标准异常树,直接映射到我们的业务异常

时区:
- ccxt 返回 Unix milliseconds(UTC epoch),直接转 UTC datetime

成交额 amount:
- ccxt 标准 OHLCV 不含 quote volume → amount 字段固定 None
- 后续 M1 如需 quote volume,改用 binance 私有 endpoint(M0 不做)

symbol 格式:**统一用 ccxt 风格 `BTC/USDT`**(带斜杠),内部传给 binance 时 ccxt 自动转 `BTCUSDT`。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import ccxt.async_support as ccxt_async
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

logger = logging.getLogger(__name__)

# ccxt 的 timeframe 字符串和我们的 Period 一致(都是 1m/5m/.../1d/1w),直接传
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
    """加密数据源(Binance 现货,通过 ccxt 异步)。"""

    name = "ccxt-binance"
    market = "crypto"

    def __init__(self) -> None:
        # ccxt async 客户端,需要在异步上下文里关闭(close()),M0 阶段我们用完即关
        # 每次 fetch 重新建一个最简单,生产可改成 lifespan 管理单例
        self._exchange_kwargs: dict[str, object] = {
            "enableRateLimit": True,
            "timeout": 30_000,  # 30s
        }

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
        exchange = ccxt_async.binance(self._exchange_kwargs)
        try:
            try:
                ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=period, limit=limit)
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
                # 兜底 Exchange 错误:既可能是限流也可能是临时不可用,当作可重试
                raise UpstreamUnavailableError(
                    f"ccxt ExchangeError: {e}",
                    market="crypto",
                    symbol=symbol,
                    upstream="ccxt-binance",
                ) from e
        finally:
            await exchange.close()

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

        # ccxt 已经按 ts 升序,但显式 sort 一次防御
        klines.sort(key=lambda k: k.ts)
        return klines
