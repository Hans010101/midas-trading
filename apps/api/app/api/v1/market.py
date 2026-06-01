"""市场数据 API · /api/v1/market

- GET /kline:统一行情接口,cache-aside ClickHouse → 回源
- GET /symbols:标的搜索(用 ClickHouse symbol_meta)
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal, get_args

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import (
    BinanceFuturesSourceDep,
    ClickHouseDep,
    CnSourceDep,
    CryptoSourceDep,
    HkSourceDep,
    UsSourceDep,
)
from app.schemas.market import KlineResponse, Market, Period, SymbolMeta
from app.services.data_sources.base import BaseDataSource
from app.services.data_sources.exceptions import (
    DataSourceError,
    SymbolNotFoundError,
    UpstreamUnavailableError,
)

# M2-B(0017 ADR)· instrument 区分 spot/perp · 默认 spot 向后兼容
Instrument = Literal["spot", "perp"]

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/market", tags=["market"])

_MARKETS: tuple[str, ...] = get_args(Market)
_PERIODS: tuple[str, ...] = get_args(Period)


@router.get(
    "/kline",
    response_model=KlineResponse,
    summary="跨市场 K 线",
    description="先查 ClickHouse,缺数据再回源到对应市场的数据源适配器,"
    "回源结果写回 CH(下次直接命中)。",
)
async def get_kline(
    ch: ClickHouseDep,
    cn: CnSourceDep,
    us: UsSourceDep,
    crypto: CryptoSourceDep,
    hk: HkSourceDep,
    binance_futures: BinanceFuturesSourceDep,
    symbol: str = Query(..., min_length=1, examples=["600519", "NVDA", "BTC/USDT", "00700"]),
    market: Market = Query(...),
    period: Period = Query("1d"),
    limit: int = Query(500, ge=1, le=5000),
    instrument: Annotated[
        Instrument,
        Query(description="'spot' 现货(默认)· 'perp' USDT-M 永续合约 · 只 crypto 市场支持 perp"),
    ] = "spot",
) -> KlineResponse:
    # M2-B 校验:perp 只允许 crypto 市场(cn/us 没有 perp)
    if instrument == "perp" and market != "crypto":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"instrument=perp 只支持 market=crypto · 当前 market={market}",
        )

    # 1. 缓存命中:CH 已有 ≥ limit 条 → 直接返回(最近 limit 条)
    cached = await ch.select_kline(
        symbol=symbol, market=market, period=period, limit=limit, instrument=instrument,
    )
    if len(cached) >= limit:
        logger.info(
            "[market.kline] cache hit · symbol=%s market=%s instrument=%s period=%s rows=%d",
            symbol, market, instrument, period, len(cached),
        )
        return KlineResponse(symbol=symbol, market=market, period=period, items=cached[-limit:])

    # 2. 缓存未命中(或不足):回源
    # M2-B · perp 走 BinanceFuturesSource;spot 走原有 _source_for 逻辑
    if instrument == "perp":
        # perp symbol 用 Binance Futures 风格(BTCUSDT 无斜杠)· 如果传入 BTC/USDT 转一下
        binance_symbol = symbol.replace("/", "") if "/" in symbol else symbol
        source: BaseDataSource = binance_futures
        fetch_symbol = binance_symbol
    else:
        source = _source_for(market, cn=cn, us=us, crypto=crypto, hk=hk)
        fetch_symbol = symbol

    try:
        upstream_rows = await source.fetch_kline(fetch_symbol, period, limit=limit)
    except SymbolNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except UpstreamUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e
    except DataSourceError as e:
        # DataFormatError 等其他业务异常 → 502 上游协议异常
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e

    # 3. 写回 CH(insert_kline 内部已经做去重,幂等)· 带上 instrument
    written = await ch.insert_kline(
        upstream_rows, symbol=symbol, market=market, period=period, instrument=instrument,
    )
    logger.info(
        "[market.kline] upstream fetch + write · symbol=%s market=%s instrument=%s"
        " period=%s upstream=%d ch_new=%d",
        symbol, market, instrument, period, len(upstream_rows), written,
    )

    return KlineResponse(
        symbol=symbol,
        market=market,
        period=period,
        items=upstream_rows[-limit:],
    )


@router.get(
    "/symbols",
    response_model=list[SymbolMeta],
    summary="标的搜索(模糊匹配 symbol / 中文名 / 英文名)",
)
async def search_symbols(
    ch: ClickHouseDep,
    q: str = Query(..., min_length=1, max_length=64, description="搜索关键词"),
    market: Market | None = Query(None, description="限定市场(可选)"),
    limit: int = Query(50, ge=1, le=200),
) -> list[SymbolMeta]:
    return await ch.search_symbols(query=q, market=market, limit=limit)


# ===========================
# 辅助
# ===========================

def _source_for(
    market: Market,
    *,
    cn: CnSourceDep,
    us: UsSourceDep,
    crypto: CryptoSourceDep,
    hk: HkSourceDep,
) -> BaseDataSource:
    """市场 → 对应适配器。"""
    mapping: dict[Market, BaseDataSource] = {
        "cn": cn,
        "us": us,
        "crypto": crypto,
        "hk": hk,
    }
    return mapping[market]


# 让 _MARKETS / _PERIODS 在 ruff 不被判 unused(供 OpenAPI 文档展示用)
__all__ = ["router", "_MARKETS", "_PERIODS"]
