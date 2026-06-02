"""港股每手股数(board lot)采集 · 下单池扩量 A2(HKEX 官方源 · 每日)。

worker 每日下载港交所官方 ListOfSecurities.xlsx → 解析主板 HKD 普通股(~2406)→
upsert `hk_board_lot` 表。下单按手取整(resolve_hk_board_lot)优先读本表 · 表无回退 18 种子。

★ 红线:只读 HKEX 公开文件 + 写 PG lot 表(下单按手取整的引用数据)· 永不触碰任何交易/下单接口。
每日刷新 → 自动跟港交所改革(如汇丰 400 改了次日自动跟)· A1 已生产实测可达(200/2406/零失败)。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from celery import shared_task
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.hk_board_lot import fetch_hkex_board_lots, upsert_board_lots

logger = logging.getLogger(__name__)


@shared_task(name="tasks.market.hk_board_lot_scan")
def hk_board_lot_scan() -> dict[str, Any]:
    return asyncio.run(_hk_board_lot_scan_async())


async def _hk_board_lot_scan_async() -> dict[str, Any]:
    # 阻塞下载+解析放线程池(项目约定 · 同 chan._analyze_sync)· 不阻塞事件循环
    result = await asyncio.to_thread(fetch_hkex_board_lots)
    if not result.ok:
        # ★ 下载/解析失败:不写库(保留上一份 good · 不让下单池因当日失败而崩)· 记 warning
        logger.warning("[hk_board_lot_scan] HKEX 下载/解析失败,跳过 upsert:%s", result.error)
        return {"ok": False, "error": result.error}

    engine = create_async_engine(
        os.environ["DATABASE_URL"], future=True, poolclass=NullPool,
    )
    try:
        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        async with session_maker() as db:
            n = await upsert_board_lots(db, result.rows)
        logger.info(
            "[hk_board_lot_scan] upsert=%d mainboard_hkd=%d parse_errors=%d updated=%s",
            n, result.mainboard_hkd_count, result.parse_errors, result.updated_as_at,
        )
        return {
            "ok": True,
            "upserted": n,
            "parse_errors": result.parse_errors,
            "updated_as_at": result.updated_as_at,
        }
    finally:
        await engine.dispose()
