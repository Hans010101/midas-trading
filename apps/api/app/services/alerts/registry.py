"""告警指标注册表 · 0025 G2b(全 DP2)。

每个指标 = 元信息(标签 / 分类 / 适用市场 / 是否需 symbol / 是否需周期)+ 一个
取「最新值」的 async fetcher(只读 ClickHouse 已采数据,不打实时上游)。

scope:
- requires_symbol=True  · per-symbol(价格/技术/缠论/crypto 衍生)或 按板块名 / 指数代码
- requires_symbol=False · 市场级 / 全局(恐贪 / BTC 占比 / 涨跌家数)

ScanContext 缓存同一次扫描里同标的的 K 线 + 全局快照,避免重复读(DP6 性能护栏)。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from app.services import (
    clickhouse_cn_market,
    clickhouse_crypto,
    clickhouse_market_home,
    clickhouse_us_market,
)
from app.services.ai import indicators
from app.services.analysis import chan

if TYPE_CHECKING:
    from app.schemas.market import Kline, Period
    from app.services.clickhouse_client import ClickHouseClient

# 单次扫描每标的拉的 K 线根数:覆盖 MA60(60)+ 缠论(≥30)。
_KLINE_LIMIT = 120


@dataclass
class ScanContext:
    """一次扫描的共享上下文 · 持 CH 句柄 + 缓存。"""

    ch: ClickHouseClient  # 取 K 线(select_kline)
    raw: Any  # clickhouse_connect AsyncClient(取快照 helper)
    _kline_cache: dict[tuple[str, str, str], list[Kline]] = field(
        default_factory=dict,
    )
    _overview: Any = None
    _overview_loaded: bool = False

    async def klines(self, market: str, symbol: str, period: str) -> list[Kline]:
        key = (market, symbol, period)
        if key not in self._kline_cache:
            self._kline_cache[key] = await self.ch.select_kline(
                symbol=symbol, market=cast("Any", market),
                period=cast("Period", period), limit=_KLINE_LIMIT,
            )
        return self._kline_cache[key]

    async def overview(self) -> Any:
        if not self._overview_loaded:
            self._overview = await clickhouse_crypto.select_latest_overview(self.raw)
            self._overview_loaded = True
        return self._overview


# fetcher 签名:(ctx, market, symbol, timeframe) -> 最新值 | None(None = 无数据,跳过)
Fetcher = Callable[
    ["ScanContext", str, "str | None", "str | None"], Awaitable["float | None"],
]


@dataclass(frozen=True)
class IndicatorDef:
    key: str
    label: str
    category: str  # price / volume / technical / chan / crypto_deriv / crypto_global / market_structure
    markets: tuple[str, ...]
    requires_symbol: bool
    needs_timeframe: bool
    fetch: Fetcher
    unit: str | None = None


def _tf(timeframe: str | None) -> str:
    return timeframe or "1d"


# ── K 线类(价格 / 成交量 / 技术 / 缠论)─────────────────────────────


async def _f_price(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
    ks = await ctx.klines(market, cast(str, symbol), _tf(tf))
    return float(ks[-1].close) if ks else None


async def _f_price_change_pct(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
    ks = await ctx.klines(market, cast(str, symbol), _tf(tf))
    if len(ks) < 2:  # noqa: PLR2004
        return None
    prev, cur = float(ks[-2].close), float(ks[-1].close)
    return (cur - prev) / prev * 100 if prev > 0 else None


async def _f_volume(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
    ks = await ctx.klines(market, cast(str, symbol), _tf(tf))
    return float(ks[-1].volume) if ks else None


def _ma_fetcher(window: int) -> Fetcher:
    async def _f(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
        ks = await ctx.klines(market, cast(str, symbol), _tf(tf))
        if len(ks) < window:
            return None
        return indicators.compute_ma(ks).get(window)
    return _f


async def _f_macd_hist(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
    ks = await ctx.klines(market, cast(str, symbol), _tf(tf))
    if len(ks) < 26:  # noqa: PLR2004
        return None
    return indicators.compute_macd(ks).get("macd")


async def _f_rsi_14(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
    ks = await ctx.klines(market, cast(str, symbol), _tf(tf))
    if len(ks) < 15:  # noqa: PLR2004
        return None
    return indicators.compute_rsi(ks).get(14)


async def _f_boll_pctb(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
    ks = await ctx.klines(market, cast(str, symbol), _tf(tf))
    if len(ks) < 20:  # noqa: PLR2004
        return None
    b = indicators.compute_boll(ks)
    upper, lower = b["upper"], b["lower"]
    if upper <= lower:
        return None
    return (float(ks[-1].close) - lower) / (upper - lower) * 100


def _chan_fetcher(side: str) -> Fetcher:
    """缠论买/卖点 · 最新买卖点是买(B*)/卖(S*)→ 1.0 否则 0.0。"""
    async def _f(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
        period = _tf(tf)
        ks = await ctx.klines(market, cast(str, symbol), period)
        if len(ks) < 30:  # noqa: PLR2004
            return None
        result = await chan.analyze(ks, cast("Period", period), cast(str, symbol))
        if not result.buy_sell_points:
            return 0.0
        kind = result.buy_sell_points[-1].kind
        return 1.0 if kind.startswith(side) else 0.0
    return _f


# ── crypto 衍生(perp · 读 ClickHouse 历史快照)──────────────────────


async def _f_funding_rate(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
    rows = await clickhouse_crypto.select_funding_rates(ctx.raw, cast(str, symbol), limit=1)
    return float(rows[-1].rate) if rows else None


async def _f_open_interest_usd(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
    rows = await clickhouse_crypto.select_open_interest(ctx.raw, cast(str, symbol), limit=1)
    return float(rows[-1].oi_usd) if rows else None


async def _f_long_short_ratio(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
    rows = await clickhouse_crypto.select_long_short(ctx.raw, cast(str, symbol), limit=1)
    return float(rows[-1].top_account_ratio) if rows else None


async def _f_basis_pct(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
    pi = await clickhouse_crypto.select_latest_premium_index(ctx.raw, cast(str, symbol))
    if pi is None or float(pi.index_price) <= 0:
        return None
    return (float(pi.mark_price) - float(pi.index_price)) / float(pi.index_price) * 100


# ── crypto 全局(symbol 无关)────────────────────────────────────────


async def _f_fear_greed(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
    ov = await ctx.overview()
    return float(ov.fear_greed_value) if ov and ov.fear_greed_value is not None else None


async def _f_btc_dominance(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
    ov = await ctx.overview()
    return float(ov.btc_dominance) if ov and ov.btc_dominance is not None else None


# ── 市场结构级(涨跌家数 / 板块 / 指数)──────────────────────────────


async def _f_cn_breadth_up_ratio(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
    b = await clickhouse_cn_market.select_latest_breadth(ctx.raw)
    if b is None:
        return None
    total = b.up_count + b.down_count
    return b.up_count / total * 100 if total > 0 else None


async def _f_sector_change_pct(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
    name = cast(str, symbol)
    if market == "cn":
        sectors = await clickhouse_cn_market.select_latest_sectors(ctx.raw, limit=200)
    else:
        sectors = await clickhouse_us_market.select_latest_us_sectors(ctx.raw)
    for s in sectors:
        if s.name == name:
            return float(s.change_pct)
    return None


async def _f_index_change_pct(ctx: ScanContext, market: str, symbol: str | None, tf: str | None) -> float | None:
    rows = await clickhouse_market_home.select_latest_indices(
        ctx.raw, market=cast("Any", market), order=(cast(str, symbol),),
    )
    return float(rows[0].change_pct) if rows else None


# ── 注册表 ───────────────────────────────────────────────────────────

_ALL = ("cn", "us", "crypto")
_CRYPTO = ("crypto",)
_CN_US = ("cn", "us")


def _reg(*defs: IndicatorDef) -> dict[str, IndicatorDef]:
    return {d.key: d for d in defs}


REGISTRY: dict[str, IndicatorDef] = _reg(
    # 价格 / 成交量(per-symbol · K 线)
    IndicatorDef("price", "最新价", "price", _ALL, True, True, _f_price),
    IndicatorDef("price_change_pct", "涨跌幅 %", "price", _ALL, True, True, _f_price_change_pct, unit="%"),
    IndicatorDef("volume", "成交量", "volume", _ALL, True, True, _f_volume),
    # 技术指标(per-symbol · K 线现算)
    IndicatorDef("ma_5", "MA5", "technical", _ALL, True, True, _ma_fetcher(5)),
    IndicatorDef("ma_20", "MA20", "technical", _ALL, True, True, _ma_fetcher(20)),
    IndicatorDef("ma_60", "MA60", "technical", _ALL, True, True, _ma_fetcher(60)),
    IndicatorDef("macd_hist", "MACD 柱", "technical", _ALL, True, True, _f_macd_hist),
    IndicatorDef("rsi_14", "RSI(14)", "technical", _ALL, True, True, _f_rsi_14),
    IndicatorDef("boll_pctb", "布林 %B", "technical", _ALL, True, True, _f_boll_pctb, unit="%"),
    # 缠论(per-symbol · 现算 · 重 → 建议低频)
    IndicatorDef("chan_buy", "缠论买点出现", "chan", _ALL, True, True, _chan_fetcher("B")),
    IndicatorDef("chan_sell", "缠论卖点出现", "chan", _ALL, True, True, _chan_fetcher("S")),
    # crypto 衍生(per-symbol)
    IndicatorDef("funding_rate", "资金费率", "crypto_deriv", _CRYPTO, True, False, _f_funding_rate),
    IndicatorDef("open_interest_usd", "未平仓额(USD)", "crypto_deriv", _CRYPTO, True, False, _f_open_interest_usd, unit="USD"),
    IndicatorDef("long_short_ratio", "多空比(大户账户)", "crypto_deriv", _CRYPTO, True, False, _f_long_short_ratio),
    IndicatorDef("basis_pct", "基差 %", "crypto_deriv", _CRYPTO, True, False, _f_basis_pct, unit="%"),
    # crypto 全局(symbol 无关)
    IndicatorDef("fear_greed", "恐贪指数", "crypto_global", _CRYPTO, False, False, _f_fear_greed),
    IndicatorDef("btc_dominance", "BTC 占比 %", "crypto_global", _CRYPTO, False, False, _f_btc_dominance, unit="%"),
    # 市场结构级
    IndicatorDef("cn_breadth_up_ratio", "A股上涨家数占比 %", "market_structure", ("cn",), False, False, _f_cn_breadth_up_ratio, unit="%"),
    IndicatorDef("sector_change_pct", "板块涨跌 %(symbol=板块名)", "market_structure", _CN_US, True, False, _f_sector_change_pct, unit="%"),
    IndicatorDef("index_change_pct", "指数涨跌 %(symbol=指数代码)", "market_structure", _CN_US, True, False, _f_index_change_pct, unit="%"),
)


def get_indicator(key: str) -> IndicatorDef | None:
    return REGISTRY.get(key)
