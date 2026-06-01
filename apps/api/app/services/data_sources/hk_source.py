"""港股数据源适配器(AKShare · `stock_hk_hist`)· ADR 0034a 阶段一 P1-2。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:
   - 港股 = 股票现货【行情展示 · 只读 · 不可交易】(下单是阶段三,本适配器不碰)。
   - 只读 akshare 历史 K 线(非高频轮询)· 复用现有 kline 表 + cache-aside 采集链路。
   - 不接任何真实券商通道 · 凭证免费源无 key。
═══════════════════════════════════════════════════════════════════════════

对齐 cn_source(akshare)模式:`fetch_kline` → `_retry` → `_run_blocking(_fetch_sync)`。
主源 akshare `stock_hk_hist(symbol=<5位>, period=daily/weekly, adjust="qfq")`(前复权 · 零-B 实测
00700 = 5408 行 OK)· yfinance `.HK` 备用源(本期不接,留扩展)。

★ 阶段一只支持【日 / 周线】:零-B 只测 daily;akshare 港股分钟级支持度待定,其它周期直接报
DataFormatError(不静默返空)。分钟级以后补(ADR 0034a 决策③)。

时区:港股日 / 周 K 用收盘 16:00 HKT(Asia/Hong_Kong = UTC+8)→ 转 UTC 存储。
"""

from __future__ import annotations

import logging
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
from app.services.hk_pool import HK_POOL, normalize_hk_code

logger = logging.getLogger(__name__)

HK_TZ = ZoneInfo("Asia/Hong_Kong")

# 我们的 Period → akshare stock_hk_hist 的 period(阶段一只日 / 周)
_AK_HK_PERIOD: dict[Period, str] = {"1d": "daily", "1w": "weekly"}

# akshare stock_hk_hist 返回的中文列(同 stock_zh_a_hist EM 风格)
_REQUIRED_COLS = {"日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额"}


def _hk_daily_ts(date_str: str) -> datetime:
    """港股日 / 周 K 时间戳:日期 + 16:00 HKT 收盘 → UTC。

    date_str 取前 10 字符防御 akshare 偶发带时间(`2024-01-02 00:00:00`)。
    """
    d = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=HK_TZ).date()
    return datetime.combine(d, time(16, 0), tzinfo=HK_TZ).astimezone(UTC)


class AKShareHkSource(BaseDataSource):
    """港股数据源 · akshare `stock_hk_hist`(日 / 周线 + 前复权)。"""

    name = "akshare-hk"
    market = "hk"

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
        """港股标的列表 = 策展池(阶段一不采全市场 · 只读 hk_pool 配置 · 不打上游)。

        全市场港股列表 / 板块榜单是阶段四(ADR 0034a §3),本期用策展 ~18 只。
        """
        now = datetime.now(tz=UTC)
        return [
            SymbolMeta(symbol=sym, market="hk", name=name, updated_at=now)
            for sym, name, _lot, _sector in HK_POOL
        ]

    # ===========================
    # 同步实现
    # ===========================

    def _fetch_sync(self, symbol: str, period: Period, limit: int) -> list[Kline]:
        ak_period = _AK_HK_PERIOD.get(period)
        if ak_period is None:
            raise DataFormatError(
                f"港股阶段一只支持日 / 周线(1d/1w),不支持周期 {period}",
                market="hk", symbol=symbol, upstream="akshare-hk",
            )
        code = normalize_hk_code(symbol)
        try:
            df = ak.stock_hk_hist(symbol=code, period=ak_period, adjust="qfq")
        except (ConnectionError, TimeoutError, OSError) as e:
            raise UpstreamUnavailableError(
                str(e), market="hk", symbol=symbol, upstream="akshare-hk",
            ) from e

        if df is None or df.empty:
            raise SymbolNotFoundError(
                f"akshare 未返回 {symbol}({code})任何 {period} 数据"
                "(代码错误 / 已退市 / 上游临时无数据)",
                market="hk", symbol=symbol, upstream="akshare-hk",
            )

        return self._df_to_klines(df, symbol=symbol, limit=limit)

    @staticmethod
    def _df_to_klines(df: pd.DataFrame, *, symbol: str, limit: int) -> list[Kline]:
        """akshare stock_hk_hist DataFrame → Kline 列表(中文列映射)。

        成交量单位 = 股(港股按股,不像 A 股有"手"概念),原值直存;成交额 = 港币元。
        """
        cols = set(df.columns)
        if not _REQUIRED_COLS.issubset(cols):
            raise DataFormatError(
                f"akshare 港股字段不全 · 实际: {sorted(cols)}",
                market="hk", symbol=symbol, upstream="akshare-hk",
            )

        df_sorted = df.sort_values("日期").tail(limit)
        klines: list[Kline] = []
        for _, row in df_sorted.iterrows():
            try:
                ts = _hk_daily_ts(str(row["日期"]))
                amount_raw = row.get("成交额")
                amount: float | None = (
                    float(amount_raw)
                    if amount_raw is not None and float(amount_raw) > 0
                    else None
                )
                k = Kline(
                    ts=ts,
                    open=float(row["开盘"]),
                    high=float(row["最高"]),
                    low=float(row["最低"]),
                    close=float(row["收盘"]),
                    volume=float(row["成交量"]),
                    amount=amount,
                )
            except (ValueError, KeyError, TypeError) as e:
                raise DataFormatError(
                    f"akshare 港股行映射失败:{row.to_dict()};{e}",
                    market="hk", symbol=symbol, upstream="akshare-hk",
                ) from e
            klines.append(k)
        return klines
