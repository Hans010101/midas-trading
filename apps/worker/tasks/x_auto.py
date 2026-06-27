"""X 营销自动托管 worker 任务(自动托管 PR-2 起草 + PR-3 发布编排)。

- draft_scan(beat 每 15min):守卫+选币+生成+门禁 → 两条都截图 → ★只排 rows[0] 一条(随机 1-7min)。
- publish(到点跑):再过守卫 → 发布 → 成功去重/计数,失败退避(连续 3 次开熔断 + TG 通知 Hans)。
- ★每轮只自动发 1 条(|change| 最大)· 第 2 条留后台人工补发 · 随机延迟抹除固定分钟机器指纹。

★开关默认 OFF · 起草/发布两层守卫都先查开关,关着时立刻 skip(零起草、零发布)。
★红线:只发分析推文 binance_square,零碰交易引擎(虚拟交易绝不真实下单)。
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
from app.services.x_marketing.auto_publish import (
    notify_circuit_open,
    publish_delay_seconds,
    run_auto_publish,
)
from app.services.x_marketing.publish import auto_guard

logger = logging.getLogger(__name__)


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


def _screenshot_all(drafted: list[tuple[int, str]]) -> None:
    """两条都截图(第 2 条留后台人工补发也要有图)· best-effort。"""
    from tasks.x_tweets import _enqueue_capture  # noqa: PLC0415

    for tweet_id, symbol in drafted:
        _enqueue_capture(tweet_id, symbol)


def _schedule_publish(target: tuple[int, str]) -> str:
    """★只排 1 条自动发布(rows[0])· 随机 1-7min 延迟(抹固定分钟指纹)· 返回任务 id。"""
    tweet_id, symbol = target
    delay = publish_delay_seconds()  # ★每次随机 1-7min · 非配速(不憋信号)
    res = auto_publish.apply_async(args=[tweet_id, symbol], countdown=delay)
    logger.info("[x-auto] 排发布 tweet=%s symbol=%s · 延迟 %ds", tweet_id, symbol, delay)
    return str(res.id)


@shared_task(name="tasks.x_auto.draft_scan", max_retries=0)
def auto_draft_scan() -> dict[str, Any]:
    """自动起草入口(beat 每 15min)· 守卫不过立刻 skip · 两条都截图 · ★只排 rows[0] 一条发布。"""
    result = asyncio.run(_draft())
    if result.get("status") == "ok":
        _screenshot_all(result.get("drafted", []))  # 两条都截图
        target = result.get("auto_publish")  # ★唯一自动发(rows[0] · 可能 None)
        if target:
            task_id = _schedule_publish(tuple(target))
            asyncio.run(_track_pending([task_id]))
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
