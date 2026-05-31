"""Celery beat · AI 决策卡 Reflection 回填(每日 · ADR 0036 批次乙 sub-unit B)。

每日跑一次,对 N 天前的 AI 历史判断(ai_analysis_memory · reflected_at IS NULL)
用事后真实价格回填验证(was_correct + actual_return)。业务逻辑在
app/services/ai/reflection.py,本文件只做 Celery sync wrapper + 资源生命周期管理。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:
   ★★ 只读已采 CH 历史价(ClickHouseClient.select_first_kline_at_or_after)·
      绝不打实时上游 —— reflection 读的是采集任务早已落库的历史 K 线。
   - 不碰下单 / 交易 / 撮合(纯验证)。
   - 不改 AI 分析主流程(独立守护任务)。
═══════════════════════════════════════════════════════════════════════════

资源模式对齐 perp_funding:create_async_engine(NullPool) + ClickHouseClient.create(),
try/finally 关闭。reflect_pending 幂等(reflected_at 标记),beat 重触发安全。
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime

from celery import shared_task
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.ai.reflection import reflect_pending
from app.services.clickhouse_client import ClickHouseClient

logger = logging.getLogger(__name__)


async def _reflect() -> dict[str, int]:
    engine = create_async_engine(
        os.environ["DATABASE_URL"], future=True, poolclass=NullPool,
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    ch: ClickHouseClient | None = None
    try:
        # ★ 只读 CH 历史价 · UTC tz(0002 教训 · 跟采集 worker 一致,由 create 内部设)
        ch = await ClickHouseClient.create()
        async with session_maker() as session:
            now = datetime.now(tz=UTC)
            stats = await reflect_pending(session, ch, now=now)
        return {
            "scanned": stats.scanned,
            "reflected": stats.reflected,
            "skipped": stats.skipped,
            "errored": stats.errored,
        }
    finally:
        if ch is not None:
            await ch.close()
        await engine.dispose()


@shared_task(name="tasks.ai.reflect_decisions")
def reflect_decisions_task() -> dict[str, int]:
    """Celery 入口 · sync wrapper · 每日回填 AI 历史决策的实测涨跌验证。"""
    result = asyncio.run(_reflect())
    if result["reflected"] or result["skipped"]:
        logger.info(
            "[ai.reflection] 本轮回填 %d 条(跳过 %d · 异常 %d · 扫描 %d)",
            result["reflected"], result["skipped"], result["errored"], result["scanned"],
        )
    return result
