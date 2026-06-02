"""港股数据源适配器(AKShare · 日线主源新浪 `stock_hk_daily`)· ADR 0034a 阶段一 P1-2。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:
   - 港股 = 股票现货【行情展示 · 只读 · 不可交易】(下单是阶段三,本适配器不碰)。
   - 只读 akshare 历史 K 线(非高频轮询)· 复用现有 kline 表 + cache-aside 采集链路。
   - 不接任何真实券商通道 · 凭证免费源无 key。
═══════════════════════════════════════════════════════════════════════════

对齐 cn_source(akshare)模式:`fetch_kline` → `_retry` → `_run_blocking(_fetch_sync)`。
★ 主源 + 备用源【自动降级】(0033 诊断 hk-kline-source-diagnosis.md:东财 `stock_hk_hist`
生产 100% 死(RemoteDisconnected)→ 换新浪 `stock_hk_daily` 主源 —— 新浪生产可达 + 覆盖冷门,
生产实测 5/5 sina_ok · 同新浪 spot 在生产稳跑):
- 日线主源 新浪 `stock_hk_daily(symbol=<5位>, adjust="qfq")`(前复权 · 覆盖冷门 · 生产可达)
- 主源失败 / 返空 → 自动降级 yfinance(Yahoo · `0700.HK` 风格 · 复用 us_source 同款 history 调用)
- 周线:新浪 `stock_hk_daily` 仅日线 → 直接走 yfinance(interval=1wk)。
- 两源都失败:真没数据 → SymbolNotFoundError(404,前端"标的不存在")· 连接抖动 → 503(前端"稍后重试")。
- ts 统一对齐 16:00 HKT 收盘 → 新浪 / yfinance 同 ts,CH 按 ts 去重不会两源各存一行。

★ 阶段一只支持【日 / 周线】:其它周期直接报 DataFormatError(不静默返空)。分钟级以后补。

时区:港股日 / 周 K 用收盘 16:00 HKT(Asia/Hong_Kong = UTC+8)→ 转 UTC 存储。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import akshare as ak
import pandas as pd
import requests
import yfinance as yf

from app.schemas.hk_market import HkSpotRow
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

# 全市场 spot 分页 · ★限页前 15 页 ≈ 900 只主要成分(防新浪封 IP · 不拉全 46 页)·
#   自己分页(不用 ak.stock_hk_spot 全 46 页)· 单次 15 页 ~15-20s → timeout 60s。
_SINA_HK_SPOT_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHKStockData"
)
_HK_SPOT_MAX_PAGES = 15        # 前 15 页(每页 60)≈ 900 只 · 限页防封 IP(本地已实证限速)
_SINA_PAGE_TIMEOUT = 8.0       # 单页 requests 超时(秒)
_HK_SPOT_TIMEOUT = 60.0        # _run_blocking 总超时(15 页 ~15-20s · 给足缓冲)
# 新浪 getHKStockData 单页 24 列位置映射(对齐 akshare stock_hk_spot · 防字段错位)
_SINA_HK_SPOT_COLUMNS = (
    "代码", "中文名称", "英文名称", "交易类型", "最新价", "昨收", "今开", "最高", "最低",
    "成交量", "-", "成交额", "日期时间", "买一", "卖一", "-", "-", "-", "-", "-",
    "涨跌额", "涨跌幅", "-", "-",
)

# 阶段一只支持日 / 周线(新浪 stock_hk_daily 仅日线;周线走 yfinance interval=1wk)
_HK_SUPPORTED_PERIODS: frozenset[Period] = frozenset({"1d", "1w"})


def _hk_daily_ts(date_str: str) -> datetime:
    """港股日 / 周 K 时间戳:日期 + 16:00 HKT 收盘 → UTC。

    date_str 取前 10 字符防御 akshare 偶发带时间(`2024-01-02 00:00:00`)。
    """
    d = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=HK_TZ).date()
    return datetime.combine(d, time(16, 0), tzinfo=HK_TZ).astimezone(UTC)


class AKShareHkSource(BaseDataSource):
    """港股数据源 · 日线主源新浪 `stock_hk_daily` + yfinance 备用(前复权 · 东财已弃·生产死)。"""

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
    # 全市场 spot 榜单(港股首页全市场 · 新浪 stock_hk_spot ~2764 只)
    # ===========================

    async def fetch_spot_snapshot(self) -> list[HkSpotRow]:
        """港股主要成分实时快照 · 新浪源 · ★限页前 15 页 ≈ 900 只(产品负责人拍板防封 IP)。

        ★ 源用新浪(getHKStockData · 生产已实测可达)· 绝不用东财 `stock_hk_spot_em`
          (生产被拒 · 本地都 RemoteDisconnected · 同 stock_hk_hist 东财翻车)。
        ★ 限页前 15 页(非全 46 页 2764 只):全拉 46 请求/次封 IP 风险高(本地连测已触发限速)·
          限页 ≈ 900 只主要成分,涨跌家数/榜单够有意义。
        """

        # ★ 自己分页前 15 页 · ~15-20s → timeout 60s · 不走 _retry(失败下次 beat 再跑)。
        return await self._run_blocking(self._fetch_spot_sync, timeout=_HK_SPOT_TIMEOUT)

    def _fetch_spot_sync(self) -> list[HkSpotRow]:
        # ★ 自己分页前 15 页(限页防封 IP)· 不用 ak.stock_hk_spot(它内部固定全拉 46 页)。
        big = pd.DataFrame()
        for page in range(1, _HK_SPOT_MAX_PAGES + 1):
            try:
                resp = requests.get(
                    _SINA_HK_SPOT_URL,
                    params={
                        "page": str(page), "num": "60", "sort": "symbol",
                        "asc": "1", "node": "qbgg_hk", "_s_r_a": "init",
                    },
                    timeout=_SINA_PAGE_TIMEOUT,
                )
                data = resp.json()
            except (ConnectionError, TimeoutError, OSError, ValueError) as e:
                raise UpstreamUnavailableError(
                    f"新浪港股 spot 第 {page} 页失败:{e}",
                    market="hk", upstream="akshare-sina-hk",
                ) from e
            if not data:
                break  # 空页 = 到底(港股不足 900 只时不足 15 页也正常)
            big = pd.concat([big, pd.DataFrame(data)], ignore_index=True)
        if big.empty:
            raise UpstreamUnavailableError(
                "新浪港股 spot 返回空(前 15 页皆空)", market="hk", upstream="akshare-sina-hk",
            )
        if len(big.columns) != len(_SINA_HK_SPOT_COLUMNS):
            raise DataFormatError(
                f"新浪港股 spot 列数变(实际 {len(big.columns)} · 期望 24)",
                market="hk", upstream="akshare-sina-hk",
            )
        big.columns = list(_SINA_HK_SPOT_COLUMNS)
        for col in ("最新价", "涨跌额", "涨跌幅", "成交量", "成交额"):
            big[col] = pd.to_numeric(big[col], errors="coerce")
        out: list[HkSpotRow] = []
        for _, row in big.iterrows():
            last = row["最新价"]
            chg_pct = row["涨跌幅"]
            if pd.isna(last) or pd.isna(chg_pct):
                continue  # 停牌 / 脏行 · 跳过
            try:
                code = normalize_hk_code(str(row["代码"]).strip())  # 规范 5 位
                out.append(
                    HkSpotRow(
                        symbol=code, name=str(row["中文名称"]).strip(),
                        last_price=max(float(last), 0.0),
                        change_pct=float(chg_pct),
                        change_amount=0.0 if pd.isna(row["涨跌额"]) else float(row["涨跌额"]),
                        amount=max(0.0 if pd.isna(row["成交额"]) else float(row["成交额"]), 0.0),
                        volume=max(0.0 if pd.isna(row["成交量"]) else float(row["成交量"]), 0.0),
                    ),
                )
            except (ValueError, TypeError):
                continue  # 个别脏行跳过,不致命
        if not out:
            raise DataFormatError(
                "新浪港股 spot 全部行解析失败", market="hk", upstream="akshare-sina-hk",
            )
        return out

    # ===========================
    # 同步实现
    # ===========================

    def _fetch_sync(self, symbol: str, period: Period, limit: int) -> list[Kline]:
        if period not in _HK_SUPPORTED_PERIODS:
            raise DataFormatError(
                f"港股阶段一只支持日 / 周线(1d/1w),不支持周期 {period}",
                market="hk", symbol=symbol, upstream="hk",
            )
        # ★ 方案A(0033 诊断):主源换新浪 stock_hk_daily —— 东财 stock_hk_hist 生产 100% 死
        #   (RemoteDisconnected),新浪生产可达 + 覆盖冷门(实测 5/5 sina_ok)。
        # 日线:新浪主源 → 失败 / 返空 → 降级 yfinance。
        # 周线:新浪 stock_hk_daily 不支持周线 → 直接 yfinance(interval=1wk)。
        if period == "1d":
            try:
                klines = self._fetch_sina_daily(symbol, limit)
                if klines:
                    return klines
                logger.warning("[hk] 新浪 stock_hk_daily 返空 · 降级 yfinance · symbol=%s", symbol)
            except Exception as e:  # noqa: BLE001 · 新浪任何失败(连接/协议)→ 降级 yfinance
                logger.warning("[hk] 新浪 stock_hk_daily 失败 · 降级 yfinance · %s · %s", symbol, e)
        # 备用源 yfinance(Yahoo · 生产可达 · 同 us_source / 全球概览用法)
        return self._fetch_yfinance(symbol, period, limit)

    def _fetch_sina_daily(self, symbol: str, limit: int) -> list[Kline]:
        """主源 新浪 `stock_hk_daily`(日线 · 前复权 qfq)· 返空则 []( 触发降级)·
        连接 / 协议异常 raise(由 _fetch_sync 接住降级 yfinance)。

        新浪列:date/open/high/low/close/volume/amount(小写)· 覆盖冷门 · 生产可达
        (替代生产 100% 死的东财 stock_hk_hist)· ts 对齐 16:00 HKT 收盘 → 与 yfinance 同 ts,
        CH 按 ts 去重不会两源各存一行。
        """
        code = normalize_hk_code(symbol)
        df = ak.stock_hk_daily(symbol=code, adjust="qfq")
        if df is None or df.empty:
            return []
        df_sorted = df.sort_values("date").tail(limit)
        klines: list[Kline] = []
        for _, row in df_sorted.iterrows():
            try:
                ts = _hk_daily_ts(str(row["date"]))
                amount_raw = row.get("amount")
                amount: float | None = (
                    float(amount_raw)
                    if amount_raw is not None and float(amount_raw) > 0
                    else None
                )
                k = Kline(
                    ts=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    amount=amount,
                )
            except (ValueError, KeyError, TypeError) as e:
                raise DataFormatError(
                    f"新浪港股日线行映射失败:{row.to_dict()};{e}",
                    market="hk", symbol=symbol, upstream="akshare-sina-hk-daily",
                ) from e
            klines.append(k)
        return klines

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
