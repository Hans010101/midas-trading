"""硬编码年度种子枯竭告警 · Celery beat 每日壳(逻辑在 app.services.econ_calendar.seed_alert)。

仿 system_health.check_disk_space:beat → 建 PG 引擎 + redis → run_check → TG 告警 admin(去抖)。
★纯卫生任务 · 任何异常只 log 不抛 · 绝不因监控任务本身崩 worker。见 seed_alert 模块头口径澄清。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from celery import shared_task
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.services.econ_calendar.seed_alert import SEED_ALERT_MONTHS, run_check

logger = logging.getLogger(__name__)


async def _run(months: float) -> dict[str, Any]:
    engine = create_async_engine(os.environ["DATABASE_URL"], future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    redis = aioredis.from_url(
        os.environ.get("REDIS_URL", settings.redis_url), decode_responses=True,
    )
    try:
        async with session_maker() as session:
            return await run_check(session, redis, months=months)
    finally:
        await redis.aclose()
        await engine.dispose()


@shared_task(name="tasks.monitor.check_seed_depletion")
def check_seed_depletion(months_override: float | None = None) -> dict[str, Any]:
    """Celery 入口(beat 每日)· 查种子 max(ts) → 快枯竭告警 admin(去抖)。

    months_override:验证用——手动 call 时传大值(如 12)让当前种子立即触发,确认 TG 收到;
    beat 不传 → 用默认 SEED_ALERT_MONTHS(3)。★纯卫生任务 · 异常只 log 不抛不崩 worker。
    """
    try:
        return asyncio.run(_run(months_override or SEED_ALERT_MONTHS))
    except Exception:
        logger.exception("check_seed_depletion 执行失败(不阻塞 · 下个 beat 重试)")
        return {"ok": False, "reason": "exception"}
