"""美股数据源适配器(yfinance)。

实现:
- 日 K / 周 K / 分钟 K 全部通过 `yfinance.Ticker.history()`
- yfinance 返回 tz-aware index(America/New_York),适配器统一转 UTC
- yfinance **不提供成交额 amount** → 字段固定 None
- yfinance 没有"列全市场标的"的 API,M0 阶段写死一份 demo 列表(NVDA / AAPL / SPY / QQQ
  等 10 个高流动性标的),后续 Task 2 完整版接 sp500 list

时区:
- yfinance daily K 用 ET 午夜:`2026-05-05 00:00:00-04:00`(ET)→ `2026-05-05 04:00 UTC`
- yfinance hourly K 用 ET 交易时刻:`13:30-04:00`(美东 09:30 早盘开盘 + DST 偏移)→ UTC

国内 IP 直连境外服务可能 451:支持 `HTTPS_PROXY` 环境变量(yfinance / requests 都尊重)。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

import yfinance as yf

from app.schemas.market import Kline, Period, SymbolMeta
from app.services.data_sources.base import BaseDataSource
from app.services.data_sources.exceptions import (
    DataFormatError,
    SymbolNotFoundError,
    UpstreamUnavailableError,
)

logger = logging.getLogger(__name__)

# yfinance interval 映射(注意 1w → "1wk")
_PERIOD_INTERVAL: dict[Period, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "1d": "1d",
    "1w": "1wk",
}

# yfinance period 限制:1m/5m/15m/30m 只支持 7 天,1h 只支持 60 天,日 K 不限
_PERIOD_LOOKBACK: dict[Period, str] = {
    "1m": "7d",
    "5m": "7d",
    "15m": "7d",
    "30m": "7d",
    "1h": "60d",
    "1d": "max",
    "1w": "max",
}

# M0 demo 标的(yfinance 没有"列全市场"API,这里写死一份)
_DEMO_SYMBOLS: list[tuple[str, str]] = [
    ("NVDA", "NVIDIA Corporation"),
    ("AAPL", "Apple Inc."),
    ("MSFT", "Microsoft Corporation"),
    ("GOOGL", "Alphabet Inc. Class A"),
    ("AMZN", "Amazon.com Inc."),
    ("META", "Meta Platforms Inc."),
    ("TSLA", "Tesla Inc."),
    ("SPY", "SPDR S&P 500 ETF Trust"),
    ("QQQ", "Invesco QQQ Trust"),
    ("VOO", "Vanguard S&P 500 ETF"),
]


class YFinanceUsSource(BaseDataSource):
    """美股数据源(yfinance)。"""

    name = "yfinance"
    market = "us"

    async def fetch_kline(
        self,
        symbol: str,
        period: Period,
        *,
        limit: int = 500,
    ) -> list[Kline]:
        async def _do() -> list[Kline]:
            return await asyncio.to_thread(self._fetch_sync, symbol, period, limit)

        return await self._retry(op="fetch_kline", symbol=symbol, coro_factory=_do)

    async def list_symbols(self) -> list[SymbolMeta]:
        # M0:写死的 demo 列表,不打外网
        now_utc = datetime.now(tz=UTC)
        return [
            SymbolMeta(
                symbol=sym,
                market="us",
                name=name,  # yfinance 一般是英文,沿用作 name(也可用作 name_en)
                name_en=name,
                updated_at=now_utc,
            )
            for sym, name in _DEMO_SYMBOLS
        ]

    # ===========================
    # 同步实现
    # ===========================

    def _fetch_sync(self, symbol: str, period: Period, limit: int) -> list[Kline]:
        interval = _PERIOD_INTERVAL[period]
        lookback = _PERIOD_LOOKBACK[period]
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=lookback, interval=interval, auto_adjust=True)
        except (ConnectionError, TimeoutError, OSError) as e:
            # 451 / 网络错误 / 代理失败
            raise UpstreamUnavailableError(
                str(e), market="us", symbol=symbol, upstream="yfinance",
            ) from e
        except Exception as e:  # noqa: BLE001
            # yfinance 内部异常通常是临时性的(rate limit / parsing)
            raise UpstreamUnavailableError(
                f"yfinance 未知异常:{e}",
                market="us",
                symbol=symbol,
                upstream="yfinance",
            ) from e

        if df is None or df.empty:
            # yfinance 对不存在标的会打 "$XYZ: possibly delisted" 到 stderr,
            # 返回空 DataFrame(empty=True)
            raise SymbolNotFoundError(
                f"yfinance 未返回 {symbol} 任何数据(代码错误 / 已退市 / IP 451)",
                market="us",
                symbol=symbol,
                upstream="yfinance",
            )

        required = {"Open", "High", "Low", "Close", "Volume"}
        cols = set(df.columns)
        if not required.issubset(cols):
            raise DataFormatError(
                f"yfinance 字段不全 · 实际: {sorted(cols)}",
                market="us",
                symbol=symbol,
                upstream="yfinance",
            )

        # yfinance index 是 tz-aware DatetimeIndex(America/New_York)
        df_sorted = df.sort_index().tail(limit)

        klines: list[Kline] = []
        for idx, row in df_sorted.iterrows():
            try:
                # idx 是 pandas Timestamp,tz-aware
                ts = idx.tz_convert("UTC").to_pydatetime()
                k = Kline(
                    ts=ts,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                    amount=None,  # yfinance 不提供成交额
                )
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                raise DataFormatError(
                    f"yfinance 行映射失败:idx={idx} row={row.to_dict()};{e}",
                    market="us",
                    symbol=symbol,
                    upstream="yfinance",
                ) from e
            klines.append(k)
        return klines
