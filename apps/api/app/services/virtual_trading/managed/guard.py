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

MAX_PARALLEL_POSITIONS = 5  # 每轮最多并行持有的托管仓(Hans 定)

_ENABLED = "managed:enabled"


# ── 开关(默认 OFF · worker beat 读)─────────────────────────────────
async def is_enabled(redis: Any) -> bool:
    return bool((await redis.get(_ENABLED)) == "1")


async def set_enabled(redis: Any, enabled: bool) -> None:  # noqa: FBT001
    await redis.set(_ENABLED, "1" if enabled else "0")


# ── 仓位约束(PR-2 开仓编排用 · 只读 DB)─────────────────────────────
async def count_open_positions(session: AsyncSession, account_id: int) -> int:
    """托管账户当前活仓数(并行 ≤ MAX_PARALLEL_POSITIONS 用)。"""
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
