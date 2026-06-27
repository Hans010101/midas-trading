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
    """守卫 → 选币(口径 b)→ 两条都起草存后台 → 只标 rows[0] 为自动发目标(频率调整)。

    ★每轮 2 条都起草+截图+过门禁存后台(待补发素材);只有【rows[0]:|change| 最大那条】进自动发布,
      且须 门禁通过 + 非 6h 重复(理解A:只看第 1 条,它被挡 → 整轮不自动发,不顺延第 2 条)。
    返回 {"status":"ok","drafted":[(id,sym) 全部·供截图],"auto_publish":(id,sym)|None·唯一自动发}。
    任一守卫不过 / 无候选 → {"status":"skip","reason":...}。
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

    # 选币(口径 b · |change| 降序)· 取 min(每轮上限, 日剩余)
    items = await _read_snapshot_items(redis)
    contexts = pick_auto_contexts(items, limit=min(_MAX_PER_ROUND, remaining))
    if not contexts:
        return {"status": "skip", "reason": "no_candidates"}

    # ★两条都起草存后台(不在起草层去重)· auto_drafted=True(待补发素材 + 计入日配额)
    rows = await generate_and_store(session, contexts, generated_by=None, auto_drafted=True)
    drafted = [(r.id, r.symbol) for r in rows]  # 全部供截图

    # ★只 rows[0](|change| 最大)进自动发布 · 门禁过 + 非 6h 重复(理解A:只看第 1 条,不顺延)
    # ★诊断:None 必带原因(门禁未过 / 6h 去重命中 / 无行)· 否则无法区分「理解A 正确跳过」和 bug。
    target: tuple[int, str] | None = None
    skip_reason: str | None = None
    head = rows[0] if rows else None
    if head is None:
        skip_reason = "无起草行"
    elif not head.compliance_passed:
        skip_reason = f"rows[0]={head.symbol} 门禁未过 → 不自动发(不顺延第2条)"
    elif await auto_guard.is_recently_published(redis, head.symbol):
        skip_reason = f"rows[0]={head.symbol} 命中6h去重 → 理解A 本轮跳过(不顺延第2条)"
    else:
        target = (head.id, head.symbol)
    logger.info(
        "[x-auto] 自动起草 · 起草 %d · %s",
        len(rows),
        f"自动发 rows[0]={target[1]}" if target else f"不自动发 · {skip_reason}",
    )
    return {"status": "ok", "drafted": drafted, "auto_publish": target}
