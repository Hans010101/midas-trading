"""Crypto Pro API · /api/v1/crypto(0017 ADR · M2-A)。

7 个新端点 · 给 M2-D 前端 landing page + 详情页合约 tab 消费:

  GET /overview                                · 加密 tab landing 顶层
  GET /tickers/24h?instrument=spot|perp&...    · 涨幅榜 / 跌幅榜 / 量榜
  GET /futures/{symbol}/funding-rate?limit=N   · 资金费率时间序列
  GET /futures/{symbol}/open-interest?limit=N  · OI 时间序列
  GET /futures/{symbol}/long-short-ratio?...   · 多空比时间序列
  GET /futures/{symbol}/info                   · 合约元信息(下次资金费率 / 标记价)
  GET /fear-greed?limit=30                     · FGI 时间序列(给图表用)

数据流:
  · 先查 ClickHouse(预热的快照数据)
  · 缺数据走 cache-aside 回源到 BinanceFuturesSource / CoinGeckoSource 等
  · 回源结果写回 CH(下次直接命中)

注:回源逻辑 M2-A 留 stub · M2-B 实装(目前 only ClickHouse read · 数据由
Celery 任务 M2-A-9 准备 · 见 apps/worker/tasks/crypto_metrics_ingest.py)。

红线:本路由全部 GET · 无任何写动作(crypto 写入由 Celery worker 完成)·
任何「交易」类动作走 /api/v1/virtual(已有的虚拟撮合)· 不在这里。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query, status

from app.api.deps import ClickHouseDep
from app.schemas.crypto import (
    CryptoOverviewResponse,
    FearGreedResponse,
    FundingRateResponse,
    FuturesSymbolInfo,
    LongShortRatioResponse,
    MarketOverview,
    OpenInterestResponse,
    Ticker24h,
    Tickers24hResponse,
)
from app.services.clickhouse_crypto import (
    select_fear_greed_series,
    select_funding_rates,
    select_latest_overview,
    select_latest_tickers,
    select_long_short,
    select_open_interest,
    select_perp_total_quote_volume,
    select_tickers_by_symbols,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crypto", tags=["crypto"])


# ============================================================================
# 1 · GET /overview · 加密 tab landing page 顶层数据
# ============================================================================


@router.get(
    "/overview",
    response_model=CryptoOverviewResponse,
    summary="加密市场总览",
    description=(
        "返回:全市场总览(总市值/dominance/FGI) + 涨幅榜 top 5 + "
        "跌幅榜 top 5 + 成交榜 top 5。给加密 tab landing page 用。"
    ),
)
async def get_overview(ch: ClickHouseDep) -> CryptoOverviewResponse:
    # 走 ClickHouse · 实际数据由 Celery 任务定期写入
    # ch 是 ClickHouseClient 对象 · 内部 self._client 是 AsyncClient · M2-A
    # 联调时 type ignore · M2-B 把 ClickHouseClient 改成有 .raw 暴露 AsyncClient
    overview = await select_latest_overview(ch._client)  # type: ignore[attr-defined]
    if overview is None:
        # 没数据 · M2-A 阶段允许返 stub · M2-B 之前 Celery 任务确保有数据
        overview = MarketOverview(
            ts=datetime.now(tz=UTC),
            total_market_cap_usd=0,
            total_volume_24h_usd=0,
            btc_dominance=0,
            eth_dominance=0,
            fear_greed_value=0,
            fear_greed_classification="N/A",
        )

    # 涨幅榜 / 跌幅榜 / 成交榜 · 都取 spot top 5(M2-D 可改成 perp)
    try:
        top_gainers = await select_latest_tickers(
            ch._client,  # type: ignore[attr-defined]
            instrument="spot",
            sort_by="change_pct_24h",
            order="DESC",
            limit=5,
        )
        top_losers = await select_latest_tickers(
            ch._client,  # type: ignore[attr-defined]
            instrument="spot",
            sort_by="change_pct_24h",
            order="ASC",
            limit=5,
        )
        top_volume = await select_latest_tickers(
            ch._client,  # type: ignore[attr-defined]
            instrument="spot",
            sort_by="quote_volume_24h",
            order="DESC",
            limit=5,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[crypto.overview] tickers 拉取失败 · 返空榜单: %s", exc)
        top_gainers = []
        top_losers = []
        top_volume = []

    # 24H 合约总成交额:CoinGecko 免费档拿不到 derivatives_volume(硬编码 0),
    # 这里用已采集的全 perp ticker 的 quote_volume_24h 求和兜底(真实数据)。
    btc_ticker = None
    eth_ticker = None
    try:
        if overview.derivatives_volume_24h_usd <= 0:
            perp_total = await select_perp_total_quote_volume(ch._client)  # type: ignore[attr-defined]
            if perp_total > 0:
                overview = overview.model_copy(
                    update={"derivatives_volume_24h_usd": perp_total},
                )
        # BTC/ETH 价格卡:按 symbol 精确取 perp ticker(不依赖涨跌幅榜)
        by_sym = await select_tickers_by_symbols(
            ch._client,  # type: ignore[attr-defined]
            instrument="perp",
            symbols=["BTC/USDT", "ETH/USDT"],
        )
        btc_ticker = by_sym.get("BTC/USDT")
        eth_ticker = by_sym.get("ETH/USDT")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[crypto.overview] 合约成交额/BTC-ETH ticker 拉取失败: %s", exc)

    return CryptoOverviewResponse(
        market_overview=overview,
        top_gainers=top_gainers,
        top_losers=top_losers,
        top_volume=top_volume,
        btc_ticker=btc_ticker,
        eth_ticker=eth_ticker,
    )


# ============================================================================
# 2 · GET /tickers/24h · 涨幅榜
# ============================================================================


@router.get(
    "/tickers/24h",
    response_model=Tickers24hResponse,
    summary="24h ticker 排行榜",
)
async def get_tickers_24h(
    ch: ClickHouseDep,
    instrument: Annotated[Literal["spot", "perp"], Query()] = "spot",
    sort_by: Annotated[
        Literal["change_pct_24h", "quote_volume_24h", "last_price"], Query()
    ] = "change_pct_24h",
    order: Annotated[Literal["desc", "asc"], Query()] = "desc",
    top: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Tickers24hResponse:
    try:
        items = await select_latest_tickers(
            ch._client,  # type: ignore[attr-defined]
            instrument=instrument,
            sort_by=sort_by,
            order=order.upper(),
            limit=top,
        )
    except ValueError as exc:
        # select_latest_tickers 对 sort_by/order 白名单校验失败
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc),
        ) from exc

    return Tickers24hResponse(
        instrument=instrument, sort_by=sort_by, order=order, items=items,
    )


# ============================================================================
# 3 · GET /futures/{symbol}/funding-rate
# ============================================================================


@router.get(
    "/futures/{symbol}/funding-rate",
    response_model=FundingRateResponse,
    summary="合约资金费率时间序列",
    description="symbol 用 Binance Futures 风格 'BTCUSDT'(无斜杠)。",
)
async def get_funding_rate(
    ch: ClickHouseDep,
    symbol: Annotated[str, Path(min_length=3, examples=["BTCUSDT"])],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> FundingRateResponse:
    items = await select_funding_rates(
        ch._client,  # type: ignore[attr-defined]
        symbol=symbol, limit=limit,
    )
    return FundingRateResponse(symbol=symbol, items=items)


# ============================================================================
# 4 · GET /futures/{symbol}/open-interest
# ============================================================================


@router.get(
    "/futures/{symbol}/open-interest",
    response_model=OpenInterestResponse,
    summary="合约未平仓量(OI)时间序列",
)
async def get_open_interest(
    ch: ClickHouseDep,
    symbol: Annotated[str, Path(min_length=3, examples=["BTCUSDT"])],
    limit: Annotated[int, Query(ge=1, le=500)] = 288,
) -> OpenInterestResponse:
    items = await select_open_interest(
        ch._client,  # type: ignore[attr-defined]
        symbol=symbol, limit=limit,
    )
    return OpenInterestResponse(symbol=symbol, items=items)


# ============================================================================
# 5 · GET /futures/{symbol}/long-short-ratio
# ============================================================================


@router.get(
    "/futures/{symbol}/long-short-ratio",
    response_model=LongShortRatioResponse,
    summary="合约多空比时间序列",
    description="同时返回三套指标:top trader 账户 / top trader 持仓 / taker buy-sell。",
)
async def get_long_short_ratio(
    ch: ClickHouseDep,
    symbol: Annotated[str, Path(min_length=3, examples=["BTCUSDT"])],
    limit: Annotated[int, Query(ge=1, le=500)] = 288,
) -> LongShortRatioResponse:
    items = await select_long_short(
        ch._client,  # type: ignore[attr-defined]
        symbol=symbol, limit=limit,
    )
    return LongShortRatioResponse(symbol=symbol, items=items)


# ============================================================================
# 6 · GET /futures/{symbol}/info
# ============================================================================


@router.get(
    "/futures/{symbol}/info",
    response_model=FuturesSymbolInfo,
    summary="合约元信息(下次资金费率 / 标记价 / 最大杠杆)",
    description=(
        "M2-A WIP · 当前返回 stub(基于 ClickHouse 最近 funding + OI 推断)· "
        "M2-B 实装实时从 Binance Futures /fapi/v1/premiumIndex 拉取。"
    ),
)
async def get_futures_info(
    ch: ClickHouseDep,
    symbol: Annotated[str, Path(min_length=3, examples=["BTCUSDT"])],
) -> FuturesSymbolInfo:
    # M2-A stub · 从 CH 数据拼装 · M2-B 改成回源
    latest_funding = await select_funding_rates(
        ch._client, symbol=symbol, limit=1,  # type: ignore[attr-defined]
    )
    latest_oi = await select_open_interest(
        ch._client, symbol=symbol, limit=1,  # type: ignore[attr-defined]
    )

    if not latest_funding or not latest_oi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"symbol {symbol} 没有 funding 或 OI 数据 · M2-A 数据预热未覆盖此 symbol",
        )

    fr = latest_funding[-1]
    oi = latest_oi[-1]

    # base/quote 简单切尾 USDT/USDC/BUSD
    base, quote = _split_symbol(symbol)

    # 下次资金费率 = 最近 funding ts + 8h(Binance 标准节奏)
    next_funding = fr.ts + timedelta(hours=8)

    return FuturesSymbolInfo(
        symbol=symbol,
        base_asset=base,
        quote_asset=quote,
        contract_type="perpetual",
        mark_price=fr.mark_price,
        index_price=fr.mark_price,  # M2-A 用 mark_price 近似 · M2-B 改 premiumIndex
        last_funding_rate=fr.rate,
        next_funding_time=next_funding,
        max_leverage=125,  # Binance perp 默认上限 · M2-B 从 exchangeInfo 取真值
        open_interest_coin=oi.oi_coin,
        open_interest_usd=oi.oi_usd,
    )


# ============================================================================
# 7 · GET /fear-greed
# ============================================================================


@router.get(
    "/fear-greed",
    response_model=FearGreedResponse,
    summary="Fear & Greed Index 时间序列",
)
async def get_fear_greed(
    ch: ClickHouseDep,
    limit: Annotated[int, Query(ge=1, le=365)] = 30,
) -> FearGreedResponse:
    items = await select_fear_greed_series(
        ch._client, limit=limit,  # type: ignore[attr-defined]
    )
    return FearGreedResponse(items=items)


# ============================================================================
# helpers
# ============================================================================


def _split_symbol(symbol: str) -> tuple[str, str]:
    """`BTCUSDT` → ('BTC', 'USDT')."""
    for quote in ("USDT", "USDC", "BUSD", "FDUSD"):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)], quote
    return symbol, ""
