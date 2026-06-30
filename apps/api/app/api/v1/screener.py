"""选股筛选器端点 · 股票第一批 功能1 · 1a(只读 · POST /screener/{market})。

🔴 红线:返回"符合条件的标的"客观列表 + 免责,**非荐股**;只读不下单。
加密第一批不做(决策4 · 只 cn/us/hk 股票);market path param `Literal` 自动校验。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, status

from app.api.deps import ClickHouseDep
from app.schemas.screener import ScreenerFilters, ScreenerResponse
from app.services import screener

router = APIRouter(prefix="/screener", tags=["screener"])

_MAX_PAGE_SIZE = 50


@router.post("/{market}", response_model=ScreenerResponse)
async def run_stock_screener(
    market: Literal["cn", "us", "hk"],
    filters: ScreenerFilters,
    ch: ClickHouseDep,
    page: int = 1,
    page_size: int = 30,
) -> ScreenerResponse:
    """跑一次股票筛选(cn/us/hk 现货)· 现成条件:价格 / 涨跌幅 / RSI 区间 / 均线多头排列。

    无任何条件 → 422(避免返回全市场)· page / page_size 边界守卫。
    """
    if filters.is_empty():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请至少选择一个筛选条件",
        )
    page = max(1, page)
    page_size = max(1, min(page_size, _MAX_PAGE_SIZE))
    return await screener.run_screener(
        ch,
        ch._client,  # noqa: SLF001 · 端点取 raw AsyncClient(同 analysis.py 范式)
        market=market,
        filters=filters,
        page=page,
        page_size=page_size,
    )
