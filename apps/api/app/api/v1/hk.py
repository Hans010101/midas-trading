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

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ClickHouseDep
from app.schemas.hk_market import HkBoardResponse
from app.schemas.market_home import MarketHomeOverview
from app.services.clickhouse_hk_market import select_latest_breadth, select_latest_spot
from app.services.clickhouse_market_home import select_latest_indices
from app.services.market_calendar import compute_market_status
from app.services.market_home_config import HK_INDEX_CODES

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
