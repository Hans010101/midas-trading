"""Celery beat · 标准化市场周报生成(每周一 · P1 第一刀)。

每周生成一篇市场周报草稿(status=draft)→ 等 admin 后台人工复核 / 编辑 / 批准。
业务逻辑在 app/services/report/generate.py,本文件只做 Celery sync wrapper + 资源生命周期。

★本刀生成的是【占位内容】(验证「定时生成 → 存草稿 → admin 复核」管道)·
  真正的专业报告 prompt 待【内容设计立项】单独替换。★本刀只生成草稿,不发送(发送是第二刀)。

资源模式对齐 ai_reflection / perp_funding:create_async_engine(NullPool) + ClickHouseClient.create(),
try/finally 关闭。生成失败重试 3 次(2/4/8s 退避)。
"""

from __future__ import annotations

import asyncio
import logging
import os

from celery import shared_task
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.clickhouse_client import ClickHouseClient
from app.services.report.generate import generate_weekly_report_draft
from app.services.report.materials import cleanup_expired_materials

logger = logging.getLogger(__name__)


async def _generate() -> dict[str, object]:
    engine = create_async_engine(
        os.environ["DATABASE_URL"], future=True, poolclass=NullPool,
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    ch: ClickHouseClient | None = None
    try:
        ch = await ClickHouseClient.create()
        async with session_maker() as session:
            report = await generate_weekly_report_draft(session, ch)
        return {"report_id": report.id, "status": report.status, "title": report.title}
    finally:
        if ch is not None:
            await ch.close()
        await engine.dispose()


@shared_task(
    name="tasks.report.generate_weekly_report",
    bind=True,
    max_retries=3,
    default_retry_delay=2,
)
def generate_weekly_report(self):  # type: ignore[no-untyped-def]
    """Celery 入口 · 每周生成一篇周报草稿(占位内容 · 待 admin 复核)。失败重试 3 次。"""
    try:
        result = asyncio.run(_generate())
        logger.info("[report] 周报草稿生成 · %s", result)
        return result
    except Exception as e:  # noqa: BLE001
        logger.warning("[report] 周报生成失败,重试 · %s", e)
        raise self.retry(exc=e, countdown=2 ** self.request.retries) from e


async def _cleanup_materials() -> int:
    engine = create_async_engine(
        os.environ["DATABASE_URL"], future=True, poolclass=NullPool,
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            return await cleanup_expired_materials(session)
    finally:
        await engine.dispose()


@shared_task(name="tasks.report.cleanup_materials")
def cleanup_materials() -> dict[str, int]:
    """Celery 入口 · 每天删 7 天前的 report_material 行(第三刀)。

    ★只清 DB 行;OSS 对象由桶 lifecycle(report-materials/ 7 天)自动过期 · app 不删 OSS。
    """
    deleted = asyncio.run(_cleanup_materials())
    logger.info("[report] 清理过期素材行 · deleted=%d", deleted)
    return {"deleted": deleted}


async def _send_weekly_dispatch() -> dict[str, object]:
    from app.services.report.weekly_dispatch import run_scheduled_dispatch
    from app.services.visit_stats import cn_now

    engine = create_async_engine(
        os.environ["DATABASE_URL"], future=True, poolclass=NullPool,
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            return await run_scheduled_dispatch(session, now=cn_now())
    finally:
        await engine.dispose()


@shared_task(name="tasks.report.send_weekly_dispatch")
def send_weekly_dispatch() -> dict[str, object]:
    """Celery 入口 · 每周日 21:00 CST 定时发送本周成品周报(有上传则发,无则提醒 admin)。"""
    result = asyncio.run(_send_weekly_dispatch())
    logger.info("[weekly] 周报定时发送 · %s", result)
    return result
