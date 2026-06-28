"""智能交易守卫 helpers(智能交易 PR-2)· 开关 + 仓位约束(PR-4 开仓用)。

照搬 managed/guard.py 范式 · 改名 intelligent · 开关 intelligent:enabled(Redis · ★默认 OFF)。
★退出开关/止盈目标不在此(智能交易退出 = ATR止损/2:1止盈/信号反转 · PR-5 定 · 不照搬 managed 的
tp/signal/timeout 开关)。🔴纯虚拟 · 全程零碰引擎撮合。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.models.perp import VirtualPerpPosition

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MAX_PER_ROUND = 5  # ★每轮(单次扫描)最多开 5 个【新】单 · 总活仓数不限(仿 managed)

_ENABLED = "intelligent:enabled"


# ── 开关(默认 OFF · worker beat 读)─────────────────────────────────
async def is_enabled(redis: Any) -> bool:
    return bool((await redis.get(_ENABLED)) == "1")


async def set_enabled(redis: Any, enabled: bool) -> None:  # noqa: FBT001
    await redis.set(_ENABLED, "1" if enabled else "0")


# ── 仓位约束(PR-4 开仓编排用 · 只读 DB · 智能交易账户)──────────────────
async def count_open_positions(session: AsyncSession, account_id: int) -> int:
    """智能交易账户当前活仓数(状态展示用)。"""
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
    """该币是否已有智能交易活仓(★同币不重复开)。"""
    pos = await session.scalar(
        select(VirtualPerpPosition.id).where(
            VirtualPerpPosition.account_id == account_id,
            VirtualPerpPosition.symbol == symbol,
            VirtualPerpPosition.closed_at.is_(None),
        ),
    )
    return pos is not None
