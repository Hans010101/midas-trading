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

import logging
import time
from datetime import UTC, datetime

import pandas as pd
import yfinance as yf

from app.schemas.market import Kline, Period, SymbolMeta
from app.schemas.market_home import IndexQuote
from app.schemas.us_market import UsSpotRow
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
            return await self._run_blocking(self._fetch_sync, symbol, period, limit)

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
    # 大盘指数(0023 阶段③ · 3.1)
    # ===========================

    async def fetch_indices(
        self, targets: tuple[tuple[str, str], ...],
    ) -> list[IndexQuote]:
        """大盘指数快照(0023 §2)· yfinance history 取 last + prev close · 算涨跌。

        targets = ((yf_symbol, 展示名), ...)· 单指数失败不致命 · 跳过(其余仍展示)。
        """

        async def _do() -> list[IndexQuote]:
            return await self._run_blocking(self._fetch_indices_sync, targets)

        return await self._retry(op="fetch_indices", symbol="<indices>", coro_factory=_do)

    def _fetch_indices_sync(
        self, targets: tuple[tuple[str, str], ...],
    ) -> list[IndexQuote]:
        now_utc = datetime.now(tz=UTC)
        out: list[IndexQuote] = []
        for symbol, name in targets:
            try:
                df = yf.Ticker(symbol).history(
                    period="5d", interval="1d", auto_adjust=True,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[yfinance] 指数 %s 拉取失败 · 跳过:%s", symbol, e)
                continue
            if df is None or df.empty or "Close" not in df.columns:
                logger.warning("[yfinance] 指数 %s 无数据 · 跳过", symbol)
                continue
            df = df.dropna(subset=["Close"])
            closes = [float(x) for x in df["Close"].tolist()]
            if not closes:
                continue
            last = closes[-1]
            prev = closes[-2] if len(closes) > 1 else last  # noqa: PLR2004
            if last <= 0:
                continue
            out.append(
                IndexQuote(
                    market="us", symbol=symbol, name=name, ts=now_utc,
                    last_point=last, prev_close=prev,
                    change_point=last - prev,
                    change_pct=((last - prev) / prev * 100) if prev > 0 else 0.0,
                ),
            )
        return out

    # ===========================
    # 策展池批量报价(0023 阶段③ · 3.3)· yfinance 批量 · 分块错峰避限流
    # ===========================

    async def fetch_pool_quotes(
        self, pool: tuple[tuple[str, str, str], ...],
    ) -> list[UsSpotRow]:
        """批量拉策展池报价(决策⑥)· pool = ((symbol, name, sector), ...)。

        yf.download 批量 + 分块(每块 40 + sleep 1.5s)· 避免触发 yfinance 限流。
        成交额 = 现价 × 成交量(美元估 · yfinance 无直接美元成交额)。
        盘前盘后异动本期不做(yfinance pre/post 质量参差 + 批量重 · 待数据源升级)。
        """

        async def _do() -> list[UsSpotRow]:
            return await self._run_blocking(self._fetch_pool_sync, pool)

        return await self._retry(op="fetch_pool_quotes", symbol="<pool>", coro_factory=_do)

    def _fetch_pool_sync(
        self, pool: tuple[tuple[str, str, str], ...],
    ) -> list[UsSpotRow]:
        meta = {sym: (name, sector) for sym, name, sector in pool}
        symbols = [sym for sym, _, _ in pool]
        chunk_size = 40
        chunk_pause_s = 1.5
        out: list[UsSpotRow] = []
        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i : i + chunk_size]
            try:
                df = yf.download(
                    chunk, period="2d", interval="1d", auto_adjust=True,
                    group_by="ticker", progress=False, threads=True,
                )
            except Exception as e:  # noqa: BLE001 · 单批失败不致命 · 跳过
                logger.warning("[yfinance] pool 批 %d 拉取失败 · 跳过:%s", i // chunk_size, e)
                continue
            if df is None or df.empty:
                continue
            cols_l0 = (
                set(df.columns.get_level_values(0))
                if isinstance(df.columns, pd.MultiIndex)
                else None
            )
            for sym in chunk:
                try:
                    if cols_l0 is not None:
                        if sym not in cols_l0:
                            continue
                        sub = df[sym]
                    else:
                        sub = df  # 单票降级:整表即该票
                    close_s = sub["Close"].dropna()
                    if close_s.empty:
                        continue
                    last = float(close_s.iloc[-1])
                    prev = float(close_s.iloc[-2]) if len(close_s) > 1 else last  # noqa: PLR2004
                    if last <= 0:
                        continue
                    vol_s = sub["Volume"].dropna()
                    vol = float(vol_s.iloc[-1]) if not vol_s.empty else 0.0
                    name, sector = meta[sym]
                    out.append(
                        UsSpotRow(
                            symbol=sym, name=name, sector=sector, last_price=last,
                            change_pct=((last - prev) / prev * 100) if prev > 0 else 0.0,
                            amount=max(last * vol, 0.0), volume=max(vol, 0.0),
                        ),
                    )
                except (KeyError, ValueError, TypeError, IndexError):
                    continue
            if i + chunk_size < len(symbols):
                time.sleep(chunk_pause_s)
        if not out:
            raise UpstreamUnavailableError(
                "yfinance 策展池全部批次无数据", market="us", upstream="yfinance",
            )
        return out

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
