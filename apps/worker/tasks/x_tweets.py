"""每日推文清理(X 营销阶段4a · PR-1)· 删 24h 前的 x_tweet 行 + 删对应截图文件。

资源模式对齐 report.cleanup_materials:create_async_engine(NullPool)开 PG session。
★与周报不同:周报靠 OSS lifecycle 删文件;本系统截图存【本地共享卷】,故清理任务【主动 os.remove】。
红线:纯清理 · 无 X API、无发布。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any
from uuid import UUID

from celery import shared_task
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.x_marketing.generate import generate_and_store, pick_contexts
from app.services.x_marketing.store import cleanup_expired

logger = logging.getLogger(__name__)

_SNAPSHOT_KEY = "boll:snapshot:latest"  # 做T A-1 快照(boll_scan 落 · 本任务只读挑币)


async def _cleanup() -> tuple[int, int]:
    engine = create_async_engine(
        os.environ["DATABASE_URL"], future=True, poolclass=NullPool,
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            paths = await cleanup_expired(session)
    finally:
        await engine.dispose()
    # ★删截图文件(本地共享卷)· 单个失败不影响其他(文件可能已不在)
    removed = 0
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
            removed += 1
        except OSError as exc:  # noqa: PERF203 · 逐个 best-effort
            logger.warning("[x-tweets] 删截图失败 %s · %s", p, exc)
    return len(paths), removed


@shared_task(name="tasks.x_tweets.cleanup_expired", max_retries=0)
def cleanup_expired_tweets() -> dict[str, int]:
    """Celery 入口 · 每小时删 24h 前的 x_tweet 行 + 删其截图文件。"""
    files, removed = asyncio.run(_cleanup())
    logger.info("[x-tweets] 清理过期推文 · 截图文件 %d 删 %d", files, removed)
    return {"image_files": files, "removed": removed}


async def _generate(generated_by: str | None) -> dict[str, int]:
    # 读 boll 快照(只读)挑币
    redis = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True,
    )
    try:
        raw = await redis.get(_SNAPSHOT_KEY)
    finally:
        await redis.aclose()
    items: list[dict[str, Any]] = json.loads(raw).get("items", []) if raw else []
    if not items:
        logger.warning("[x-tweets] 无 boll 快照 · 跳过生成")
        return {"generated": 0, "passed": 0, "rejected": 0}
    contexts = pick_contexts(items)
    # 生成 + 门禁 + 存行(★DeepSeek 慢 · 在 worker 跑;★image_path 先 null,截图 PR-4)
    by = UUID(generated_by) if generated_by else None
    engine = create_async_engine(os.environ["DATABASE_URL"], future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            return await generate_and_store(session, contexts, generated_by=by)
    finally:
        await engine.dispose()


@shared_task(name="tasks.x_tweets.generate_daily", max_retries=0)
def generate_daily(generated_by: str | None = None) -> dict[str, int]:
    """Celery 入口(admin 端点 enqueue)· 选币 → DeepSeek 生成 → 门禁 → 存 x_tweet(止于 draft)。

    ★异步:DeepSeek 每币数秒,放 worker 不阻塞 HTTP。★门禁不过也存(后台可见,4b 不发)。零 X 调用。
    """
    result = asyncio.run(_generate(generated_by))
    logger.info("[x-tweets] 生成完成 · %s", result)
    return result
