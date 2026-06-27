"""X 营销自动托管 worker 任务(自动托管 PR-2 起草 + PR-3 发布编排)。

- draft_scan(beat 每 15min):守卫+选币+生成+门禁 → 截图 → 2-4min 间隔排发布(追踪 id 供 revoke)。
- publish(到点跑):再过守卫 → 发布 → 成功去重/计数,失败退避(连续 3 次开熔断 + TG 通知 Hans)。

★开关默认 OFF · 起草/发布两层守卫都先查开关,关着时立刻 skip(零起草、零发布)。
★红线:只发分析推文 binance_square,零碰交易引擎(虚拟交易绝不真实下单)。
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Any

from celery import shared_task
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.x_marketing.auto_draft import run_auto_draft
from app.services.x_marketing.auto_publish import notify_circuit_open, run_auto_publish
from app.services.x_marketing.publish import auto_guard

logger = logging.getLogger(__name__)

_MIN_GAP_S = 120  # 发布间隔下限 2min(更像真人 · 降封号)
_MAX_GAP_S = 240  # 发布间隔上限 4min


def _redis() -> Any:
    return aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True,
    )


def _engine() -> Any:
    return create_async_engine(os.environ["DATABASE_URL"], future=True, poolclass=NullPool)


# ── 起草(beat 每 15min)──────────────────────────────────────────────


async def _draft() -> dict[str, Any]:
    redis = _redis()
    engine = _engine()
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            return await run_auto_draft(session, redis)
    finally:
        await redis.aclose()
        await engine.dispose()


async def _track_pending(task_ids: list[str]) -> None:
    redis = _redis()
    try:
        for tid in task_ids:
            await auto_guard.add_pending_task(redis, tid)
    finally:
        await redis.aclose()


def _schedule_publishes(passed: list[tuple[int, str]]) -> list[str]:
    """截图门禁通过的 + 按 2-4min 累积间隔排发布任务 · 返回排队任务 id(供熔断 revoke 追踪)。"""
    from tasks.x_tweets import _enqueue_capture  # noqa: PLC0415

    task_ids: list[str] = []
    delay = 0
    for tweet_id, symbol in passed:
        _enqueue_capture(tweet_id, symbol)  # 截图(best-effort · 发布前 2-4min 给它时间跑完)
        delay += random.randint(_MIN_GAP_S, _MAX_GAP_S)  # noqa: S311  # 累积间隔(非密码学用途)
        res = auto_publish.apply_async(args=[tweet_id, symbol], countdown=delay)
        task_ids.append(res.id)
    return task_ids


@shared_task(name="tasks.x_auto.draft_scan", max_retries=0)
def auto_draft_scan() -> dict[str, Any]:
    """自动起草入口(beat 每 15min)· 守卫不过立刻 skip · 起草门禁通过的 → 截图 + 排发布。"""
    result = asyncio.run(_draft())
    if result.get("status") == "ok":
        passed = result.get("passed", [])
        if passed:
            task_ids = _schedule_publishes(passed)
            asyncio.run(_track_pending(task_ids))
    logger.info("[x-auto] draft_scan · %s", result)
    return result


# ── 发布(到点跑 · 再过守卫)─────────────────────────────────────────


async def _publish_one(tweet_id: int, symbol: str, task_id: str | None) -> dict[str, Any]:
    redis = _redis()
    engine = _engine()
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            result = await run_auto_publish(session, redis, tweet_id=tweet_id, symbol=symbol)
        if result.get("circuit_opened"):
            await notify_circuit_open(int(result.get("fail_count", 0)))
        if task_id:
            await auto_guard.remove_pending_task(redis, task_id)  # 移除自身 id
        return result
    finally:
        await redis.aclose()
        await engine.dispose()


@shared_task(bind=True, name="tasks.x_auto.publish", max_retries=0)
def auto_publish(self: Any, tweet_id: int, symbol: str) -> dict[str, Any]:  # noqa: ANN401
    """单条自动发布(draft_scan 排的 · 到点跑)· 再过守卫 → 发 → 成功去重/计数,失败退避熔断。"""
    result = asyncio.run(_publish_one(tweet_id, symbol, self.request.id))
    logger.info("[x-auto] publish tweet=%s symbol=%s · %s", tweet_id, symbol, result)
    return result
