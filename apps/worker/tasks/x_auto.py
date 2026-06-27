"""X 营销自动托管 worker 任务(自动托管 PR-2 起草 · PR-3 加发布编排)。

draft_scan:每 15min(挂 boll_scan 后 1min)跑 run_auto_draft(守卫+选币+生成+门禁)→ 截图通过的。
★开关默认 OFF · run_auto_draft 内守卫,关着时立刻 skip(不起草、不烧 LLM)。
★PR-2 止于起草+截图,不发布(自动发布编排 = PR-3)。红线:只发分析推文,零碰交易。
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

from app.services.x_marketing.auto_draft import run_auto_draft

logger = logging.getLogger(__name__)


async def _draft() -> dict[str, Any]:
    redis = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True,
    )
    engine = create_async_engine(os.environ["DATABASE_URL"], future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            return await run_auto_draft(session, redis)
    finally:
        await redis.aclose()
        await engine.dispose()


@shared_task(name="tasks.x_auto.draft_scan", max_retries=0)
def auto_draft_scan() -> dict[str, Any]:
    """自动起草入口(beat 每 15min)· 守卫不过立刻 skip · 起草门禁通过的 → 截图(发布留 PR-3)。"""
    result = asyncio.run(_draft())
    if result.get("status") == "ok":
        # 截图门禁通过的(复用 4a 截图链路 · best-effort)· 发布 = PR-3
        from tasks.x_tweets import _enqueue_capture  # noqa: PLC0415

        for tweet_id, symbol in result.get("passed", []):
            _enqueue_capture(tweet_id, symbol)
    logger.info("[x-auto] draft_scan · %s", result)
    return result
