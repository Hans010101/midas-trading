"""每日推文清理(X 营销阶段4a · PR-1)· 删 24h 前的 x_tweet 行 + 删对应截图文件。

资源模式对齐 report.cleanup_materials:create_async_engine(NullPool)开 PG session。
★与周报不同:周报靠 OSS lifecycle 删文件;本系统截图存【本地共享卷】,故清理任务【主动 os.remove】。
红线:纯清理 · 无 X API、无发布。
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from celery import shared_task
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.x_marketing.store import cleanup_expired

logger = logging.getLogger(__name__)


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
