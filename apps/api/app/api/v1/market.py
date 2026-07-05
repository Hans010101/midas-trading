"""市场数据 API · /api/v1/market

- GET /kline:统一行情接口,cache-aside ClickHouse → 回源
- GET /symbols:标的搜索(用 ClickHouse symbol_meta)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated, Literal, get_args

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import (
    BinanceFuturesSourceDep,
    ClickHouseDep,
    CnSourceDep,
    CryptoSourceDep,
    HkSourceDep,
    RequestLangDep,
    UsSourceDep,
)
from app.schemas.market import KlineResponse, Market, Period, SymbolMeta
from app.services.data_sources.base import BaseDataSource
from app.services.data_sources.exceptions import (
    DataSourceError,
    SymbolNotFoundError,
    UpstreamUnavailableError,
)
from app.services.hk_pool import HK_POOL
from app.services.i18n import translate
from app.services.kline_freshness import get_fresh_kline

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
    lang: RequestLangDep,
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
            detail=translate("common.perp_only_crypto", lang, market=market),
        )

    # 刀A2-1:cache-aside 收敛进 get_fresh_kline(端点 + 撮合 fetcher 共用)——
    #   行数不足 → 回源(原行为);行数够但末根过期(仅 crypto)→ 也回源(治多周期永久 stale)。
    #   perp symbol 归一 / 同 ts 重复行去重在 ClickHouseClient 内部(所有调用方生效)。
    source: BaseDataSource = (
        binance_futures
        if instrument == "perp"
        else _source_for(market, cn=cn, us=us, crypto=crypto, hk=hk)
    )
    try:
        items = await get_fresh_kline(
            ch,
            symbol=symbol,
            market=market,
            period=period,
            limit=limit,
            instrument=instrument,
            source=source,
        )
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

    return KlineResponse(symbol=symbol, market=market, period=period, items=items)


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
    # 港股标的 = 策展池(阶段二只读 · 固定 18 只 · 不依赖 CH symbol_meta 是否已采)
    # 按 q 过滤代码 / 中文名;阶段四接全市场后再走 CH 搜索。
    if market == "hk":
        now = datetime.now(tz=UTC)
        ql = q.strip().lower()
        metas = [
            SymbolMeta(symbol=sym, market="hk", name=name, updated_at=now)
            for sym, name, _lot, _sector in HK_POOL
            if ql in sym.lower() or ql in name.lower()
        ]
        return metas[:limit]
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
