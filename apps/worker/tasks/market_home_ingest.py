"""A股 / 美股 市场首页数据采集(0023 阶段③ · 3.1)。

3 个任务:
- market.cn_index_scan       · Sina 大盘指数快照(上证/深成/创业板/沪深300)→ market_index_snapshot
- market.us_index_scan        · yfinance 4 大盘指数(道指/纳指/标普/罗素)→ market_index_snapshot
- market.cn_calendar_refresh  · AKShare 交易日历 → market_trade_calendar(每日刷 · 给状态机判交易日)

调度(celery_config.py):指数采集只在各自交易时段跑(A股日盘 / 美股夜盘 · 错峰)·
交易日历每日开盘前刷一次。

红线:本 worker 只 GET 行情 + INSERT ClickHouse · 永不触碰任何交易/下单接口。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

import clickhouse_connect
from celery import shared_task

from app.core.config import settings
from app.services.clickhouse_market_home import (
    insert_index_snapshots,
    insert_trade_calendar,
)
from app.services.data_sources.cn_source import AKShareCnSource
from app.services.data_sources.us_source import YFinanceUsSource
from app.services.market_home_config import CN_INDEX_CODES, US_INDICES

logger = logging.getLogger(__name__)


async def _get_ch_client() -> Any:
    """建一个 ClickHouse async client · 调用方负责 close · 跟 crypto 采集对齐。

    session_timezone='UTC':否则 tz 写读按 server 本地时区误转(0002 教训)。
    """
    return await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
        settings={"session_timezone": "UTC"},
    )


# ============================================================================
# 1 · A股大盘指数 · 交易时段每 2min
# ============================================================================


@shared_task(name="tasks.market.cn_index_scan")
def cn_index_scan() -> dict[str, Any]:
    return asyncio.run(_cn_index_scan_async())


async def _cn_index_scan_async() -> dict[str, Any]:
    source = AKShareCnSource()
    ch = await _get_ch_client()
    try:
        items = await source.fetch_indices(CN_INDEX_CODES)
        n = await insert_index_snapshots(ch, items)
        logger.info("[market.cn_index_scan] indices written=%d", n)
        return {"written": n}
    finally:
        await ch.close()


# ============================================================================
# 2 · 美股大盘指数 · 夜盘时段每 2min
# ============================================================================


@shared_task(name="tasks.market.us_index_scan")
def us_index_scan() -> dict[str, Any]:
    return asyncio.run(_us_index_scan_async())


async def _us_index_scan_async() -> dict[str, Any]:
    source = YFinanceUsSource()
    ch = await _get_ch_client()
    try:
        items = await source.fetch_indices(US_INDICES)
        n = await insert_index_snapshots(ch, items)
        logger.info("[market.us_index_scan] indices written=%d", n)
        return {"written": n}
    finally:
        await ch.close()


# ============================================================================
# 3 · A股交易日历 · 每日开盘前刷
# ============================================================================


@shared_task(name="tasks.market.cn_calendar_refresh")
def cn_calendar_refresh() -> dict[str, Any]:
    return asyncio.run(_cn_calendar_refresh_async())


async def _cn_calendar_refresh_async() -> dict[str, Any]:
    source = AKShareCnSource()
    ch = await _get_ch_client()
    try:
        days = await source.fetch_trade_calendar()
        # 全量 8797 天没必要 · 状态机只看「今天是不是交易日」· 存近 ±1 年窗口足够。
        today = date.today()  # noqa: DTZ011
        lo = date(today.year - 1, 1, 1)
        hi = date(today.year + 1, 12, 31)
        window = [d for d in days if lo <= d <= hi]
        n = await insert_trade_calendar(ch, market="cn", dates=window)
        logger.info(
            "[market.cn_calendar_refresh] written=%d (upstream total=%d)", n, len(days),
        )
        return {"written": n}
    finally:
        await ch.close()
