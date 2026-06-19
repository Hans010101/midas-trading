"""访问统计 flush · Celery beat 每 10 分钟把 Redis 实时计数落库 daily_visit_stat。

资源模式对齐 ai_reflection:asyncio.run(_async) + create_async_engine(NullPool) + aioredis。
读 Redis 今/昨两天(覆盖午夜边界)→ upsert PG(见 app.services.visit_stats.flush_recent_days)。
★ 与采集埋点共用同一 Redis 库:track 端点写 settings.redis_url(默认 db0),
   本任务读 REDIS_URL(compose 同指 redis:6379/0)· 同库才能读到计数。
"""

import asyncio
import logging
import os

from celery import shared_task
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.visit_stats import flush_recent_days

logger = logging.getLogger(__name__)


async def _flush() -> dict[str, tuple[int, int]]:
    engine = create_async_engine(
        os.environ["DATABASE_URL"], future=True, poolclass=NullPool,
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    redis = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )
    try:
        async with session_maker() as session:
            return await flush_recent_days(session, redis)
    finally:
        await redis.aclose()
        await engine.dispose()


@shared_task(name="tasks.visit.flush_visit_stats")
def flush_visit_stats() -> dict[str, list[int]]:
    """Celery 入口 · sync wrapper · 把今/昨 Redis PV/UV 快照 upsert 进 daily_visit_stat。"""
    result = asyncio.run(_flush())
    logger.info("[visit.flush] %s", {k: list(v) for k, v in result.items()})
    return {k: list(v) for k, v in result.items()}
