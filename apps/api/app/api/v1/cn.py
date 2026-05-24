"""A股市场首页 API · /api/v1/cn(0023 阶段③ · 3.1 基建)。

3.1:GET /cn/overview = 市场状态(交易时段)+ 大盘指数卡(4 指数)。
后续 3.2 在本路由扩展:榜单 Tab(涨幅/跌幅/成交额/换手/量比)+ 涨跌家数 + 涨跌停 + 行业板块。

数据流:只读 ClickHouse(market_index_snapshot / market_trade_calendar)·
实际数据由 Celery worker(tasks.market.cn_*)在 A股交易时段定时写入。

红线:本路由全部 GET · 无任何写动作 · 行情只读 · 不碰交易接口。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ClickHouseDep
from app.schemas.cn_market import CnBoardResponse
from app.schemas.market_home import MarketHomeOverview
from app.services.clickhouse_cn_market import (
    select_latest_breadth,
    select_latest_sectors,
    select_latest_spot,
)
from app.services.clickhouse_market_home import select_latest_indices, select_trade_days
from app.services.market_calendar import compute_market_status
from app.services.market_home_config import CN_INDEX_CODES

router = APIRouter(prefix="/cn", tags=["cn"])

# 交易日历查询窗口 · 状态机只需判「今天」· ±7 天足够覆盖时区边界
_CAL_WINDOW_DAYS = 7


@router.get(
    "/overview",
    response_model=MarketHomeOverview,
    summary="A股市场首页总览(交易状态 + 大盘指数)",
    description="返回 A股市场状态(盘中/午间休市/已收盘/休市)+ 上证/深成/创业板/沪深300 四大指数。",
)
async def get_cn_overview(ch: ClickHouseDep) -> MarketHomeOverview:
    indices = await select_latest_indices(
        ch._client, market="cn", order=CN_INDEX_CODES,  # noqa: SLF001
    )
    now = datetime.now(tz=UTC)
    trading_days = await select_trade_days(
        ch._client,  # noqa: SLF001
        market="cn",
        since=now.date() - timedelta(days=_CAL_WINDOW_DAYS),
        until=now.date() + timedelta(days=_CAL_WINDOW_DAYS),
    )
    data_as_of = max((q.ts for q in indices), default=None)
    status = compute_market_status(
        "cn", now_utc=now, data_as_of=data_as_of, cn_trading_days=trading_days,
    )
    return MarketHomeOverview(market="cn", status=status, indices=indices)


@router.get(
    "/board",
    response_model=CnBoardResponse,
    summary="A股榜单 + 情绪条 + 行业板块(3.2)",
    description=(
        "情绪条(涨跌平家数 + 涨跌停估算)+ 涨幅/跌幅/成交额 3 榜(同一全市场快照 3 种排序)+ "
        "行业板块。Sina 源 · 只读。换手率/量比本期不做(Sina 无字段 · 东财不可达)。"
    ),
)
async def get_cn_board(
    ch: ClickHouseDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CnBoardResponse:
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
    sectors = await select_latest_sectors(ch._client, limit=60)  # noqa: SLF001
    return CnBoardResponse(
        breadth=breadth,
        data_as_of=breadth.ts if breadth else None,
        gainers=gainers,
        losers=losers,
        top_amount=top_amount,
        sectors=sectors,
    )
