"""A 股数据源适配器(AKShare)。

策略:
- 日 K / 周 K 走 **Sina** (`stock_zh_a_daily`)—— 比 EastMoney 更稳定
- 分钟 K(1m/5m/15m/30m/1h)走 **EastMoney** (`stock_zh_a_hist_min_em`),Sina 不提供
- 标的列表 (`stock_info_a_code_name`) 走 EM 但是不同接口,目前稳定

详见 docs/decisions/0002 第 4 条:EM 高频 K 接口当前不稳。

时区:
- 日/周 K:Sina 返回 "YYYY-MM-DD",定为 15:00 CN 收盘 → 07:00 UTC
- 分钟 K:EM 返回 "YYYY-MM-DD HH:MM:SS" naive CN → 转 UTC

成交量单位:**手**(1 手 = 100 股),Sina 返回的是"股",在适配器层除 100 归一。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import akshare as ak
import pandas as pd

from app.schemas.market import Kline, Period, SymbolMeta
from app.services.data_sources.base import BaseDataSource
from app.services.data_sources.exceptions import (
    DataFormatError,
    SymbolNotFoundError,
    UpstreamUnavailableError,
)

logger = logging.getLogger(__name__)

CN_TZ = ZoneInfo("Asia/Shanghai")

# Sina 只用于日 K(stock_zh_a_daily 不接受 period 参数 —— 翻车 7 实测)
_SINA_DAILY: dict[Period, None] = {"1d": None}

# EM 日/周 K 走 stock_zh_a_hist(period 参数支持 daily/weekly/monthly)
# 这里只用 "1w";"1d" 让给 Sina(更稳)
_EM_DAILY_LIKE: dict[Period, str] = {
    "1w": "weekly",
}

# EM 分钟 K 走 stock_zh_a_hist_min_em(注意是 min_em 后缀,跟 daily/weekly 不同函数)
_EM_MINUTE_LIKE: dict[Period, str] = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
}


def _to_sina_symbol(symbol: str) -> str:
    """A 股代码 → Sina 格式(加 sh/sz 前缀)。

    沪市:6/688 开头(主板 / 科创板)→ sh
    深市:0/300 开头(主板 / 创业板)→ sz
    """
    if symbol.startswith(("6", "688")):
        return f"sh{symbol}"
    if symbol.startswith(("0", "3")):
        return f"sz{symbol}"
    msg = f"无法识别的 A 股代码格式:{symbol}"
    raise SymbolNotFoundError(msg, market="cn", symbol=symbol, upstream="akshare-sina")


def _daily_ts(date_str: str) -> datetime:
    """日 K 时间戳:日期 + 15:00 CN 收盘 → UTC。"""
    d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=CN_TZ).date()
    return datetime.combine(d, time(15, 0), tzinfo=CN_TZ).astimezone(UTC)


def _minute_ts(dt_str: str) -> datetime:
    """分钟 K 时间戳:naive CN → UTC。"""
    return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=CN_TZ).astimezone(UTC)


class AKShareCnSource(BaseDataSource):
    """A 股(沪/深)数据源,Sina + EM 混合。"""

    name = "akshare"
    market = "cn"

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
        async def _do() -> list[SymbolMeta]:
            return await asyncio.to_thread(self._list_sync)

        return await self._retry(op="list_symbols", symbol="<all>", coro_factory=_do)

    # ===========================
    # 同步实现
    # ===========================

    def _fetch_sync(self, symbol: str, period: Period, limit: int) -> list[Kline]:
        if period in _SINA_DAILY:
            return self._fetch_sina_daily(symbol, limit)
        if period in _EM_DAILY_LIKE:
            return self._fetch_em_daily_like(symbol, period, limit)
        if period in _EM_MINUTE_LIKE:
            return self._fetch_em_minute(symbol, period, limit)
        msg = f"AKShare 不支持的周期:{period}"
        raise DataFormatError(msg, market="cn", symbol=symbol, upstream="akshare")

    def _fetch_sina_daily(self, symbol: str, limit: int) -> list[Kline]:
        sina_symbol = _to_sina_symbol(symbol)
        try:
            df = ak.stock_zh_a_daily(symbol=sina_symbol, adjust="qfq")
        except (ConnectionError, TimeoutError, OSError) as e:
            raise UpstreamUnavailableError(
                str(e), market="cn", symbol=symbol, upstream="akshare-sina",
            ) from e

        if df is None or df.empty:
            raise SymbolNotFoundError(
                f"Sina 未返回 {symbol} 任何数据(代码错误 / 已退市 / 上游临时无数据)",
                market="cn",
                symbol=symbol,
                upstream="akshare-sina",
            )

        return self._sina_df_to_klines(df, symbol=symbol, limit=limit)

    def _fetch_em_daily_like(self, symbol: str, period: Period, limit: int) -> list[Kline]:
        """EM `stock_zh_a_hist` 走日/周 K。M0 只用周 K(日 K 让给 Sina)。"""
        em_period = _EM_DAILY_LIKE[period]
        try:
            df = ak.stock_zh_a_hist(symbol=symbol, period=em_period, adjust="qfq")
        except (ConnectionError, TimeoutError, OSError) as e:
            raise UpstreamUnavailableError(
                str(e), market="cn", symbol=symbol, upstream="akshare-em",
            ) from e

        if df is None or df.empty:
            raise SymbolNotFoundError(
                f"EM 未返回 {symbol} 任何 {period} 数据",
                market="cn",
                symbol=symbol,
                upstream="akshare-em",
            )

        return self._em_daily_df_to_klines(df, symbol=symbol, limit=limit)

    def _fetch_em_minute(self, symbol: str, period: Period, limit: int) -> list[Kline]:
        em_period = _EM_MINUTE_LIKE[period]
        try:
            df = ak.stock_zh_a_hist_min_em(symbol=symbol, period=em_period, adjust="qfq")
        except (ConnectionError, TimeoutError, OSError) as e:
            raise UpstreamUnavailableError(
                str(e), market="cn", symbol=symbol, upstream="akshare-em",
            ) from e

        if df is None or df.empty:
            raise SymbolNotFoundError(
                f"EM 未返回 {symbol} 任何分钟数据",
                market="cn",
                symbol=symbol,
                upstream="akshare-em",
            )

        return self._em_minute_df_to_klines(df, symbol=symbol, limit=limit)

    def _list_sync(self) -> list[SymbolMeta]:
        try:
            df = ak.stock_info_a_code_name()
        except (ConnectionError, TimeoutError, OSError) as e:
            raise UpstreamUnavailableError(
                str(e), market="cn", upstream="akshare-em",
            ) from e

        if df is None or df.empty:
            raise DataFormatError(
                "stock_info_a_code_name 返回空,上游协议可能变了",
                market="cn",
                upstream="akshare-em",
            )

        now_utc = datetime.now(tz=UTC)
        return [
            SymbolMeta(
                symbol=str(row["code"]),
                market="cn",
                name=str(row["name"]).strip(),
                updated_at=now_utc,
            )
            for _, row in df.iterrows()
        ]

    # ===========================
    # 字段映射:Sina 日/周 K vs EM 分钟 K
    # ===========================

    @staticmethod
    def _sina_df_to_klines(df: pd.DataFrame, *, symbol: str, limit: int) -> list[Kline]:
        """Sina daily/weekly:date / open / high / low / close / volume(股) / amount(元)。"""
        required = {"date", "open", "high", "low", "close", "volume", "amount"}
        cols = set(df.columns)
        if not required.issubset(cols):
            raise DataFormatError(
                f"Sina 字段不全 · 实际: {sorted(cols)}",
                market="cn", symbol=symbol, upstream="akshare-sina",
            )

        df_sorted = df.sort_values("date").tail(limit)
        return _to_klines(
            df_sorted, symbol=symbol, upstream="akshare-sina",
            ts_col="date", ts_builder=_daily_ts,
            volume_scale=0.01,  # 股 → 手
        )

    @staticmethod
    def _em_daily_df_to_klines(df: pd.DataFrame, *, symbol: str, limit: int) -> list[Kline]:
        """EM daily/weekly:日期 / 开盘 / 收盘 / 最高 / 最低 / 成交量(手) / 成交额(元)。

        跟 minute K 字段几乎一样,但 ts 列名是 `日期` 而非 `时间`,且只到日级精度。
        """
        required = {"日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额"}
        cols = set(df.columns)
        if not required.issubset(cols):
            raise DataFormatError(
                f"EM daily/weekly 字段不全 · 实际: {sorted(cols)}",
                market="cn", symbol=symbol, upstream="akshare-em",
            )

        df_sorted = df.sort_values("日期").tail(limit)
        df_renamed = df_sorted.rename(
            columns={
                "日期": "ts_str",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
            },
        )
        return _to_klines(
            df_renamed, symbol=symbol, upstream="akshare-em",
            ts_col="ts_str", ts_builder=_daily_ts,
            volume_scale=1.0,  # EM 已经是 手
        )

    @staticmethod
    def _em_minute_df_to_klines(df: pd.DataFrame, *, symbol: str, limit: int) -> list[Kline]:
        """EM minute:时间 / 开盘 / 收盘 / 最高 / 最低 / 成交量(手) / 成交额(元)。"""
        required = {"时间", "开盘", "收盘", "最高", "最低", "成交量", "成交额"}
        cols = set(df.columns)
        if not required.issubset(cols):
            raise DataFormatError(
                f"EM minute 字段不全 · 实际: {sorted(cols)}",
                market="cn", symbol=symbol, upstream="akshare-em",
            )

        df_sorted = df.sort_values("时间").tail(limit)
        # 重命名到统一字段名,复用 _to_klines
        df_renamed = df_sorted.rename(
            columns={
                "时间": "ts_str",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
            },
        )
        return _to_klines(
            df_renamed, symbol=symbol, upstream="akshare-em",
            ts_col="ts_str", ts_builder=_minute_ts,
            volume_scale=1.0,  # EM 已经是 手
        )


def _to_klines(
    df: pd.DataFrame,
    *,
    symbol: str,
    upstream: str,
    ts_col: str,
    ts_builder: Callable[[str], datetime],
    volume_scale: float,
) -> list[Kline]:
    """通用 DataFrame → Kline 列表。"""
    klines: list[Kline] = []
    for _, row in df.iterrows():
        try:
            ts = ts_builder(str(row[ts_col]))
            amount_raw = row.get("amount")
            amount: float | None = (
                float(amount_raw) if amount_raw is not None and float(amount_raw) > 0 else None
            )
            k = Kline(
                ts=ts,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]) * volume_scale,
                amount=amount,
            )
        except (ValueError, KeyError, TypeError) as e:
            raise DataFormatError(
                f"AKShare 行映射失败:{row.to_dict()};{e}",
                market="cn", symbol=symbol, upstream=upstream,
            ) from e
        klines.append(k)
    return klines
