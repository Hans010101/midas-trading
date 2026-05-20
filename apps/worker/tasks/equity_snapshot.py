"""Celery beat · 每日 23:59:30 给所有激活的子账户写一条 daily equity snapshot。

走每个 user_market 的活仓 + 用 ClickHouse 最新 close 估值。
没拿到价的持仓用 avg_entry_price 兜底(不让快照失败)。
"""

from __future__ import annotations

import asyncio
import logging
import os

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.virtual import SnapshotTrigger, VirtualAccount
from app.services.virtual_trading.equity import snapshot_equity_for_account

logger = logging.getLogger(__name__)


async def _take_daily_snapshots() -> int:
    """遍历所有 virtual_account,每个写一条 daily snapshot。

    返回写入的快照条数。
    """
    db_url = os.environ["DATABASE_URL"]
    # Worker 独立 engine,跑完即丢
    engine = create_async_engine(db_url, future=True, poolclass=NullPool)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    count = 0
    try:
        async with Session() as session:
            accounts = (
                await session.scalars(select(VirtualAccount))
            ).all()

            for acc in accounts:
                # M0 daily snapshot 不带 price_fetcher · 用 avg_entry 兜底估值。
                # 真实最新价会在用户访问 /portfolio 时实时算,不需要每日批拉行情。
                await snapshot_equity_for_account(
                    session,
                    account_id=acc.id,
                    market=acc.market,
                    trigger=SnapshotTrigger.DAILY,
                    price_fetcher=None,
                )
                count += 1

            await session.commit()
    finally:
        await engine.dispose()

    return count


@shared_task(name="tasks.equity_snapshot.take_daily_snapshots")
def take_daily_snapshots() -> dict[str, int]:
    """Celery 入口 · sync wrapper · 跑 async snapshot 函数。"""
    n = asyncio.run(_take_daily_snapshots())
    logger.info("daily snapshot 完成 · 写入 %d 条", n)
    return {"snapshots_written": n}
