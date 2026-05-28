"""Celery beat · 每 1 分钟扫所有用户自选股,涨跌 ±5% 触发推送 · 0009 § 4 / 0028 N1。

🔴 0028 N1 边沿触发(降噪 · DP9 同 alert_scan 一并改):
- Redis state key `price_alert:state:{user}:{market}:{symbol}` 持久态:triggered/not_triggered
- |change_pct| ≥ 5% → "triggered"(否则 "not_triggered")
- 状态机:
  · not_triggered → triggered → **edge fire**(过 quiet/cool 后派发 + 写 state=triggered + 写 cool key)
  · triggered → not_triggered → 状态复位(写 state=not_triggered · 不推)
  · 持续态 → 不操作
- Cool key `price_alert:cool:{user}:{market}:{symbol}` TTL 300s · 仅 edge fire 派发成功时写
- Quiet 拦截(0028 DP10):PriceAnomalyEvent 非豁免,quiet 时段内不派发 + 仍写 state=triggered
  避免每分钟空查;用户离开 quiet 后只有"再次进入 ±5%"才推

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

from app.models.notification import NotificationConfig
from app.models.watchlist import WatchlistItem
from app.services.clickhouse_client import ClickHouseClient
from app.services.notifications.events import PriceAnomalyEvent
from app.services.notifications.quiet import is_in_quiet_now, is_quiet_exempt

logger = logging.getLogger(__name__)

PRICE_ALERT_THRESHOLD = Decimal("5.0")  # ±5%
COOLDOWN_TTL_SECONDS = 300  # 5 分钟同标的 cool 护栏(防 mark 抖动跨阈值反复)


async def _scan_async() -> dict[str, int]:
    """返回 {triggered, skipped_dedup, no_data, scanned}。"""
    db_url = os.environ["DATABASE_URL"]
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    engine = create_async_engine(db_url, future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    redis = aioredis.from_url(redis_url, decode_responses=True)
    ch = await ClickHouseClient.create()

    triggered = 0
    skipped_dedup = 0  # 兼容旧返回字段:含 edge 持续/cool 护栏/quiet 拦截 三种"未派发"
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

                # 0028 N1 边沿触发去重 · curr_state 由 |change_pct| ≥ 5% 决定
                curr_state = (
                    "triggered" if abs(change_pct) >= PRICE_ALERT_THRESHOLD
                    else "not_triggered"
                )
                state_key = (
                    f"price_alert:state:{item.user_id}:"
                    f"{item.market}:{item.symbol}"
                )
                prev_state = await redis.get(state_key)

                # 状态复位:triggered → not_triggered · 写状态不推
                if prev_state == "triggered" and curr_state == "not_triggered":
                    await redis.set(state_key, "not_triggered")
                    continue
                # 持续态(prev==curr,或 prev=None/not_triggered + curr=not_triggered)· 不推
                if curr_state != "triggered" or prev_state == "triggered":
                    continue

                # edge fire 候选:curr=triggered & prev != triggered
                # Quiet 拦截(price_alerts 不走 dispatcher · 自查 quiet)
                event = PriceAnomalyEvent(
                    symbol=item.symbol, market=item.market,
                    current_price=curr_close, reference_price=prev_close,
                    change_pct=change_pct,
                )
                config = await db.scalar(
                    select(NotificationConfig).where(
                        NotificationConfig.user_id == item.user_id,
                    ),
                )
                if not is_quiet_exempt(event) and is_in_quiet_now(config):
                    # quiet 内:写 state 防空转 · 不派
                    await redis.set(state_key, "triggered")
                    skipped_dedup += 1
                    continue

                # Cool 护栏(防 mark 抖动反复跨阈值)
                cool_key = (
                    f"price_alert:cool:{item.user_id}:"
                    f"{item.market}:{item.symbol}"
                )
                if await redis.get(cool_key):
                    skipped_dedup += 1
                    continue

                # 派发 · 走原 celery send_task 路径(链路不改)
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
                # 派发任务入队(异步实际发)· 即视为"已触发":写 state + cool
                # (失败重试由 send_price_anomaly_notification task 自管,无需我们重做 edge)
                await redis.set(state_key, "triggered")
                await redis.set(cool_key, "1", ex=COOLDOWN_TTL_SECONDS)
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
