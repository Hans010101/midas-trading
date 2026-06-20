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
