"""K线图 PNG 端点(KLINE-001)· bot「K线」按钮 sendPhoto 用。

GET /api/v1/chart/kline.png?market=&symbol=&name=&period= → image/png。
只读已有 CH K线数据 → mplfinance 渲染 PNG · 数据不足(< 30 根)→ 404(调用方 bot 回退网页链接)。
★ 红线:纯只读画图 · 不回源(无写)· 不碰下单/撮合/红线。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import ClickHouseDep
from app.schemas.market import Market, Period
from app.services.charting.kline_render import render_kline_png_async

router = APIRouter(prefix="/chart", tags=["chart"])
logger = logging.getLogger(__name__)

_MIN_KLINES = 30  # 少于此画不出有意义指标 → 回退链接
_LIMIT = 150  # 画图取最近 N 根(够 MA20/MACD 暖机 + 视觉密度)


@router.get(
    "/kline.png",
    summary="K线图 PNG(bot sendPhoto · 只读已有 K线数据渲染)",
    responses={
        200: {"content": {"image/png": {}}, "description": "K线图 PNG"},
        404: {"description": "K线数据不足 · 调用方回退网页链接"},
    },
)
async def get_kline_png(
    ch: ClickHouseDep,
    market: Market,
    symbol: Annotated[str, Query(min_length=1, max_length=32, description="标的(crypto 可带斜杠)")],
    name: Annotated[str, Query(max_length=32, description="中文名(标题用 · 缺省用 symbol)")] = "",
    period: Period = "1d",
) -> Response:
    # crypto = perp K线(去斜杠对齐 CH 键 · 同 /market/kline)· cn/us/hk = spot
    instrument = "perp" if market == "crypto" else "spot"
    ch_symbol = symbol.replace("/", "") if market == "crypto" else symbol

    klines = await ch.select_kline(
        symbol=ch_symbol, market=market, period=period,
        limit=_LIMIT, instrument=instrument,
    )
    if len(klines) < _MIN_KLINES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"K线数据不足({len(klines)} 根)· 无法渲染",
        )
    try:
        png = await render_kline_png_async(
            symbol=symbol, name=name or symbol, market=market, klines=klines,
        )
    except ValueError as e:  # 渲染层数据不足兜底
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
        # 此刻截图 · 不缓存(每次新鲜)· TG 拉 URL 时拿最新
        headers={"Cache-Control": "no-store"},
    )
