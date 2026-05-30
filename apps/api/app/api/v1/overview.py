"""全球指标概览 API · /api/v1/overview(ADR 0035 阶段 A)。

GET /overview/global = 全球核心市场指标(环球指数 / 商品 / 外汇 / 债券 / 加密),按分类分组。
数据流:只读 ClickHouse(market_index_snapshot category!='' + crypto_ticker_24h)·
        实际数据由 Celery worker(tasks.market.global_overview_scan · 每 10min · yfinance)写入,
        加密复用现有 ccxt 采集的 crypto_ticker_24h。

★ 红线:全部 GET · 无任何写动作 · 纯只读展示 · 不涉及交易(地区码非交易市场 · 不可下单)。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.api.deps import ClickHouseDep
from app.schemas.overview import GlobalOverviewResponse, OverviewGroup
from app.services.clickhouse_overview import (
    select_crypto_overview,
    select_latest_overview,
)
from app.services.global_overview_config import (
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    CRYPTO_OVERVIEW,
    OVERVIEW_SYMBOL_ORDER,
)

router = APIRouter(prefix="/overview", tags=["overview"])

_CRYPTO_SYMBOLS = tuple(sym for sym, _ in CRYPTO_OVERVIEW)


@router.get(
    "/global",
    response_model=GlobalOverviewResponse,
    summary="全球核心市场指标概览(环球指数/商品/外汇/债券/加密)",
    description="只读全球指标快照,按分类分组。数据先采进 CH 再展示,~15min 延迟。"
    "纯展示不涉及交易,行情仅供参考。",
)
async def global_overview(ch: ClickHouseDep) -> GlobalOverviewResponse:
    # ch 是 ClickHouseClient 包装层(不暴露通用 query)· 传底层 AsyncClient(沿用 cn.py/us.py 约定)
    yf_items = await select_latest_overview(ch._client)  # noqa: SLF001
    crypto_items = await select_crypto_overview(ch._client, _CRYPTO_SYMBOLS)  # noqa: SLF001
    all_items = [*yf_items, *crypto_items]

    groups: list[OverviewGroup] = []
    for cat in CATEGORY_ORDER:
        items = sorted(
            (it for it in all_items if it.category == cat),
            key=lambda it: OVERVIEW_SYMBOL_ORDER.get(it.symbol, 9999),
        )
        if not items:
            continue
        groups.append(
            OverviewGroup(category=cat, label=CATEGORY_LABELS[cat], items=items),
        )

    return GlobalOverviewResponse(groups=groups, as_of=datetime.now(tz=UTC))
