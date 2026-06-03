"""港股行业(板块)采集 · 港股板块 A2(yfinance GICS 行业源 · 周级)。

worker 遍历行情池 ~900 只(CH hk_spot_snapshot 成交额前 900)→ yfinance `.info` 拿 GICS sector →
upsert PG `hk_sector` 表(code→sector 英文)。`/hk/sectors` 端点 join 本表 + spot 聚合成中文板块。

★ 红线:只读行业分类 + 写 PG hk_sector(首页板块展示用)· 永不触碰下单/撮合/余额。
生产实测:50 只 1.94s · 背靠背 180 调用 0 限流 · ~900 只 ≈ 35s(yfinance .info 港 VPS 快且不限流)。
失败(yfinance 全挂)→ collect 返空 → 不 upsert(保留上一份 good · 不让板块因当次失败而崩)。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import clickhouse_connect
from celery import shared_task
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.services.clickhouse_hk_market import select_latest_spot
from app.services.hk_sector import collect_hk_sectors, upsert_hk_sectors

logger = logging.getLogger(__name__)

_POOL_LIMIT = 900  # 行情池(成交额前 N)· 板块聚合的范围(对齐首页 ~900)


@shared_task(name="tasks.market.hk_sector_scan")
def hk_sector_scan() -> dict[str, Any]:
    return asyncio.run(_hk_sector_scan_async())


async def _hk_sector_scan_async() -> dict[str, Any]:
    # 1 · 读行情池 codes(CH · 成交额前 900)
    ch = await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
        settings={"session_timezone": "UTC"},
    )
    try:
        spot = await select_latest_spot(
            ch, sort_by="amount", order="DESC", limit=_POOL_LIMIT,
        )
    finally:
        await ch.close()
    codes = [row.symbol for row in spot]
    if not codes:
        logger.warning("[hk_sector_scan] 行情池空(spot 未采?)· 跳过")
        return {"ok": False, "error": "spot pool empty"}

    # 2 · yfinance .info 拿 sector(阻塞 · 线程池并发经 to_thread)· 失败/空 → 不入该只
    rows = await asyncio.to_thread(collect_hk_sectors, codes)
    if not rows:
        # 全军覆没(yfinance 全挂)→ 不写库,保留上一份 good
        logger.warning("[hk_sector_scan] yfinance sector 全空(%d 只)· 跳过 upsert", len(codes))
        return {"ok": False, "codes": len(codes), "got": 0}

    # 3 · upsert PG hk_sector
    engine = create_async_engine(os.environ["DATABASE_URL"], future=True, poolclass=NullPool)
    try:
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        async with session_maker() as db:
            n = await upsert_hk_sectors(db, rows)
        logger.info(
            "[hk_sector_scan] codes=%d got_sector=%d upserted=%d", len(codes), len(rows), n,
        )
        return {"ok": True, "codes": len(codes), "got": len(rows), "upserted": n}
    finally:
        await engine.dispose()
