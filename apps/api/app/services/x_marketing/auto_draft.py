"""X 营销自动托管 · 自动起草(自动托管 PR-2)。

每 15min(挂 boll_scan 节奏后 1min · worker beat)跑:守卫 → 读快照选币(口径 b)→ 6h 去重 →
generate_and_store(★门禁硬拦在内,不过的不进发布)→ 返回【门禁通过】的行供 worker 截图 + PR-3 排发布。

★起草时守卫(任一不过 → 不起草):① 开关 enabled ② 未熔断 ③ 在时段窗(7:30-22:30 CST)④ 日配额>0。
★门禁硬拦:generate_and_store 内 validate_tweet · 只 compliance_passed 进发布(failed 也存但不发)。
★红线:只起草分析推文,零碰交易引擎(虚拟交易绝不真实下单)。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from app.services.x_marketing.generate import generate_and_store, pick_auto_contexts
from app.services.x_marketing.publish import auto_guard

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_SNAPSHOT_KEY = "boll:snapshot:latest"  # boll_scan 落 · 本任务只读挑币
_MAX_PER_ROUND = 2                      # 每轮最多起草 1-2 条(Hans 定)


async def _read_snapshot_items(redis: Any) -> list[dict[str, Any]]:
    raw = await redis.get(_SNAPSHOT_KEY)
    if not raw:
        return []
    data = json.loads(raw)
    items = data.get("items", []) if isinstance(data, dict) else []
    return items if isinstance(items, list) else []


async def run_auto_draft(
    session: AsyncSession, redis: Any, *, now: datetime | None = None,
) -> dict[str, Any]:
    """守卫 → 选币(口径 b)→ 6h 去重 → 生成+门禁存 → 返回门禁通过的 (id,symbol) 供截图/排发布。

    任一守卫不过 → {"status":"skip","reason":...}(不起草)。无候选 → skip。
    """
    # ★守卫(顺序:开关 → 熔断 → 时段 → 日配额)
    if not await auto_guard.is_enabled(redis):
        return {"status": "skip", "reason": "disabled"}
    if await auto_guard.is_circuit_open(redis):
        return {"status": "skip", "reason": "circuit_open"}
    if not auto_guard.is_in_publish_window(now):
        return {"status": "skip", "reason": "out_of_window"}
    remaining = await auto_guard.daily_remaining(redis, now)
    if remaining <= 0:
        return {"status": "skip", "reason": "daily_cap"}

    # 选币(口径 b)· 取 min(每轮上限, 日剩余)
    items = await _read_snapshot_items(redis)
    contexts = pick_auto_contexts(items, limit=min(_MAX_PER_ROUND, remaining))
    # ★6h 去重:近 6h 发过的 symbol 不再起草(省 LLM + 防同币刷屏)
    fresh = [c for c in contexts if not await auto_guard.is_recently_published(redis, c.symbol)]
    if not fresh:
        return {"status": "skip", "reason": "no_candidates"}

    # ★生成 + 门禁(generate_and_store 内 validate_tweet)· 门禁不过的也存但不进发布
    rows = await generate_and_store(session, fresh, generated_by=None)
    passed = [(r.id, r.symbol) for r in rows if r.compliance_passed]
    logger.info(
        "[x-auto] 自动起草 · 候选 %d 起草 %d 门禁通过 %d",
        len(fresh), len(rows), len(passed),
    )
    return {"status": "ok", "drafted": len(rows), "passed": passed}
