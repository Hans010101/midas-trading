"""美股市场首页 API · /api/v1/us(0023 阶段③ · 3.1 基建)。

3.1:GET /us/overview = 市场状态(盘前/盘中/盘后/休市 · ET 含 DST)+ 大盘指数卡(4 指数)。
后续 3.3 在本路由扩展:策展股票池榜单 + 行业 / 中概股板块(决策⑥ · 不引入付费源)。

数据流:只读 ClickHouse(market_index_snapshot)· 实际数据由 Celery worker
(tasks.market.us_index_scan)在美股盘前/盘中/盘后时段定时写入。
交易日历:美股用 market_calendar 硬编码节假日(US_MARKET_HOLIDAYS)· 无需查 CH。

红线:本路由全部 GET · 无任何写动作 · 行情只读 · 不碰交易接口。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.deps import ClickHouseDep
from app.schemas.market_home import MarketHomeOverview
from app.services.clickhouse_market_home import select_latest_indices
from app.services.market_calendar import compute_market_status
from app.services.market_home_config import US_INDEX_ORDER

router = APIRouter(prefix="/us", tags=["us"])


@router.get(
    "/overview",
    response_model=MarketHomeOverview,
    summary="美股市场首页总览(交易状态 + 大盘指数)",
    description="返回美股市场状态(盘前/盘中/盘后/休市 · ET 含 DST)+ 道指/纳指/标普/罗素指数。",
)
async def get_us_overview(ch: ClickHouseDep) -> MarketHomeOverview:
    indices = await select_latest_indices(
        ch._client, market="us", order=US_INDEX_ORDER,  # noqa: SLF001
    )
    now = datetime.now(tz=UTC)
    data_as_of = max((q.ts for q in indices), default=None)
    status = compute_market_status("us", now_utc=now, data_as_of=data_as_of)
    return MarketHomeOverview(market="us", status=status, indices=indices)
