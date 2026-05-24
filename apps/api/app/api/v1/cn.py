"""A股市场首页 API · /api/v1/cn(0023 阶段③ · 3.1 基建)。

3.1:GET /cn/overview = 市场状态(交易时段)+ 大盘指数卡(4 指数)。
后续 3.2 在本路由扩展:榜单 Tab(涨幅/跌幅/成交额/换手/量比)+ 涨跌家数 + 涨跌停 + 行业板块。

数据流:只读 ClickHouse(market_index_snapshot / market_trade_calendar)·
实际数据由 Celery worker(tasks.market.cn_*)在 A股交易时段定时写入。

红线:本路由全部 GET · 无任何写动作 · 行情只读 · 不碰交易接口。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter

from app.api.deps import ClickHouseDep
from app.schemas.market_home import MarketHomeOverview
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
