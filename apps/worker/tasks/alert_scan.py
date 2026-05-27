"""告警规则扫描 worker · 0025 G2b。

beat 每 1 分钟跑一次:遍历所有启用规则 → 按指标分类做频率分层(DP6:价格/技术
每分钟、衍生/全局 5min、市场结构 3min、缠论 30min)→ engine 求值(只读 ClickHouse,
不打实时上游)→ 命中且过 Redis 冷却 → 经 G2a 核心层 dispatch 推送统一 bot。

与 price_alerts(±5% 自选异动)并存(DP13):本任务是【新增并行】扫描,不替代旧任务。
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime

import clickhouse_connect
from celery import shared_task
from redis import asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.alert_rule import AlertRule
from app.services.alerts.engine import evaluate_rule
from app.services.alerts.registry import ScanContext, get_indicator
from app.services.clickhouse_client import ClickHouseClient
from app.services.notifications.dispatcher import dispatch
from app.services.notifications.events import AlertTriggeredEvent

logger = logging.getLogger(__name__)

# DP6 频率分层:指标分类 → 扫描间隔(分钟)。每分钟 beat,按 epoch 分钟整除判定是否「到点」。
_CATEGORY_INTERVAL_MIN: dict[str, int] = {
    "price": 1,
    "volume": 1,
    "technical": 1,
    "market_structure": 3,
    "crypto_deriv": 5,
    "crypto_global": 5,
    "chan": 30,  # 缠论现算重 · 低频(DP6)
}


def _due(category: str, now: datetime) -> bool:
    interval = _CATEGORY_INTERVAL_MIN.get(category, 1)
    return int(now.timestamp() // 60) % interval == 0


async def _get_ch_raw():  # noqa: ANN202
    return await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
        settings={"session_timezone": "UTC"},
    )


@shared_task(name="tasks.alerts.scan_alert_rules")
def scan_alert_rules() -> int:
    return asyncio.run(_scan_async())


async def _scan_async() -> int:
    now = datetime.now(tz=UTC)
    engine = create_async_engine(
        os.environ["DATABASE_URL"], future=True, poolclass=NullPool,
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    redis = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )
    ch = await ClickHouseClient.create()
    raw = await _get_ch_raw()
    triggered = 0
    try:
        ctx = ScanContext(ch=ch, raw=raw)
        async with session_maker() as db:
            result = await db.execute(
                select(AlertRule).where(AlertRule.enabled.is_(True)),
            )
            rules = list(result.scalars().all())
            for rule in rules:
                indicator = get_indicator(rule.indicator)
                if indicator is None or not _due(indicator.category, now):
                    continue
                try:
                    ev = await evaluate_rule(ctx, rule)
                except Exception as e:  # noqa: BLE001 · 单规则失败不致命
                    logger.warning("[alert] rule=%s 求值失败:%s", rule.id, e)
                    continue
                if not ev.triggered or ev.value is None:
                    continue
                # Redis 冷却去重(key 含 rule_id · TTL = rule.cooldown_sec)
                dedup_key = f"alert_rule:{rule.id}"
                if await redis.get(dedup_key):
                    continue
                event = AlertTriggeredEvent(
                    market=rule.market, symbol=rule.symbol,
                    indicator_label=indicator.label, operator=rule.operator,
                    threshold=float(rule.threshold), value=ev.value,
                    unit=indicator.unit,
                )
                disp = await dispatch(db, rule.user_id, event)
                if disp.any_sent:
                    await redis.set(dedup_key, "1", ex=rule.cooldown_sec)
                    triggered += 1
    finally:
        await ch.close()
        await raw.close()
        await redis.aclose()
        await engine.dispose()

    if triggered:
        logger.info("[alert] 本轮触发 %d 条告警", triggered)
    return triggered
