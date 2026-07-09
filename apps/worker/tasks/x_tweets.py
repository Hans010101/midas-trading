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

from celery import current_app, shared_task, signature
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.clickhouse_client import ClickHouseClient
from app.services.x_marketing.generate import generate_and_store, pick_contexts
from app.services.x_marketing.store import (
    cleanup_expired,
    expire_published_images,
    select_image_paths,
    set_image_path,
)

logger = logging.getLogger(__name__)

_SNAPSHOT_KEY = "boll:snapshot:latest"  # 做T A-1 快照(boll_scan 落 · 本任务只读挑币)
_SHOTS_DIR = Path("/shots")             # x-shooter 写 · api/worker 读的共享卷(compose x_shots)
# ★孤儿清扫竞态保护:截图落盘 → link 回调写 image_path 之间有秒级窗口,刚写的文件
#   还没行引用会被误判孤儿 → 只清 mtime 超 24h 的(窗口秒级·24h 余量绝对安全)。
_ORPHAN_MIN_AGE_S = 24 * 3600


def _unlink_all(paths: list[str]) -> int:
    """删截图文件(本地共享卷)· 单个失败不影响其他(文件可能已不在)· 返回成功数。"""
    removed = 0
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
            removed += 1
        except OSError as exc:  # noqa: PERF203 · 逐个 best-effort
            logger.warning("[x-tweets] 删截图失败 %s · %s", p, exc)
    return removed


def _sweep_orphan_shots(known_paths: set[str]) -> int:
    """★孤儿截图清扫(磁盘治理):/shots 里没有任何行引用的 png 删除。

    ★只清 mtime 超 _ORPHAN_MIN_AGE_S(24h)的——防误删「已落盘但 link 回调还没写
    image_path」的新图(窗口秒级·24h 余量绝对安全)。目录不存在(如本地 dev)→ 0。
    """
    if not _SHOTS_DIR.is_dir():
        return 0
    import time  # noqa: PLC0415 · 只此处用

    now_ts = time.time()
    removed = 0
    for f in _SHOTS_DIR.glob("*.png"):
        try:
            if str(f) in known_paths:
                continue
            if now_ts - f.stat().st_mtime < _ORPHAN_MIN_AGE_S:
                continue  # 太新 · 可能回调在途
            f.unlink(missing_ok=True)
            removed += 1
        except OSError as exc:  # noqa: PERF203 · 逐个 best-effort
            logger.warning("[x-tweets] 孤儿截图清扫失败 %s · %s", f, exc)
    return removed


async def _cleanup() -> dict[str, int]:
    engine = create_async_engine(
        os.environ["DATABASE_URL"], future=True, poolclass=NullPool,
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            paths = await cleanup_expired(session)                 # 超 7 天未发布行(删行+图)
            pub_paths = await expire_published_images(session)     # ★已发布满 30 天(删图留行)
            known = await select_image_paths(session)              # 剩余引用集(孤儿比对基准)
    finally:
        await engine.dispose()
    removed = _unlink_all(paths)
    pub_removed = _unlink_all(pub_paths)
    orphans = _sweep_orphan_shots(known)
    return {
        "image_files": len(paths), "removed": removed,
        "published_images": len(pub_paths), "published_removed": pub_removed,
        "orphans_removed": orphans,
    }


@shared_task(name="tasks.x_tweets.cleanup_expired", max_retries=0)
def cleanup_expired_tweets() -> dict[str, int]:
    """Celery 入口 · 删过期行+图 · ★已发布满 30 天删图留行 · ★/shots 孤儿清扫(磁盘治理)。"""
    stats = asyncio.run(_cleanup())
    logger.info(
        "[x-tweets] 清理 · 过期行图 %d/%d · 已发布过期图 %d/%d · 孤儿 %d",
        stats["image_files"], stats["removed"],
        stats["published_images"], stats["published_removed"], stats["orphans_removed"],
    )
    return stats


async def _generate(
    generated_by: str | None, style: str = "default",
) -> tuple[dict[str, int], list[tuple[int, str]]]:
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
        return {"generated": 0, "passed": 0, "rejected": 0}, []
    contexts = pick_contexts(items)
    # 生成 + 门禁 + 存行(★DeepSeek 慢 · 在 worker 跑;★image_path 先 null,截图异步回填)
    by = UUID(generated_by) if generated_by else None
    engine = create_async_engine(os.environ["DATABASE_URL"], future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    # ★刀2:建 ClickHouse 客户端富化扩数据(做T零碰·CH 建连失败→None→基础字段照常生成)
    try:
        ch: ClickHouseClient | None = await ClickHouseClient.create()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[x-tweets] ClickHouse 建连失败 · 不富化: %s", exc)
        ch = None
    try:
        async with session_maker() as session:
            rows = await generate_and_store(
                session, contexts, generated_by=by, ch=ch, style=style,
            )
            # expire_on_commit=False → 关 session 后 id/symbol 仍可读 · 收集供 enqueue 截图
            targets = [(r.id, r.symbol) for r in rows]
            passed = sum(1 for r in rows if r.compliance_passed)
    finally:
        if ch is not None:
            await ch.close()
        await engine.dispose()
    counts = {"generated": len(targets), "passed": passed, "rejected": len(targets) - passed}
    return counts, targets


def _enqueue_capture(tweet_id: int, symbol: str) -> None:
    """enqueue 截图到 xshot 队列 · link 回调 set_image_path(主 worker 落库)。

    ★best-effort:enqueue 失败仅 log,不影响其他条、不影响文字推文(截图纯增量)。
    ★link 必须显式 queue="celery"(易踩坑):否则被 xshot app 的 task_default_queue=xshot 吞掉,
    主 worker 收不到回调(对齐 backtest.py persist_outcome 的同款修法)。
    """
    try:
        current_app.send_task(
            "xshot.capture",
            args=[tweet_id, symbol],
            queue="xshot",
            link=signature("tasks.x_tweets.set_image_path", queue="celery"),
            expires=300,  # 5min 内没被消费就丢(shooter 没起时不堆积)
        )
    except Exception as exc:  # noqa: BLE001 · enqueue 失败不阻塞
        logger.warning("[x-tweets] enqueue 截图失败 tweet=%s · %s", tweet_id, exc)


@shared_task(name="tasks.x_tweets.generate_daily", max_retries=0)
def generate_daily(generated_by: str | None = None, style: str = "default") -> dict[str, int]:
    """Celery 入口(admin 端点 enqueue)· 选币 → DeepSeek 生成 → 门禁 → 存 x_tweet(止于 draft)。

    存行后逐条 enqueue 截图(xshot 队列 · ★截图 best-effort,失败/shooter 没起不阻塞生成)。
    ★异步:DeepSeek 每币数秒,放 worker 不阻塞 HTTP。★门禁不过也存(后台可见,4b 不发)。零 X 调用。
    ★style(step1 分平台):default=币安广场长文 / x_short=X 短推 · 由 enqueue 传入(默认兼容在途任务)。
    """
    counts, targets = asyncio.run(_generate(generated_by, style))
    for tweet_id, symbol in targets:
        _enqueue_capture(tweet_id, symbol)  # ★截图链路与生成解耦 · 失败隔离
    logger.info("[x-tweets] 生成完成 · %s · enqueue 截图 %d 条", counts, len(targets))
    return counts


async def _set_image_path(tweet_id: int, image_path: str) -> bool:
    engine = create_async_engine(os.environ["DATABASE_URL"], future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            return await set_image_path(session, tweet_id, image_path)
    finally:
        await engine.dispose()


@shared_task(name="tasks.x_tweets.set_image_path", max_retries=0)
def set_image_path_callback(capture_result: dict[str, Any]) -> dict[str, Any]:
    """xshot.capture 的 link 回调(主 worker · celery 队列)· 截图成功则落库 image_path。

    capture_result = {tweet_id, status, path?/error?}(x-shooter 返回 · 作为 link 首参 prepend)。
    ★截图失败(status!=ok)只 log 不落库,推文 image_path 保持 null(面板显占位 · 不阻塞)。
    """
    if capture_result.get("status") != "ok":
        logger.warning("[x-tweets] 截图未成功 · %s", capture_result)
        return capture_result
    tweet_id = int(capture_result["tweet_id"])
    path = str(capture_result["path"])
    ok = asyncio.run(_set_image_path(tweet_id, path))
    logger.info("[x-tweets] 截图落库 tweet=%s path=%s ok=%s", tweet_id, path, ok)
    return capture_result
