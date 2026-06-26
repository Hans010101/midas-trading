"""X 营销发布任务(发布层 PR-1)· 消费 admin 端点 enqueue 的发布请求 → 调 adapter 发 → 更新台账。

★admin 端点显式触发才有任务(无 beat、无自动)· run_publish 内再硬校验 compliance_passed(双保险)。
★PR-1 币安 adapter 是 stub(假成功)· PR-2 换真 API。
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

from app.services.x_marketing.publish.dispatch import run_publish

logger = logging.getLogger(__name__)


async def _publish(dispatch_id: int) -> dict[str, Any]:
    redis = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True,
    )
    engine = create_async_engine(os.environ["DATABASE_URL"], future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            return await run_publish(session, redis, dispatch_id)
    finally:
        await redis.aclose()
        await engine.dispose()


@shared_task(name="tasks.x_publish.publish", max_retries=0)
def publish_dispatch(dispatch_id: int) -> dict[str, Any]:
    """Celery 入口(admin 端点 enqueue)· 异步发布到平台 → 更新 platform_dispatch 台账。"""
    result = asyncio.run(_publish(dispatch_id))
    logger.info("[x-publish] 发布任务完成 dispatch=%s · %s", dispatch_id, result)
    return result
