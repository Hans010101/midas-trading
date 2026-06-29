"""智能交易复盘 worker(智能交易第二期 PR-8)· DeepSeek 复盘生成 + 发送。

🔴旁观分析师:只读已平 intelligent 仓数据 → DeepSeek 分析 → 邮件/TG 发 admin · 绝不碰交易执行。
- daily_review(每天 20:00):日报 · 邮件 + TG(即时看 + 邮箱存档)· 顺带清理 30 天前历史。
- weekly_review(每周六 20:30):周报 · 邮件 · 对比上周。
- monthly_review(每月末 21:00):月报 · 邮件 · ★beat 配 day_of_month=28-31 + 任务内判真月末。
★asyncio.run 范式(Celery 同步 entry · NullPool)· 复用 review_report.dispatch_review。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from celery import shared_task
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.virtual_trading.intelligent.review_report import (
    cleanup_old_reviews,
    dispatch_review,
    is_last_day_of_month,
)
from app.services.visit_stats import cn_now

logger = logging.getLogger(__name__)


async def _run(period: str, channels: set[str], *, cleanup: bool = False) -> dict[str, Any]:
    """共用环境(pg)· 生成 + 发送复盘 · cleanup=True 时顺带删 30 天前历史。"""
    engine = create_async_engine(os.environ["DATABASE_URL"], future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            now = cn_now()
            result = await dispatch_review(session, period, now, channels=channels)
            if cleanup:
                deleted = await cleanup_old_reviews(session, now)
                result["cleaned"] = deleted
            return result
    finally:
        await engine.dispose()


@shared_task(name="tasks.intelligent_review.daily_review", max_retries=0)
def daily_review() -> dict[str, Any]:
    """日报(每天 20:00)· 邮件 + TG · 顺带清理 30 天前历史。"""
    result = asyncio.run(_run("day", {"email", "tg"}, cleanup=True))
    logger.info("[intelligent-review] daily · %s", result)
    return result


@shared_task(name="tasks.intelligent_review.weekly_review", max_retries=0)
def weekly_review() -> dict[str, Any]:
    """周报(每周六 20:30)· 邮件 · 对比上周。"""
    result = asyncio.run(_run("week", {"email"}))
    logger.info("[intelligent-review] weekly · %s", result)
    return result


@shared_task(name="tasks.intelligent_review.monthly_review", max_retries=0)
def monthly_review() -> dict[str, Any]:
    """月报(每月末 21:00)· 邮件 · ★beat 每月 28-31 触发 · 仅真【最后一天】执行,其余 skip。"""
    if not is_last_day_of_month(cn_now()):
        logger.info("[intelligent-review] monthly skip · 非当月最后一天")
        return {"status": "skip", "reason": "not_last_day_of_month"}
    result = asyncio.run(_run("month", {"email"}))
    logger.info("[intelligent-review] monthly · %s", result)
    return result
