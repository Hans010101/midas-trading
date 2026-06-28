"""托管交易守卫 helpers(托管交易 PR-1)· 开关 + 仓位约束(PR-2 用)。

- 开关:managed:enabled(Redis · worker beat 读 · ★默认 OFF)· 仿 x:auto 开关范式。
- 仓位约束(PR-2 开仓编排用):并行仓数 ≤ 5 · 同币已持仓跳过(不重复开)。
★纯虚拟 · 全程零碰引擎撮合。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.models.perp import VirtualPerpPosition

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MAX_PER_ROUND = 5  # ★每轮(单次扫描)最多开 5 个【新】单 · ★总活仓数不限(Hans 定:下轮可继续累积)

_ENABLED = "managed:enabled"

# ★三个平仓条件开关(Hans 补充)· close_scan 每轮读最新 → 改开关即时生效。
#   ★默认开(未设过 = None ≠ "0" = 开)· 显式 set "0" = 关 · 三个全关 = 自动平仓失效(仅手动平)。
_EXIT_TP = "managed:exit:tp"
_EXIT_SIGNAL = "managed:exit:signal"
_EXIT_TIMEOUT = "managed:exit:timeout"
_EXIT_KEYS = {"tp": _EXIT_TP, "signal": _EXIT_SIGNAL, "timeout": _EXIT_TIMEOUT}


# ── 开关(默认 OFF · worker beat 读)─────────────────────────────────
async def is_enabled(redis: Any) -> bool:
    return bool((await redis.get(_ENABLED)) == "1")


async def set_enabled(redis: Any, enabled: bool) -> None:  # noqa: FBT001
    await redis.set(_ENABLED, "1" if enabled else "0")


# ── 三个平仓条件开关(tp / signal / timeout · 默认开)──────────────────
async def get_exit_switches(redis: Any) -> dict[str, bool]:
    """三平仓条件开关 · ★默认开(未设过 = None ≠ "0")· close_scan 每轮读 → 即时生效。"""
    return {
        "tp": (await redis.get(_EXIT_TP)) != "0",
        "signal": (await redis.get(_EXIT_SIGNAL)) != "0",
        "timeout": (await redis.get(_EXIT_TIMEOUT)) != "0",
    }


async def set_exit_switch(redis: Any, which: str, on: bool) -> None:  # noqa: FBT001
    """设单个平仓条件开关(which ∈ tp/signal/timeout)· 关 = set "0" · 开 = set "1"。"""
    await redis.set(_EXIT_KEYS[which], "1" if on else "0")


# ── 仓位约束(PR-2 开仓编排用 · 只读 DB)─────────────────────────────
async def count_open_positions(session: AsyncSession, account_id: int) -> int:
    """托管账户当前活仓数(★仅状态展示用 · 不再作总上限 · 总数不限)。"""
    n = await session.scalar(
        select(func.count())
        .select_from(VirtualPerpPosition)
        .where(
            VirtualPerpPosition.account_id == account_id,
            VirtualPerpPosition.closed_at.is_(None),
        ),
    )
    return int(n or 0)


async def has_open_position(session: AsyncSession, account_id: int, symbol: str) -> bool:
    """该币是否已有托管活仓(★同币不重复开)。"""
    pos = await session.scalar(
        select(VirtualPerpPosition.id).where(
            VirtualPerpPosition.account_id == account_id,
            VirtualPerpPosition.symbol == symbol,
            VirtualPerpPosition.closed_at.is_(None),
        ),
    )
    return pos is not None
