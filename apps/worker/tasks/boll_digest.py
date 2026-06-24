"""做T 定时全景(体系1 · M2-3a · ★影子模式)· Celery beat 每小时整点跑。

读 A-1 快照(boll:snapshot:latest)→ 按结构倾向分偏多/中性/偏空三组 → 每组按 %B 极端程度取前 5 →
组装「图1」分组全景消息(SYMBOL 超链接详情页)→ ★只 logger.info(影子),【绝不】真发 TG(真发 M2-5)。

★与体系2(boll_scan 边沿影子推送)正交:体系2=状态转换事件流,本体系=定时快照全景。
★只读快照不重算(分类/排序/组装是纯逻辑 · 在 app.services.ai.boll_digest · 可单测)。
🔴 红线:① 影子不真发(无任何 TG send)② 全局安静时段(夜间)跳过 ③ 末尾「· 仅供参考」过门禁。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from celery import shared_task
from redis import asyncio as aioredis

from app.services.ai.boll_digest import build_hourly_digest, is_global_quiet_hour

logger = logging.getLogger(__name__)

_SNAPSHOT_KEY = "boll:snapshot:latest"  # A-1 全量快照(boll_scan 落 · 本任务只读)
_CN_TZ = "Asia/Shanghai"


async def _digest_async() -> dict[str, Any]:
    redis = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )
    try:
        now = datetime.now(tz=UTC)
        # ★全局安静时段(夜间 23–06)跳过 —— M2-3a 全局统一;M2-5 真发再按用户级 quiet_hours
        if is_global_quiet_hour(now):
            logger.info("[boll-hourly-digest] 安静时段(夜间)· 跳过本轮")
            return {"action": "quiet_skip"}
        raw = await redis.get(_SNAPSHOT_KEY)
        if not raw:
            logger.info("[boll-hourly-digest] 无 A-1 快照(boll:snapshot:latest)· 跳过")
            return {"action": "no_snapshot"}
        payload = json.loads(raw)
        items: list[dict[str, Any]] = payload.get("items", [])
        as_of_label = datetime.now(tz=ZoneInfo(_CN_TZ)).strftime("%H:%M")
        msg = build_hourly_digest(items, as_of_label=as_of_label)
        if msg is None:
            logger.info(
                "[boll-hourly-digest] 快照无可分组候选 · 不推(snapshot %d 条)", len(items),
            )
            return {"action": "empty", "snapshot": len(items)}
        # ★影子模式:只打日志,★绝不调 TG 发送 helper(真发 M2-5 才接 dispatch / 订阅广播)
        logger.info(
            "[boll-hourly-digest-shadow] 全景文案(★影子不真发):\n%s", msg,
        )
        return {"action": "shadow_logged", "snapshot": len(items)}
    finally:
        await redis.aclose()


@shared_task(name="tasks.crypto.boll_hourly_digest", max_retries=0)
def boll_hourly_digest() -> dict[str, Any]:
    """每小时整点 · ★影子全景(只 logger 不发 TG)· 读 A-1 快照不重算 · 夜间安静时段跳过。"""
    return asyncio.run(_digest_async())
