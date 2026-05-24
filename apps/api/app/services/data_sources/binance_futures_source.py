"""Binance USDT-M Futures 数据源(0017 ADR · M2-A)。

跟现有 ccxt-based crypto_source.py(现货)互补:
- crypto_source.py 用 ccxt · 走标准 OHLCV · 拉现货 K
- 本模块用 httpx · 直接打 Binance fapi · 拉 perp 特有维度
  (funding rate / open interest / long-short ratio / 24h ticker)

为什么不全走 ccxt?
- ccxt 对 Binance Futures 部分 endpoint 包装层不完整(funding 历史 / OI 历史
  /多空比 都需要 ccxt.binance.fapi_data_get_* 这种低级 API)
- 直接 httpx 更简单 · 协议透明 · 出问题好诊断

symbol 格式约定:
- 本 adapter 内部和返回值统一用 Binance Futures 风格 `BTCUSDT`(无斜杠)
- 因为 Binance Futures API 用这个格式 · 转换到 ccxt 风格 `BTC/USDT`
  在调用方做(写 ClickHouse 时)· 这样 adapter 不带格式偏见

红线:本 adapter 只用 GET endpoints · 没 sign · 没 trade · 没 key。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import httpx

from app.schemas.crypto import (
    FundingRate,
    LongShortRatio,
    OpenInterest,
    PremiumIndex,
    Ticker24h,
)
from app.schemas.market import Kline, Period
from app.services.data_sources.base import BaseDataSource
from app.services.data_sources.exceptions import (
    DataFormatError,
    RateLimitError,
    SymbolNotFoundError,
    UpstreamUnavailableError,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Binance Futures fapi 期间映射(跟 spot 一致)
_FAPI_INTERVAL: dict[Period, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "1d": "1d",
    "1w": "1w",
}

# long/short ratio 只支持这几个 period · 本 adapter 固定取 5m
_LONG_SHORT_PERIOD = "5m"

# OI 历史也固定 5m
_OI_PERIOD = "5m"


class BinanceFuturesSource(BaseDataSource):
    """Binance USDT-M Futures 数据源(httpx async)。

    所有方法都包 _retry · 上游 5xx / 429 / 网络抖动自动退避重试 3 次。
    """

    name = "binance-futures"
    market = "crypto"

    def __init__(
        self,
        *,
        base_url: str = "https://fapi.binance.com",
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # 调用方注入 client · 复用连接池;否则自己建一个
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ========================================================================
    # 通用 HTTP helper
    # ========================================================================

    async def _get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        symbol_for_error: str | None = None,
    ) -> Any:
        """HTTP GET + 错误映射 · 不在这里 retry(外层用 _retry 包)。"""
        url = f"{self._base_url}{path}"
        try:
            resp = await self._client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(
                f"Binance Futures 网络错: {type(exc).__name__}: {exc}",
                market="crypto",
                symbol=symbol_for_error,
                upstream="binance-futures",
            ) from exc

        # 429 / 418(Binance 封禁)→ rate limit
        if resp.status_code in (418, 429):
            raise RateLimitError(
                f"Binance Futures 限流 · HTTP {resp.status_code}",
                market="crypto",
                symbol=symbol_for_error,
                upstream="binance-futures",
            )
        # 5xx → 上游不可达 · 可重试
        if 500 <= resp.status_code < 600:
            raise UpstreamUnavailableError(
                f"Binance Futures 5xx · HTTP {resp.status_code}",
                market="crypto",
                symbol=symbol_for_error,
                upstream="binance-futures",
            )
        # 400/404 · 多半 symbol 错 · 终态
        if resp.status_code in (400, 404):
            raise SymbolNotFoundError(
                f"Binance Futures symbol 不存在 · HTTP {resp.status_code} body={resp.text[:200]}",
                market="crypto",
                symbol=symbol_for_error,
                upstream="binance-futures",
            )
        # 其它非 2xx · 终态(避免无脑重试)
        if not resp.is_success:
            raise DataFormatError(
                f"Binance Futures 非预期响应 · HTTP {resp.status_code} body={resp.text[:200]}",
                market="crypto",
                symbol=symbol_for_error,
                upstream="binance-futures",
            )

        try:
            return resp.json()
        except ValueError as exc:
            raise DataFormatError(
                f"Binance Futures 响应非 JSON: {resp.text[:200]}",
                market="crypto",
                symbol=symbol_for_error,
                upstream="binance-futures",
            ) from exc

    # ========================================================================
    # 1 · Perp K 线(继承 BaseDataSource.fetch_kline 接口)
    # ========================================================================

    async def fetch_kline(
        self,
        symbol: str,
        period: Period,
        limit: int = 500,
    ) -> list[Kline]:
        """拉 perp K 线 · /fapi/v1/klines。

        symbol 格式 `BTCUSDT`(Binance 风格)。
        返回 ts 升序的 Kline 列表(继承基类约定)。
        """
        if period not in _FAPI_INTERVAL:
            raise SymbolNotFoundError(
                f"不支持的 period: {period}",
                market="crypto",
                symbol=symbol,
                upstream="binance-futures",
            )

        async def _do() -> list[Kline]:
            data = await self._get_json(
                "/fapi/v1/klines",
                params={"symbol": symbol, "interval": _FAPI_INTERVAL[period], "limit": limit},
                symbol_for_error=symbol,
            )
            if not isinstance(data, list):
                raise DataFormatError(
                    f"klines 响应非数组: {type(data).__name__}",
                    market="crypto", symbol=symbol, upstream="binance-futures",
                )
            return [_parse_kline_row(r, symbol=symbol) for r in data]

        return await self._retry(op="fetch_kline", symbol=symbol, coro_factory=_do)

    # ========================================================================
    # 2 · 资金费率历史
    # ========================================================================

    async def fetch_funding_rate(
        self,
        symbol: str,
        *,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
        limit: int = 100,
    ) -> list[FundingRate]:
        """资金费率历史 · /fapi/v1/fundingRate。

        默认取最近 `limit` 条(Binance 默认 100 · max 1000)。
        指定 start_ts/end_ts 时按时间范围拉取。
        """
        params: dict[str, Any] = {"symbol": symbol, "limit": min(limit, 1000)}
        if start_ts:
            params["startTime"] = int(start_ts.timestamp() * 1000)
        if end_ts:
            params["endTime"] = int(end_ts.timestamp() * 1000)

        async def _do() -> list[FundingRate]:
            data = await self._get_json(
                "/fapi/v1/fundingRate", params=params, symbol_for_error=symbol,
            )
            if not isinstance(data, list):
                raise DataFormatError(
                    f"fundingRate 响应非数组: {type(data).__name__}",
                    market="crypto", symbol=symbol, upstream="binance-futures",
                )
            return [_parse_funding_row(r, symbol=symbol) for r in data]

        return await self._retry(op="fetch_funding_rate", symbol=symbol, coro_factory=_do)

    # ========================================================================
    # 3 · Open Interest 历史
    # ========================================================================

    async def fetch_open_interest(
        self,
        symbol: str,
        *,
        limit: int = 100,
    ) -> list[OpenInterest]:
        """OI 历史 · /futures/data/openInterestHist · 5min 栅格。"""
        async def _do() -> list[OpenInterest]:
            data = await self._get_json(
                "/futures/data/openInterestHist",
                params={"symbol": symbol, "period": _OI_PERIOD, "limit": min(limit, 500)},
                symbol_for_error=symbol,
            )
            if not isinstance(data, list):
                raise DataFormatError(
                    "openInterestHist 响应非数组",
                    market="crypto", symbol=symbol, upstream="binance-futures",
                )
            return [_parse_oi_row(r, symbol=symbol) for r in data]

        return await self._retry(op="fetch_open_interest", symbol=symbol, coro_factory=_do)

    # ========================================================================
    # 4 · 多空比(top trader + taker · 三套指标合并)
    # ========================================================================

    async def fetch_long_short_ratio(
        self,
        symbol: str,
        *,
        limit: int = 100,
    ) -> list[LongShortRatio]:
        """三套多空比指标合并 · 按 ts 对齐。

        并发拉:
        - /futures/data/topLongShortAccountRatio
        - /futures/data/topLongShortPositionRatio
        - /futures/data/takerlongshortRatio

        三个 endpoint 都按 5min 栅格 · ts 对齐(理论上)。
        实际可能错位 · 此版本按 timestamp 严格匹配 · 任一缺失则跳过。
        """
        # M2-A 简化:串行拉 · M2-B 可改并发(asyncio.gather)
        # 这里写串行先保正确性
        async def _do() -> list[LongShortRatio]:
            account = await self._get_json(
                "/futures/data/topLongShortAccountRatio",
                params={"symbol": symbol, "period": _LONG_SHORT_PERIOD, "limit": min(limit, 500)},
                symbol_for_error=symbol,
            )
            position = await self._get_json(
                "/futures/data/topLongShortPositionRatio",
                params={"symbol": symbol, "period": _LONG_SHORT_PERIOD, "limit": min(limit, 500)},
                symbol_for_error=symbol,
            )
            taker = await self._get_json(
                "/futures/data/takerlongshortRatio",
                params={"symbol": symbol, "period": _LONG_SHORT_PERIOD, "limit": min(limit, 500)},
                symbol_for_error=symbol,
            )
            return _merge_long_short(account=account, position=position, taker=taker, symbol=symbol)

        return await self._retry(op="fetch_long_short_ratio", symbol=symbol, coro_factory=_do)

    # ========================================================================
    # 5 · 24h ticker(全币种 or 指定子集)
    # ========================================================================

    async def fetch_ticker_24h(
        self,
        *,
        symbols: list[str] | None = None,
    ) -> list[Ticker24h]:
        """24h ticker · /fapi/v1/ticker/24hr。

        不传 symbols → 拉全市场(Binance 一次返 ~300 个 perp 标的)
        传 symbols → Binance API 不支持批量 filter · 我们拉全量再 filter
        """
        async def _do() -> list[Ticker24h]:
            data = await self._get_json("/fapi/v1/ticker/24hr")
            if not isinstance(data, list):
                # 单 symbol 时 Binance 返单对象 · 包装成数组
                data = [data]
            results = [_parse_ticker_row(r, instrument="perp") for r in data]
            if symbols:
                wanted = set(symbols)
                results = [t for t in results if _to_binance_symbol(t.symbol) in wanted]
            return results

        return await self._retry(op="fetch_ticker_24h", symbol="*", coro_factory=_do)

    # ========================================================================
    # 5.5 · Premium Index 全市场快照(标记价/指数价/资金费)· M2-C.2.1
    # ========================================================================

    async def fetch_premium_index(self) -> list[PremiumIndex]:
        """全市场标记价/指数价/资金费快照 · /fapi/v1/premiumIndex(无 symbol = 全量)。

        单请求返回全市场 ~500 个 perp 的
        {symbol, markPrice, indexPrice, lastFundingRate, nextFundingTime, time}。
        权重极低(类 ticker/24hr 全市场)· 适合每分钟刷,给撮合/强平价源用。

        过滤(在 _parse_premium_index_row 内):
        - 非法价/时间(<=0)→ 跳过(下架/异常 symbol)
        - 含 '_' 的交割合约(BTCUSDT_240628 等)→ 跳过(只要永续)
        """
        async def _do() -> list[PremiumIndex]:
            data = await self._get_json("/fapi/v1/premiumIndex")
            if not isinstance(data, list):
                # 理论上无 symbol 时返数组;容错单对象
                data = [data]
            out: list[PremiumIndex] = []
            for r in data:
                parsed = _parse_premium_index_row(r)
                if parsed is not None:
                    out.append(parsed)
            return out

        return await self._retry(op="fetch_premium_index", symbol="*", coro_factory=_do)

    # ========================================================================
    # 6 · 合约元信息(给 /api/v1/crypto/futures/{symbol}/info 用)
    # ========================================================================

    async def fetch_symbol_info(self, symbol: str) -> dict[str, Any]:
        """合约元信息 · 组合 /fapi/v1/premiumIndex + /fapi/v1/exchangeInfo。

        M2-A 只 stub 返回 raw dict · M2-B 再 map 到 FuturesSymbolInfo schema。
        """
        async def _do() -> dict[str, Any]:
            premium = await self._get_json(
                "/fapi/v1/premiumIndex", params={"symbol": symbol}, symbol_for_error=symbol,
            )
            # exchangeInfo 是全量 · 缓存友好;M2-A 不做缓存 · 直接拉
            ex_info = await self._get_json("/fapi/v1/exchangeInfo", symbol_for_error=symbol)
            return {"premium_index": premium, "exchange_info": ex_info, "symbol": symbol}

        return await self._retry(op="fetch_symbol_info", symbol=symbol, coro_factory=_do)

    # ========================================================================
    # BaseDataSource 抽象方法兜底(本 adapter 不提供 symbol_meta)
    # ========================================================================

    async def list_symbols(self) -> list[Any]:
        """合约市场的 symbol 元信息走 fetch_symbol_info · 不实装通用 list。"""
        raise NotImplementedError(
            "BinanceFuturesSource 不提供 list_symbols · 用 fetch_ticker_24h() 列全市场",
        )


# ============================================================================
# 解析器 helpers
# ============================================================================


def _parse_kline_row(row: list[Any], *, symbol: str) -> Kline:
    """Binance fapi/v1/klines 返回的 array · 字段顺序:
    [openTime, open, high, low, close, volume, closeTime, quoteVolume, trades,
     takerBuyBase, takerBuyQuote, ignore]
    """
    try:
        ts_ms = int(row[0])
        return Kline(
            ts=datetime.fromtimestamp(ts_ms / 1000, tz=UTC),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            amount=float(row[7]) if row[7] else None,
        )
    except (IndexError, ValueError, TypeError) as exc:
        raise DataFormatError(
            f"kline 行解析失败: {row[:5]}... {exc}",
            market="crypto", symbol=symbol, upstream="binance-futures",
        ) from exc


def _parse_funding_row(row: dict[str, Any], *, symbol: str) -> FundingRate:
    """fundingRate 返回字典:
    {symbol, fundingTime (ms), fundingRate (string), markPrice (string)}
    """
    try:
        return FundingRate(
            symbol=row["symbol"],
            ts=datetime.fromtimestamp(int(row["fundingTime"]) / 1000, tz=UTC),
            rate=float(row["fundingRate"]),
            mark_price=float(row.get("markPrice") or 0),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise DataFormatError(
            f"funding 行解析失败: {row} {exc}",
            market="crypto", symbol=symbol, upstream="binance-futures",
        ) from exc


def _parse_premium_index_row(row: dict[str, Any]) -> PremiumIndex | None:
    """premiumIndex 行 → PremiumIndex · 非法行返回 None(由调用方跳过,不抛)。

    上游字段:
    {symbol, markPrice, indexPrice, estimatedSettlePrice, lastFundingRate,
     interestRate, nextFundingTime (ms), time (ms)}
    estimatedSettlePrice / interestRate 本期不用。

    跳过条件:
    - 含 '_' 的交割合约(只要永续)
    - mark/index/nextFundingTime <= 0(下架/异常)
    """
    try:
        symbol = str(row["symbol"])
        if "_" in symbol:  # 交割合约(BTCUSDT_240628)· 非永续 · 跳过
            return None
        mark = float(row["markPrice"])
        index = float(row["indexPrice"])
        next_ms = int(row["nextFundingTime"])
        if mark <= 0 or index <= 0 or next_ms <= 0:
            return None
        return PremiumIndex(
            symbol=symbol,
            ts=datetime.fromtimestamp(int(row["time"]) / 1000, tz=UTC),
            mark_price=mark,
            index_price=index,
            last_funding_rate=float(row.get("lastFundingRate") or 0),
            next_funding_time=datetime.fromtimestamp(next_ms / 1000, tz=UTC),
        )
    except (KeyError, ValueError, TypeError):
        return None


def _parse_oi_row(row: dict[str, Any], *, symbol: str) -> OpenInterest:
    """openInterestHist 返回字典:
    {symbol, sumOpenInterest, sumOpenInterestValue, timestamp (ms)}
    """
    try:
        return OpenInterest(
            symbol=row["symbol"],
            ts=datetime.fromtimestamp(int(row["timestamp"]) / 1000, tz=UTC),
            oi_coin=float(row["sumOpenInterest"]),
            oi_usd=float(row["sumOpenInterestValue"]),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise DataFormatError(
            f"OI 行解析失败: {row} {exc}",
            market="crypto", symbol=symbol, upstream="binance-futures",
        ) from exc


def _parse_ticker_row(row: dict[str, Any], *, instrument: Literal["spot", "perp"]) -> Ticker24h:
    """ticker/24hr 返回字典 · perp 字段示例:
    {symbol: BTCUSDT, lastPrice, priceChangePercent, highPrice, lowPrice,
     volume, quoteVolume, count}
    """
    binance_symbol = row["symbol"]  # "BTCUSDT"
    ccxt_symbol = _to_ccxt_symbol(binance_symbol)  # "BTC/USDT"
    return Ticker24h(
        symbol=ccxt_symbol,
        instrument=instrument,
        ts=datetime.now(tz=UTC),  # ticker 是当下快照 · 用本地拉取时间
        last_price=float(row["lastPrice"]),
        change_pct_24h=float(row["priceChangePercent"]),
        high_24h=float(row["highPrice"]),
        low_24h=float(row["lowPrice"]),
        volume_24h=float(row["volume"]),
        quote_volume_24h=float(row["quoteVolume"]),
        count_24h=int(row.get("count", 0)),
    )


def _merge_long_short(
    *,
    account: list[dict[str, Any]],
    position: list[dict[str, Any]],
    taker: list[dict[str, Any]],
    symbol: str,
) -> list[LongShortRatio]:
    """三套指标按 timestamp 对齐合并。"""
    # 按 timestamp 索引化
    by_ts_account = {int(r["timestamp"]): r for r in account}
    by_ts_position = {int(r["timestamp"]): r for r in position}
    by_ts_taker = {int(r["timestamp"]): r for r in taker}

    # 取三者交集 ts(避免缺数)
    common_ts = sorted(set(by_ts_account) & set(by_ts_position) & set(by_ts_taker))

    results: list[LongShortRatio] = []
    for ts_ms in common_ts:
        a = by_ts_account[ts_ms]
        p = by_ts_position[ts_ms]
        t = by_ts_taker[ts_ms]
        try:
            results.append(LongShortRatio(
                symbol=symbol,
                ts=datetime.fromtimestamp(ts_ms / 1000, tz=UTC),
                top_account_long=float(a["longAccount"]),
                top_account_short=float(a["shortAccount"]),
                top_account_ratio=float(a["longShortRatio"]),
                top_position_long=float(p["longAccount"]),
                top_position_short=float(p["shortAccount"]),
                top_position_ratio=float(p["longShortRatio"]),
                taker_buy_vol=float(t["buyVol"]),
                taker_sell_vol=float(t["sellVol"]),
                taker_ratio=float(t["buySellRatio"]),
            ))
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("[binance-futures] long_short merge skip ts=%s · %s", ts_ms, exc)
            continue
    return results


def _to_ccxt_symbol(binance_symbol: str) -> str:
    """`BTCUSDT` → `BTC/USDT`(USDT-M 永续约定).

    简单切尾约定:USDT/USDC/BUSD/FDUSD 作为常见 quote · 找不到就退回原值。
    """
    for quote in ("USDT", "USDC", "BUSD", "FDUSD"):
        if binance_symbol.endswith(quote) and len(binance_symbol) > len(quote):
            base = binance_symbol[: -len(quote)]
            return f"{base}/{quote}"
    return binance_symbol


def _to_binance_symbol(ccxt_symbol: str) -> str:
    """`BTC/USDT` → `BTCUSDT`."""
    return ccxt_symbol.replace("/", "")
