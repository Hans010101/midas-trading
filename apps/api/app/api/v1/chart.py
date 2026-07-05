"""K线图 PNG 端点(KLINE-001)· bot「K线」按钮 sendPhoto 用。

GET /api/v1/chart/kline.png?market=&symbol=&name=&period= → image/png。
读 CH K线 → 不足则【回源写库】(fetch-on-miss · 复用 /market/kline 路径:cn=akshare / us=yfinance /
hk=akshare / crypto=binance perp)→ mplfinance 渲染 PNG。回源后仍不足(冷门无数据)→ 404(调用方 bot
回退网页链接)。覆盖任意符号(不再只限 worker 预存的 demo 符号)· crypto 走 perp(对齐加密 perp 主体)。

★ 红线:K线数据读取 + 画图 · 不碰下单/撮合/虚拟引擎/红线。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import (
    BinanceFuturesSourceDep,
    ClickHouseDep,
    CnSourceDep,
    HkSourceDep,
    RequestLangDep,
    UsSourceDep,
)
from app.schemas.market import Kline, Market, Period
from app.services.charting.kline_render import render_kline_png_async
from app.services.clickhouse_client import ClickHouseClient
from app.services.data_sources.base import BaseDataSource
from app.services.data_sources.exceptions import DataSourceError
from app.services.i18n import translate

router = APIRouter(prefix="/chart", tags=["chart"])
logger = logging.getLogger(__name__)

_MIN_KLINES = 30  # 少于此画不出有意义指标 → 回退链接
_LIMIT = 150  # 画图取最近 N 根(够 MA20/MACD 暖机 + 视觉密度)


async def _fetch_on_miss(
    ch: ClickHouseClient,
    *,
    market: Market,
    ch_symbol: str,
    period: Period,
    instrument: str,
    cn: BaseDataSource,
    us: BaseDataSource,
    hk: BaseDataSource,
    binance_futures: BaseDataSource,
) -> list[Kline]:
    """CH 不足 → 回源 + 写库 + 返回(复用 /market/kline 回源:perp→binance_futures · spot→市场源)。

    回源失败(冷门无数据 / 上游不可达 / 格式异常 = DataSourceError 全子类)→ 返空,
    调用方据此 404 → 回退网页链接(fallback 保留)。写库 = 缓存,下次直接命中。
    """
    src: BaseDataSource = (
        binance_futures if instrument == "perp" else {"cn": cn, "us": us, "hk": hk}.get(market, cn)
    )
    try:
        upstream = await src.fetch_kline(ch_symbol, period, limit=_LIMIT)
    except DataSourceError as e:
        logger.info("[chart.kline] 回源失败 %s/%s:%s · 将回退链接", market, ch_symbol, e)
        return []
    if upstream:
        await ch.insert_kline(
            upstream, symbol=ch_symbol, market=market, period=period, instrument=instrument,
        )
    return upstream


@router.get(
    "/kline.png",
    summary="K线图 PNG(bot sendPhoto · 读 CH 不足则回源 · 复用 /market/kline)",
    responses={
        200: {"content": {"image/png": {}}, "description": "K线图 PNG"},
        404: {"description": "回源后仍数据不足 · 调用方回退网页链接"},
    },
)
async def get_kline_png(
    ch: ClickHouseDep,
    cn: CnSourceDep,
    us: UsSourceDep,
    hk: HkSourceDep,
    binance_futures: BinanceFuturesSourceDep,
    lang: RequestLangDep,
    market: Market,
    symbol: Annotated[str, Query(min_length=1, max_length=32, description="标的(crypto 可带斜杠)")],
    name: Annotated[str, Query(max_length=32, description="中文名(标题用 · 缺省用 symbol)")] = "",
    period: Period = "1d",
) -> Response:
    # crypto = perp K线(去斜杠对齐 binance 风格 · 同 /market/kline)· cn/us/hk = spot
    instrument = "perp" if market == "crypto" else "spot"
    ch_symbol = symbol.replace("/", "") if market == "crypto" else symbol

    klines = await ch.select_kline(
        symbol=ch_symbol, market=market, period=period, limit=_LIMIT, instrument=instrument,
    )
    if len(klines) < _MIN_KLINES:
        # fetch-on-miss:CH 没有/不足 → 回源写库(覆盖任意符号 · 和详情页同数据路径)
        klines = await _fetch_on_miss(
            ch, market=market, ch_symbol=ch_symbol, period=period, instrument=instrument,
            cn=cn, us=us, hk=hk, binance_futures=binance_futures,
        )
    if len(klines) < _MIN_KLINES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=translate("chart.insufficient_kline_data", lang, count=len(klines)),
        )
    try:
        png = await render_kline_png_async(
            symbol=symbol, name=name or symbol, market=market, klines=klines,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e),
        ) from e

    logger.info(
        "[chart.kline] rendered · market=%s symbol=%s rows=%d bytes=%d",
        market, symbol, len(klines), len(png),
    )
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},  # 此刻截图 · 不缓存
    )
