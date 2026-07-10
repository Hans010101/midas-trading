"""事件日程层 · 每日刷新任务(P0 · 低频:日程提前数月已知)。

三源各自隔离(单源失败不影响其他):fed_json(FOMC)/ bea_json(GDP/PCE)/
rule_seed(LPR·PMI·社融窗口·非农惯例占位 + 统计局/ECB/BOJ 年度种子)。
每源成功 → 写 Redis last-run 键(econ:cal:last_success:{source})= 保鲜监控口径
(★绝不用 max(事件ts) 判 stale——未来时间戳永远假新鲜)。
🔴 红线:纯日程采集 · 零 key · 零交易逻辑(不 import 任何 virtual_trading/conditional)。
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any

from celery import shared_task
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.econ_calendar.fetchers import fetch_bea_events, fetch_fed_events
from app.services.econ_calendar.rules import gen_rule_and_seed_events
from app.services.econ_calendar.store import mark_source_success, upsert_events

logger = logging.getLogger(__name__)


async def _refresh() -> dict[str, int]:
    redis = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True,
    )
    engine = create_async_engine(os.environ["DATABASE_URL"], future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    stats: dict[str, int] = {}
    try:
        async with session_maker() as session:
            # 源1 · Fed calendar.json(FOMC)· 失败隔离
            try:
                fed = await fetch_fed_events()
                # ★0 条仍记成功(拉取/解析没炸),但留 warn:上游格式漂移会呈现为
                #   「新鲜度绿 + 数据静默停更」,这行日志是唯一线索(交叉审 P1-2)
                if not fed:
                    logger.warning("[econ-cal] fed_json 解析 0 条(疑上游格式漂移)")
                stats["fed_json"] = await upsert_events(session, fed)
                await mark_source_success(redis, "fed_json")
            except Exception as exc:  # noqa: BLE001 · 单源失败不影响其他(存量日程仍有效)
                # ★rollback 必须:upsert 在 DB 层失败会把共享 session 打进 aborted 态,
                #   不清掉后两源连坐全挂(违背单源隔离)· 照 perp_cross_liquidation 范式
                await session.rollback()
                logger.warning("[econ-cal] fed_json 刷新失败(存量日程仍有效): %s", exc)
            # 源2 · BEA release_dates.json(GDP/PCE)
            try:
                bea = await fetch_bea_events()
                if not bea:
                    logger.warning("[econ-cal] bea_json 解析 0 条(疑上游格式漂移)")
                stats["bea_json"] = await upsert_events(session, bea)
                await mark_source_success(redis, "bea_json")
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                logger.warning("[econ-cal] bea_json 刷新失败(存量日程仍有效): %s", exc)
            # 源3 · 规则 + 年度种子(零网络 · 理论不会失败,仍隔离防御)
            try:
                rs = gen_rule_and_seed_events(datetime.now(tz=UTC))
                stats["rule_seed"] = await upsert_events(session, rs)
                await mark_source_success(redis, "rule_seed")
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                logger.warning("[econ-cal] rule_seed 生成失败: %s", exc)
    finally:
        await redis.aclose()
        await engine.dispose()
    return stats


@shared_task(name="tasks.econ_calendar.refresh_daily", max_retries=0)
def refresh_daily() -> dict[str, Any]:
    """Celery 入口(beat 每日)· 三源隔离刷新 → upsert → last-run 保鲜键。"""
    stats = asyncio.run(_refresh())
    logger.info("[econ-cal] 日程刷新 · %s", stats)
    return stats
