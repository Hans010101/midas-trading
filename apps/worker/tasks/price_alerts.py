"""Celery beat · 每 1 分钟扫所有用户自选股,涨跌 ±5% 触发推送 · 0009 § 4。

去重:Redis key `price_alert:{user_id}:{market}:{symbol}` · TTL 300s(5 分钟)
跨用户同标的不共用 key(每用户独立去重)。

价格参考:ClickHouse 日 K 取最近 2 条 close · pct = (current - prev) / prev
"""

from __future__ import annotations

import asyncio
import logging
import os
from decimal import Decimal

from celery import shared_task
from redis import asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.watchlist import WatchlistItem
from app.services.clickhouse_client import ClickHouseClient

logger = logging.getLogger(__name__)

PRICE_ALERT_THRESHOLD = Decimal("5.0")  # ±5%
DEDUP_TTL_SECONDS = 300  # 5 分钟同标的去重


async def _scan_async() -> dict[str, int]:
    """返回 {triggered, skipped_dedup, no_data, scanned}。"""
    db_url = os.environ["DATABASE_URL"]
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    engine = create_async_engine(db_url, future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    redis = aioredis.from_url(redis_url, decode_responses=True)
    ch = await ClickHouseClient.create()

    triggered = 0
    skipped_dedup = 0
    no_data = 0
    scanned = 0

    try:
        async with session_maker() as db:
            # 取所有用户的自选股 · 去重 (user, symbol, market) 三元组
            items = (
                await db.scalars(
                    select(WatchlistItem),
                )
            ).all()

            for item in items:
                scanned += 1
                # 拉最近 2 根日 K(今天 + 昨天)算 pct
                rows = await ch.select_kline(
                    symbol=item.symbol,
                    market=item.market,  # type: ignore[arg-type]
                    period="1d",
                    limit=2,
                )
                if len(rows) < 2:
                    no_data += 1
                    continue
                prev_close = Decimal(str(rows[-2].close))
                curr_close = Decimal(str(rows[-1].close))
                if prev_close == 0:
                    no_data += 1
                    continue
                change_pct = (
                    (curr_close - prev_close) / prev_close * Decimal("100")
                )

                if abs(change_pct) < PRICE_ALERT_THRESHOLD:
                    continue

                # Dedup
                key = (
                    f"price_alert:{item.user_id}:"
                    f"{item.market}:{item.symbol}"
                )
                already = await redis.get(key)
                if already:
                    skipped_dedup += 1
                    continue

                await redis.set(key, "1", ex=DEDUP_TTL_SECONDS)

                # Dispatch via Celery(让 dispatcher 在 worker async ctx 里跑)
                from celery import Celery  # noqa: PLC0415
                celery = Celery(
                    "midas-price-alert", broker=os.environ["CELERY_BROKER_URL"],
                )
                celery.send_task(
                    "tasks.notifications.send_price_anomaly_notification",
                    args=[
                        str(item.user_id),
                        item.symbol,
                        item.market,
                        str(curr_close),
                        str(prev_close),
                        str(change_pct.quantize(Decimal("0.01"))),
                    ],
                )
                triggered += 1
    finally:
        await ch.close()
        await redis.aclose()
        await engine.dispose()

    return {
        "scanned": scanned,
        "triggered": triggered,
        "skipped_dedup": skipped_dedup,
        "no_data": no_data,
    }


@shared_task(name="tasks.price_alerts.scan_price_anomalies")
def scan_price_anomalies() -> dict[str, int]:
    """每 1 分钟扫一次所有用户自选股 · 涨跌 ±5% 触发推送(0009 § 4)。"""
    result = asyncio.run(_scan_async())
    logger.info(
        "[price_alerts] scanned=%d triggered=%d dedup=%d no_data=%d",
        result["scanned"], result["triggered"],
        result["skipped_dedup"], result["no_data"],
    )
    return result
