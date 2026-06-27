"""X 营销自动托管护栏 helpers(PR-1)单测:开关/时段窗/6h去重/日上限/熔断 · FakeRedis 纯逻辑。

★时段窗边界 7:29→out / 7:30→in / 22:30→in / 22:31→out 钉死(降封号护栏不能错)。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from app.services.visit_stats import CN_TZ
from app.services.x_marketing.publish import auto_guard as ag


class _FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, Any] = {}
        self.sets: dict[str, set[str]] = {}

    async def get(self, k: str) -> Any:
        return self.kv.get(k)

    async def set(self, k: str, v: Any, ex: int | None = None) -> None:  # noqa: ARG002
        self.kv[k] = v

    async def delete(self, k: str) -> None:
        self.kv.pop(k, None)
        self.sets.pop(k, None)

    async def incr(self, k: str) -> int:
        self.kv[k] = int(self.kv.get(k, 0)) + 1
        return self.kv[k]

    async def expire(self, k: str, ttl: int) -> None:
        pass

    async def sadd(self, k: str, v: str) -> None:
        self.sets.setdefault(k, set()).add(v)

    async def smembers(self, k: str) -> set[str]:
        return self.sets.get(k, set())


# ── ① 开关(默认 OFF)──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_enabled_default_off_and_toggle() -> None:
    r = _FakeRedis()
    assert await ag.is_enabled(r) is False  # 默认 OFF
    await ag.set_enabled(r, enabled=True)
    assert await ag.is_enabled(r) is True
    await ag.set_enabled(r, enabled=False)
    assert await ag.is_enabled(r) is False


# ── ② 时段窗(★边界钉死)──────────────────────────────────────────
def _cst(h: int, m: int) -> datetime:
    return datetime(2026, 6, 27, h, m, tzinfo=CN_TZ)


def test_publish_window_boundaries() -> None:
    assert ag.is_in_publish_window(_cst(7, 29)) is False   # 窗前一分 → 不发
    assert ag.is_in_publish_window(_cst(7, 30)) is True    # 窗起(含)
    assert ag.is_in_publish_window(_cst(13, 0)) is True    # 窗内
    assert ag.is_in_publish_window(_cst(22, 30)) is True   # 窗止(含)
    assert ag.is_in_publish_window(_cst(22, 31)) is False  # 窗后一分 → 不发
    assert ag.is_in_publish_window(_cst(3, 0)) is False    # 深夜 → 不发(机器规律=降封号)


# ── ③ 6h 去重 ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_dedup_6h() -> None:
    r = _FakeRedis()
    assert await ag.is_recently_published(r, "BTCUSDT") is False
    await ag.mark_published(r, "BTCUSDT")
    assert await ag.is_recently_published(r, "BTCUSDT") is True
    assert await ag.is_recently_published(r, "ETHUSDT") is False  # 别的币不受影响


# ── ④ 日上限(30 封顶)────────────────────────────────────────────
@pytest.mark.asyncio
async def test_daily_cap() -> None:
    r = _FakeRedis()
    now = _cst(12, 0)
    assert await ag.daily_remaining(r, now) == ag.AUTO_DAILY_MAX  # 30
    for _ in range(ag.AUTO_DAILY_MAX):
        await ag.incr_daily(r, now)
    assert await ag.daily_remaining(r, now) == 0  # 顶到 0
    # 跨日 → 新 key 重置(date-stamped)
    assert await ag.daily_remaining(r, _cst(12, 0).replace(day=28)) == ag.AUTO_DAILY_MAX


# ── ⑤ 熔断 + 连续失败 ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_circuit_and_fail_count() -> None:
    r = _FakeRedis()
    assert await ag.is_circuit_open(r) is False
    # 连续失败累加
    assert await ag.record_fail(r) == 1
    assert await ag.record_fail(r) == 2
    assert await ag.record_fail(r) == ag.FAIL_THRESHOLD  # 3
    await ag.open_circuit(r)
    assert await ag.is_circuit_open(r) is True
    # 关熔断 → 清失败计数
    await ag.close_circuit(r)
    assert await ag.is_circuit_open(r) is False
    assert await ag.record_fail(r) == 1  # 计数已清,从 1 起
    await ag.reset_fail(r)
    assert await ag.record_fail(r) == 1  # 成功 reset 后又从 1


@pytest.mark.asyncio
async def test_pending_task_tracking() -> None:
    r = _FakeRedis()
    await ag.add_pending_task(r, "t1")
    await ag.add_pending_task(r, "t2")
    ids = await ag.pop_pending_tasks(r)
    assert set(ids) == {"t1", "t2"}
    assert await ag.pop_pending_tasks(r) == []  # pop 后清空
