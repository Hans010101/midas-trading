"""港股市场首页 API · /api/v1/hk(港股首页全市场 · 对标 A股 cn)。

- GET /hk/overview = 市场状态(港股交易时段)+ 大盘指数卡(恒生 + 恒生国企)。
- GET /hk/board    = 情绪条(涨跌平家数 + 总成交额 · ★港股无涨跌停)+ 涨幅/跌幅/成交额 3 榜单。

数据流:只读 ClickHouse(market_index_snapshot market='hk' · hk_spot_snapshot · hk_market_breadth)·
实际数据由 Celery worker(tasks.market.hk_board_scan 新浪全市场 + global_overview_scan 指数)
在港股交易时段定时写入。

★ 边界:本路由全部 GET · 只读行情 · 不碰下单/AI(港股阶段三)· 板块暂不做(全市场无现成行业源)。
红线:港股 = 行情展示 · 只读 · 不可交易。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ClickHouseDep
from app.schemas.hk_market import (
    HkBoardLotScanResult,
    HkBoardResponse,
    HkKlineSourceProbe,
)
from app.schemas.market_home import MarketHomeOverview
from app.services.clickhouse_hk_market import select_latest_breadth, select_latest_spot
from app.services.clickhouse_market_home import select_latest_indices
from app.services.hk_board_lot import fetch_hkex_board_lots
from app.services.hk_kline_probe import probe_hk_kline_sources
from app.services.market_calendar import compute_market_status
from app.services.market_home_config import HK_INDEX_CODES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hk", tags=["hk"])


@router.get(
    "/overview",
    response_model=MarketHomeOverview,
    summary="港股市场首页总览(交易状态 + 大盘指数)",
    description="港股市场状态(盘中/午间休市/已收盘/休市)+ 恒生指数 / 恒生国企指数。",
)
async def get_hk_overview(ch: ClickHouseDep) -> MarketHomeOverview:
    indices = await select_latest_indices(
        ch._client, market="hk", order=HK_INDEX_CODES,  # noqa: SLF001
    )
    now = datetime.now(tz=UTC)
    data_as_of = max((q.ts for q in indices), default=None)
    # 港股状态机只看 HKT 时段(_hk_status)· 无需交易日历参数(同美股硬编码节假日)
    status = compute_market_status("hk", now_utc=now, data_as_of=data_as_of)
    return MarketHomeOverview(market="hk", status=status, indices=indices)


@router.get(
    "/board",
    response_model=HkBoardResponse,
    summary="港股榜单 + 情绪条(全市场 ~2764 只)",
    description=(
        "情绪条(涨跌平家数 + 总成交额 · ★港股无涨跌停)+ 涨幅/跌幅/成交额 3 榜"
        "(同一全市场快照 3 种排序)。新浪 stock_hk_spot 源 · 只读。"
        "板块暂不做(港股全市场无现成行业源 · 留后续)。"
    ),
)
async def get_hk_board(
    ch: ClickHouseDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
) -> HkBoardResponse:
    # le=1000:供前端滚动加载到数据池底(限页 ~900 只)· 默认 50 不变
    breadth = await select_latest_breadth(ch._client)  # noqa: SLF001
    gainers = await select_latest_spot(
        ch._client, sort_by="change_pct", order="DESC", limit=limit,  # noqa: SLF001
    )
    losers = await select_latest_spot(
        ch._client, sort_by="change_pct", order="ASC", limit=limit,  # noqa: SLF001
    )
    top_amount = await select_latest_spot(
        ch._client, sort_by="amount", order="DESC", limit=limit,  # noqa: SLF001
    )
    return HkBoardResponse(
        breadth=breadth,
        data_as_of=breadth.ts if breadth else None,
        gainers=gainers,
        losers=losers,
        top_amount=top_amount,
    )


@router.get(
    "/board-lot-scan",
    response_model=HkBoardLotScanResult,
    summary="[阶段三A1] HKEX board lot 下载+解析实测(生产可达验证 · 只读不写库)",
    description=(
        "下载港交所官方 ListOfSecurities.xlsx → 解析主板 HKD 普通股 board lot,返摘要。"
        "★ A1 只读 · 不写库、不改下单池(A2 才放量)· 用于生产 VPS 实测 HKEX 可达 + 解析正确。"
    ),
)
async def hk_board_lot_scan() -> HkBoardLotScanResult:
    # 阻塞下载+解析经 asyncio.to_thread(项目约定 · 同 chan._analyze_sync)· 不阻塞事件循环
    r = await asyncio.to_thread(fetch_hkex_board_lots)
    logger.info(
        "[hk-board-lot-scan] ok=%s http=%s bytes=%s mainboard_hkd=%s errors=%s updated=%s",
        r.ok, r.http_code, r.bytes_downloaded, r.mainboard_hkd_count,
        r.parse_errors, r.updated_as_at,
    )
    return HkBoardLotScanResult(
        ok=r.ok, http_code=r.http_code, bytes_downloaded=r.bytes_downloaded,
        updated_as_at=r.updated_as_at, total_rows=r.total_rows,
        mainboard_hkd_count=r.mainboard_hkd_count, parse_errors=r.parse_errors,
        samples=r.samples, error=r.error,
    )


@router.get(
    "/kline-source-probe",
    response_model=HkKlineSourceProbe,
    summary="[方案A阶段1] 港股K线源探测(新浪 stock_hk_daily 生产可达 · 只读不改降级链)",
    description=(
        "探测新浪 stock_hk_daily(主源候选)+ yfinance(现备用)对某冷门股的生产可达性 + 行数。"
        "★ 只读 · 不改 fetch_kline 降级链(零回归)· 实测新浪生产可达后阶段2 再正式接入主源。"
    ),
)
async def hk_kline_source_probe(
    symbol: Annotated[str, Query(description="港股代码 · 默认冷门 00980 联华超市")] = "00980",
) -> HkKlineSourceProbe:
    r = await asyncio.to_thread(probe_hk_kline_sources, symbol)
    logger.info(
        "[hk-kline-probe] %s sina_ok=%s rows=%s yf_ok=%s",
        r.symbol, r.sina_ok, r.sina_rows, r.yfinance_ok,
    )
    return HkKlineSourceProbe(
        symbol=r.symbol, sina_ok=r.sina_ok, sina_rows=r.sina_rows, sina_last=r.sina_last,
        sina_error=r.sina_error, yfinance_ok=r.yfinance_ok, yfinance_rows=r.yfinance_rows,
        yfinance_error=r.yfinance_error,
    )
