"""发布执行(发布层 PR-1)· enqueue(api 侧)+ run_publish(worker 侧核心逻辑)。

★admin 端点 enqueue → worker 异步跑(真 API 慢)→ adapter.publish → 更新台账 + 成功才计频率。
★worker 侧【再硬校验 compliance_passed】(双保险:绝不发未过门禁的,哪怕端点被绕过)。
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from app.models.platform_dispatch import PlatformDispatch
from app.models.x_tweet import XTweet
from app.services.x_marketing.publish.rate_limit import record_post
from app.services.x_marketing.publish.registry import get_adapter
from app.services.x_marketing.publish.store import update_dispatch_result

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_PUBLISH_TASK = "tasks.x_publish.publish"
_celery_client: Any = None


def _client() -> Any:
    global _celery_client
    if _celery_client is None:
        from celery import Celery  # noqa: PLC0415

        broker = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1")
        _celery_client = Celery("midas-api", broker=broker)
    return _celery_client


def enqueue_publish(dispatch_id: int) -> None:
    """admin 端点触发 · enqueue worker 异步发布(真 API 慢,不阻塞 HTTP)· 走 Celery broker。"""
    _client().send_task(_PUBLISH_TASK, args=[dispatch_id])
    logger.info("[x-publish] enqueue 发布 · dispatch=%s", dispatch_id)


def revoke_auto_tasks(task_ids: list[str]) -> int:
    """★紧急熔断:revoke 排队中的 auto-publish Celery 任务(取消未执行的)· 返回 revoke 数。

    ★兜底:auto-publish 任务执行时还会自检开关/熔断(PR-3),即使 revoke 漏了也会 skip,双保险。
    """
    if not task_ids:
        return 0
    ctrl = _client().control
    for tid in task_ids:
        ctrl.revoke(tid)
    logger.info("[x-publish] 熔断 revoke %d 个排队任务", len(task_ids))
    return len(task_ids)


async def run_publish(session: AsyncSession, redis: Any, dispatch_id: int) -> dict[str, Any]:
    """worker 跑:载 dispatch+tweet → adapter.adapt_text → publish → 更新台账(成功计频率)。"""
    dispatch = await session.get(PlatformDispatch, dispatch_id)
    if dispatch is None:
        return {"status": "skip", "reason": "dispatch 不存在"}
    adapter = get_adapter(dispatch.platform)
    if adapter is None or not adapter.enabled:
        await update_dispatch_result(
            session, dispatch_id, status="failed", error="adapter 不可用或未配置",
        )
        return {"status": "failed", "reason": "adapter 不可用"}
    tweet = await session.get(XTweet, dispatch.tweet_id)
    if tweet is None:
        await update_dispatch_result(
            session, dispatch_id, status="failed", error="推文不存在(已清理)",
        )
        return {"status": "failed", "reason": "tweet 不存在"}
    # ★worker 侧再硬校验:绝不发门禁未通过的(双保险)
    if not tweet.compliance_passed:
        await update_dispatch_result(
            session, dispatch_id, status="failed", error="门禁未通过,不可发布",
        )
        logger.warning("[x-publish] 拦截:门禁未过 tweet=%s", tweet.id)
        return {"status": "failed", "reason": "门禁未过"}

    text = adapter.adapt_text(tweet.tweet_text)
    result = await adapter.publish(text=text, image_path=tweet.image_path)
    if result.success:
        await update_dispatch_result(
            session, dispatch_id, status="success",
            platform_post_id=result.platform_post_id, url=result.url,
        )
        await record_post(redis, dispatch.platform)  # ★成功才计入频率(失败不耗配额)
        logger.info(
            "[x-publish] ✓ 发布成功 platform=%s tweet=%s url=%s",
            dispatch.platform, tweet.id, result.url,
        )
        return {"status": "success", "url": result.url}
    await update_dispatch_result(session, dispatch_id, status="failed", error=result.error)
    logger.warning("[x-publish] 发布失败 platform=%s · %s", dispatch.platform, result.error)
    return {"status": "failed", "error": result.error}
