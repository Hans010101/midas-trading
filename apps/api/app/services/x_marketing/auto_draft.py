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

    from app.services.clickhouse_client import ClickHouseClient

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
    ch: ClickHouseClient | None = None,
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
    rows = await generate_and_store(
        session, contexts, generated_by=None, auto_drafted=True, ch=ch,
    )
    drafted = [(r.id, r.symbol) for r in rows]  # 全部供截图

    # ★理解B(Hans 定):按 rows 顺序(|change| 降序)找第一个「门禁过 且 6h 内没发过」的 → 只发它。
    #   第1条优先;第1条重复/门禁未过 → 顺延第2条;都不满足 → 不发。★仍只发1条/轮(找到即 break)。
    # ★诊断:逐条记原因,日志说清发了谁 / 为何顺延 / 为何全不发(可观测,不再猜)。
    target: tuple[int, str] | None = None
    notes: list[str] = []
    for idx, r in enumerate(rows):
        if not r.compliance_passed:
            notes.append(f"rows[{idx}]={r.symbol} 门禁未过")
            continue
        if await auto_guard.is_recently_published(redis, r.symbol):
            notes.append(f"rows[{idx}]={r.symbol} 命中6h去重")
            continue
        target = (r.id, r.symbol)
        notes.append(f"→发 rows[{idx}]={r.symbol}")
        break  # ★找到第一个可发的就停 · 仍只发 1 条/轮
    trace = " | ".join(notes) if notes else "无起草行"
    logger.info(
        "[x-auto] 自动起草 · 起草 %d · %s",
        len(rows),
        f"自动发 {target[1]} · {trace}" if target else f"不自动发(全被挡)· {trace}",
    )
    return {"status": "ok", "drafted": drafted, "auto_publish": target}


async def run_auto_draft_xshort(
    session: AsyncSession, redis: Any, *, now: datetime | None = None,
    ch: ClickHouseClient | None = None,
) -> list[tuple[int, str]]:
    """★step1:X 短推【独立】自动起草(自有日配额 · 手动发 · 永不进 auto_publish)。

    与币安 run_auto_draft 完全隔离,是【新增】函数,不改币安红线逻辑一行:
    - 自有配额键 `x:auto:xshort_draft_count`,★不碰币安 daily_count / circuit / auto_publish target。
    - 守卫:is_enabled(总开关 · 共享)+ 时段窗 + 自有 x_short 日配额
      (★不受币安 daily_cap / circuit 影响 · 独立配额避免挤占)。
    - ★★x_short draft 永不自动发布:本函数【不返回 target】,只返回 (id,sym) 供截图;
      x_short 只能人工发(auto_publish.AUTO_PUBLISH_ALLOWED 白名单焊死不含 x · manual-first 不破)。
    - 选币同币安口径 b(每轮 ≤ 2 · 同一快照 → 同批热门币)· gen_style=x_short。

    返回 [(id, symbol)] 供截图;守卫不过 / 无候选 / 无生成行 → []。
    """
    if not await auto_guard.is_enabled(redis):          # 总开关(共享)· 关着 x_short 也不起草
        return []
    if not auto_guard.is_in_publish_window(now):        # 时段窗(与币安同节奏)
        return []
    remaining = await auto_guard.xshort_draft_remaining(redis, now)  # ★独立配额
    if remaining <= 0:
        return []
    items = await _read_snapshot_items(redis)
    contexts = pick_auto_contexts(items, limit=min(_MAX_PER_ROUND, remaining))
    if not contexts:
        return []
    # ★style="x_short" → 短推 prompt + #加密货币 标签 + gen_style=x_short 入库 · auto_drafted=True
    rows = await generate_and_store(
        session, contexts, generated_by=None, auto_drafted=True, ch=ch, style="x_short",
    )
    if not rows:
        return []
    await auto_guard.incr_xshort_draft(redis, len(rows), now)
    logger.info(
        "[x-auto] X 短推自动起草 · %d 条(gen_style=x_short · ★手动发·永不自动发)",
        len(rows),
    )
    return [(r.id, r.symbol) for r in rows]


def merge_xshort_drafted(
    result: dict[str, Any], xs_drafted: list[tuple[int, str]],
) -> dict[str, Any]:
    """把 x_short 起草结果并入币安 run_auto_draft 的 result · ★纯函数(红线边界·可单测)。

    ★★manual-first 锚点:x_short 只进 result["drafted"](供截图)· 【绝不】写 result["auto_publish"]
    (auto_publish 键只由币安 run_auto_draft 设 → auto_draft_scan 排发只发币安 target)。
    币安 skip 但 x_short 有货 → status 提为 "ok" 触发截图分支;★auto_publish 键不碰
    (币安 skip 时本就无该键 → 排发拿到 None → x_short 永不自动发)。空 xs_drafted → result 原样返回。
    """
    if not xs_drafted:
        return result
    result["drafted"] = list(result.get("drafted") or []) + xs_drafted
    if result.get("status") != "ok":
        result["status"] = "ok"
    return result
