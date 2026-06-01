"""港股数据源适配器(AKShare · `stock_hk_hist`)· ADR 0034a 阶段一 P1-2。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:
   - 港股 = 股票现货【行情展示 · 只读 · 不可交易】(下单是阶段三,本适配器不碰)。
   - 只读 akshare 历史 K 线(非高频轮询)· 复用现有 kline 表 + cache-aside 采集链路。
   - 不接任何真实券商通道 · 凭证免费源无 key。
═══════════════════════════════════════════════════════════════════════════

对齐 cn_source(akshare)模式:`fetch_kline` → `_retry` → `_run_blocking(_fetch_sync)`。
★ 主源 + 备用源【自动降级】(2026-06-01 实证:生产香港 VPS 的出口 IP 被 akshare 港股上游
(东财)持续 RemoteDisconnected,而 yfinance/Yahoo 对生产可达 —— 全球概览 52 指标在生产稳跑):
- 主源 akshare `stock_hk_hist(symbol=<5位>, period=daily/weekly, adjust="qfq")`(前复权 · 数据更全)
- 主源失败 / 返空 → 自动降级 yfinance(Yahoo · `0700.HK` 风格 · 复用 us_source 同款 history 调用)
- 两源都失败才 503。yfinance 的 ts 统一对齐 akshare(16:00 HKT 收盘)→ CH 按 ts 去重不会两源各存一行。

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
import yfinance as yf

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
            # 两源阶段一都只日 / 周线 · 不降级(降级也不支持)
            raise DataFormatError(
                f"港股阶段一只支持日 / 周线(1d/1w),不支持周期 {period}",
                market="hk", symbol=symbol, upstream="hk",
            )
        # 主源 akshare(数据更全)· 失败 / 返空 → 自动降级备用源 yfinance
        try:
            klines = self._fetch_akshare(symbol, ak_period, limit)
            if klines:
                return klines
            logger.warning("[hk] akshare 返空 · 降级 yfinance · symbol=%s", symbol)
        except Exception as e:  # noqa: BLE001 · akshare 任何失败(连接/上游/协议)→ 降级
            logger.warning("[hk] akshare 失败 · 降级 yfinance · symbol=%s · %s", symbol, e)
        # 备用源 yfinance(Yahoo · 生产可达 · 同 us_source / 全球概览用法)
        return self._fetch_yfinance(symbol, period, limit)

    def _fetch_akshare(self, symbol: str, ak_period: str, limit: int) -> list[Kline]:
        """主源 akshare · 返空则 []( 触发降级)· 连接 / 协议异常 raise(由 _fetch_sync 接住降级)。"""
        code = normalize_hk_code(symbol)
        df = ak.stock_hk_hist(symbol=code, period=ak_period, adjust="qfq")
        if df is None or df.empty:
            return []
        return self._df_to_klines(df, symbol=symbol, limit=limit)

    @staticmethod
    def _to_yf_code(symbol: str) -> str:
        """akshare 5 位港股代码 → yfinance ticker:去前导 0 补 4 位 + '.HK'。

        00700 → 0700.HK · 09988 → 9988.HK · 00005 → 0005.HK(对齐 Yahoo Finance 港股 ticker)。
        """
        return normalize_hk_code(symbol).lstrip("0").zfill(4) + ".HK"

    def _fetch_yfinance(self, symbol: str, period: Period, limit: int) -> list[Kline]:
        """备用源 yfinance(Yahoo)· 复用 us_source 同款 `yf.Ticker().history()`。

        ts 统一走 _hk_daily_ts(16:00 HKT 收盘)· 与主源 akshare 一致 → 同交易日同 ts,
        CH 按 ts 去重不会因两源(yfinance daily index 是 HKT 午夜)各存一行。
        """
        yf_code = self._to_yf_code(symbol)
        interval = "1wk" if period == "1w" else "1d"
        try:
            df = yf.Ticker(yf_code).history(period="max", interval=interval, auto_adjust=True)
        except (ConnectionError, TimeoutError, OSError) as e:
            raise UpstreamUnavailableError(
                str(e), market="hk", symbol=symbol, upstream="yfinance-hk",
            ) from e
        except Exception as e:  # noqa: BLE001 · yfinance 内部异常通常临时(限流/解析)
            raise UpstreamUnavailableError(
                f"yfinance 未知异常:{e}", market="hk", symbol=symbol, upstream="yfinance-hk",
            ) from e

        if df is None or df.empty:
            raise SymbolNotFoundError(
                f"akshare + yfinance 都未返回 {symbol}({yf_code})数据"
                "(代码错误 / 已退市 / 两源皆不可达)",
                market="hk", symbol=symbol, upstream="yfinance-hk",
            )
        required = {"Open", "High", "Low", "Close", "Volume"}
        if not required.issubset(set(df.columns)):
            raise DataFormatError(
                f"yfinance 港股字段不全 · 实际: {sorted(df.columns)}",
                market="hk", symbol=symbol, upstream="yfinance-hk",
            )

        df_sorted = df.sort_index().tail(limit)
        klines: list[Kline] = []
        for idx, row in df_sorted.iterrows():
            try:
                # yfinance index 是 tz-aware(HKT)· 只取日期 → 统一 16:00 HKT 收盘(对齐 akshare)
                ts = _hk_daily_ts(idx.strftime("%Y-%m-%d"))
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
                    f"yfinance 港股行映射失败:idx={idx};{e}",
                    market="hk", symbol=symbol, upstream="yfinance-hk",
                ) from e
            klines.append(k)
        return klines

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
