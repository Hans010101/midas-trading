"""X 营销自动托管 · 安全护栏 helpers(自动托管 PR-1)。

5 条护栏的状态读写(Redis · 纯函数化便于测):
- 开关:x:auto:enabled(默认 OFF · worker beat 读它决定跑不跑)
- 6h 去重:x:auto:published:{symbol}(TTL 6h · 同币 6h 内不重发)
- 日上限:x:auto:daily_count:{CST date}(30 封顶 · date-stamped 自然跨日重置)
- 时段窗:7:30-22:30 大中华区(CST/UTC+8 · 纯函数 · 时段外不发 → 更像真人、降封号)
- 熔断:x:auto:circuit_open(连续失败触发 · 开 → 停所有自动发)+ 连续失败计数

★全程红线:自动托管只发分析推文,零碰交易引擎(虚拟交易绝不真实下单)。
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from app.services.visit_stats import CN_TZ

# ── 护栏常量(Hans 定 · 不走 env)──────────────────────────────────────
AUTO_DAILY_MAX = 30                  # 自动托管每日发布上限(独立于 TG 200 / 手动 100)
XSHORT_DRAFT_DAILY_MAX = 30          # ★X 短推每日【自动起草】上限 · 独立于币安配额 · 手动发 · 可调
DEDUP_TTL_S = 6 * 3600               # 同 symbol 6h 去重
FAIL_THRESHOLD = 3                   # 连续失败 N 次 → 开熔断(不硬刚,降封号)
_WINDOW_START = time(7, 30)          # 大中华区发布窗起(含)
_WINDOW_END = time(22, 30)           # 大中华区发布窗止(含)

# ── Redis 键 ──────────────────────────────────────────────────────────
_ENABLED = "x:auto:enabled"
_CIRCUIT = "x:auto:circuit_open"
_FAIL = "x:auto:fail_count"
_PENDING = "x:auto:pending_tasks"    # set:排队中的 auto-publish 任务 id(熔断时 revoke)


def _published_key(symbol: str) -> str:
    return f"x:auto:published:{symbol}"


def _daily_key(now: datetime | None = None) -> str:
    d = (now or datetime.now(tz=CN_TZ)).date().isoformat()
    return f"x:auto:daily_count:{d}"


def _xshort_draft_key(now: datetime | None = None) -> str:
    """★X 短推自动起草计数键(step1)· 与币安 _daily_key 完全独立(不共享·不挤占)。"""
    d = (now or datetime.now(tz=CN_TZ)).date().isoformat()
    return f"x:auto:xshort_draft_count:{d}"


# ── ① 开关(默认 OFF)────────────────────────────────────────────────
async def is_enabled(redis: Any) -> bool:
    return bool((await redis.get(_ENABLED)) == "1")


async def set_enabled(redis: Any, enabled: bool) -> None:  # noqa: FBT001
    await redis.set(_ENABLED, "1" if enabled else "0")


# ── ② 时段窗(纯函数 · 7:30-22:30 CST 含两端)────────────────────────
def is_in_publish_window(now: datetime | None = None) -> bool:
    t = (now or datetime.now(tz=CN_TZ)).timetz().replace(tzinfo=None)
    return _WINDOW_START <= t <= _WINDOW_END


# ── ③ 6h 去重 ─────────────────────────────────────────────────────────
async def is_recently_published(redis: Any, symbol: str) -> bool:
    return bool(await redis.get(_published_key(symbol)))


async def mark_published(redis: Any, symbol: str) -> None:
    await redis.set(_published_key(symbol), "1", ex=DEDUP_TTL_S)


# ── ④ 日上限(30 封顶 · date-stamped)──────────────────────────────────
async def daily_remaining(redis: Any, now: datetime | None = None) -> int:
    used = int(await redis.get(_daily_key(now)) or 0)
    return max(0, AUTO_DAILY_MAX - used)


async def incr_daily(redis: Any, now: datetime | None = None) -> None:
    key = _daily_key(now)
    await redis.incr(key)
    await redis.expire(key, 48 * 3600)  # 2 天 TTL 兜底(自然跨日已重置)


# ── ④b ★X 短推自动起草日上限(step1 · 独立配额 · 不与币安共享)────────────────
async def xshort_draft_remaining(redis: Any, now: datetime | None = None) -> int:
    """X 短推每日自动起草剩余额度(独立键 · 不受币安 daily_count/circuit 影响)。"""
    used = int(await redis.get(_xshort_draft_key(now)) or 0)
    return max(0, XSHORT_DRAFT_DAILY_MAX - used)


async def incr_xshort_draft(redis: Any, n: int = 1, now: datetime | None = None) -> None:
    """X 短推起草计数 +n(date-stamped · 2 天 TTL 兜底)· FakeRedis 无 incrby,循环 incr。"""
    key = _xshort_draft_key(now)
    for _ in range(n):
        await redis.incr(key)
    if n > 0:
        await redis.expire(key, 48 * 3600)


# ── ⑤ 熔断 + 连续失败计数 ─────────────────────────────────────────────
async def is_circuit_open(redis: Any) -> bool:
    return bool(await redis.get(_CIRCUIT))


async def open_circuit(redis: Any) -> None:
    await redis.set(_CIRCUIT, "1")


async def close_circuit(redis: Any) -> None:
    await redis.delete(_CIRCUIT)
    await redis.delete(_FAIL)


async def record_fail(redis: Any) -> int:
    """连续失败 +1 · 返回当前连续失败数(达 FAIL_THRESHOLD 由调用方开熔断)。"""
    n = await redis.incr(_FAIL)
    await redis.expire(_FAIL, 48 * 3600)
    return int(n)


async def reset_fail(redis: Any) -> None:
    """发布成功 → 清连续失败计数。"""
    await redis.delete(_FAIL)


# ── 排队任务追踪(熔断 revoke 用)─────────────────────────────────────
async def add_pending_task(redis: Any, task_id: str) -> None:
    await redis.sadd(_PENDING, task_id)
    await redis.expire(_PENDING, 2 * 3600)  # 兜底 TTL · 防 id 永久堆积(任务几分钟内必触发)


async def pop_pending_tasks(redis: Any) -> list[str]:
    """取出并清空所有排队中的 auto-publish 任务 id(熔断时 revoke)。"""
    ids = await redis.smembers(_PENDING)
    if ids:
        await redis.delete(_PENDING)
    return [str(x) for x in ids]


async def remove_pending_task(redis: Any, task_id: str) -> None:
    """auto-publish 任务执行完移除自身 id(保持 pending 集只含真排队中的)。"""
    await redis.srem(_PENDING, task_id)
