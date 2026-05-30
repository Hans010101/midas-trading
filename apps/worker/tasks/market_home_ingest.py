"""A股 / 美股 市场首页数据采集(0023 阶段③ · 3.1)。

5 个任务:
- market.cn_index_scan       · Sina 大盘指数快照(上证/深成/创业板/沪深300)→ market_index_snapshot
- market.us_index_scan        · yfinance 4 大盘指数(道指/纳指/标普/罗素)→ market_index_snapshot
- market.cn_calendar_refresh  · AKShare 交易日历 → market_trade_calendar(每日刷 · 给状态机判交易日)
- market.cn_board_scan        · Sina 全市场 spot → cn_spot_snapshot + cn_market_breadth(情绪)·
                                Sina 行业板块 → cn_sector_snapshot(0023 阶段③ · 3.2)
- market.us_board_scan        · yfinance 批量拉策展池 → us_spot_snapshot + us_sector_snapshot
                                (行业 + 中概股板块)(0023 阶段③ · 3.3 · 决策⑥ 策展池)

调度(celery_config.py):指数/榜单采集只在各自交易时段跑(A股日盘 / 美股夜盘 · 错峰)·
交易日历每日开盘前刷一次。

红线:本 worker 只 GET 行情 + INSERT ClickHouse · 永不触碰任何交易/下单接口。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime
from typing import Any

import clickhouse_connect
from celery import shared_task

from app.core.config import settings
from app.services.clickhouse_cn_market import (
    insert_breadth,
    insert_sectors,
    insert_spot_snapshot,
)
from app.services.clickhouse_market_home import (
    insert_index_snapshots,
    insert_trade_calendar,
)
from app.services.clickhouse_overview import insert_overview_quotes
from app.services.clickhouse_us_market import insert_us_sectors, insert_us_spot
from app.services.cn_market import aggregate_breadth
from app.services.data_sources.cn_source import AKShareCnSource
from app.services.data_sources.us_source import YFinanceUsSource
from app.services.global_overview_config import GLOBAL_OVERVIEW_YF
from app.services.market_home_config import CN_INDEX_CODES, US_INDICES
from app.services.us_market import aggregate_sectors
from app.services.us_pool import US_POOL

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
# 2b · 全球指标概览 · 每 10min · yfinance(ADR 0035 阶段 A · 加密由 API 读 crypto_ticker_24h)
# ============================================================================


@shared_task(name="tasks.market.global_overview_scan")
def global_overview_scan() -> dict[str, Any]:
    return asyncio.run(_global_overview_scan_async())


async def _global_overview_scan_async() -> dict[str, Any]:
    """yfinance 拉全球指标(指数/商品/外汇/债券)→ market_index_snapshot(category 标记)。

    加密不在此采(复用现有 ccxt 的 crypto_ticker_24h · 由 /overview/global API 读时合并)。
    单个 symbol 失败不致命(fetch_overview_quotes 内部跳过)· 红线:只 GET + INSERT。
    """
    source = YFinanceUsSource()
    ch = await _get_ch_client()
    try:
        items = await source.fetch_overview_quotes(GLOBAL_OVERVIEW_YF)
        n = await insert_overview_quotes(ch, items)
        logger.info("[market.global_overview_scan] overview written=%d", n)
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


# ============================================================================
# 4 · A股榜单 · 全市场 spot 快照 + 情绪条 + 行业板块 · 交易时段每 3min(3.2)
# ============================================================================


@shared_task(name="tasks.market.cn_board_scan")
def cn_board_scan() -> dict[str, Any]:
    return asyncio.run(_cn_board_scan_async())


async def _cn_board_scan_async() -> dict[str, Any]:
    """Sina 全市场 spot → 存快照 + 算情绪条;Sina 行业板块 → 存。

    spot / sectors 都用 Sina(东财 _em 本地不可达 · 跟 3.1 指数同款)· 所有行共享同一扫描 ts。
    板块失败不阻断榜单 / 情绪条(独立 try)。
    """
    source = AKShareCnSource()
    ch = await _get_ch_client()
    try:
        now = datetime.now(tz=UTC)
        rows = await source.fetch_spot_snapshot()
        n_spot = await insert_spot_snapshot(ch, rows, ts=now)
        breadth = aggregate_breadth(rows, ts=now)
        await insert_breadth(ch, breadth)
        try:
            sectors = await source.fetch_sectors()
            n_sec = await insert_sectors(ch, sectors, ts=now)
        except Exception as exc:  # noqa: BLE001 · 板块失败不阻断榜单/情绪条
            logger.warning("[market.cn_board_scan] sectors 失败 · 跳过:%s", exc)
            n_sec = 0
        logger.info(
            "[market.cn_board_scan] spot=%d breadth(up=%d down=%d lu=%d ld=%d) sectors=%d",
            n_spot, breadth.up_count, breadth.down_count,
            breadth.limit_up_count, breadth.limit_down_count, n_sec,
        )
        return {"spot": n_spot, "sectors": n_sec}
    finally:
        await ch.close()


# ============================================================================
# 5 · 美股榜单 · 策展池批量报价 + 行业/中概板块 · 美股时段每 5min(3.3)
# ============================================================================


@shared_task(name="tasks.market.us_board_scan")
def us_board_scan() -> dict[str, Any]:
    return asyncio.run(_us_board_scan_async())


async def _us_board_scan_async() -> dict[str, Any]:
    """yfinance 批量拉策展池 → 存个股快照 + 算板块聚合(行业 + 中概股)→ 存。

    全 yfinance(策展池 · 决策⑥)· 分块错峰避限流(见 us_source._fetch_pool_sync)·
    所有行共享同一扫描 ts。
    """
    source = YFinanceUsSource()
    ch = await _get_ch_client()
    try:
        now = datetime.now(tz=UTC)
        rows = await source.fetch_pool_quotes(US_POOL)
        n_spot = await insert_us_spot(ch, rows, ts=now)
        sectors = aggregate_sectors(rows)
        n_sec = await insert_us_sectors(ch, sectors, ts=now)
        logger.info("[market.us_board_scan] pool=%d sectors=%d", n_spot, n_sec)
        return {"pool": n_spot, "sectors": n_sec}
    finally:
        await ch.close()
