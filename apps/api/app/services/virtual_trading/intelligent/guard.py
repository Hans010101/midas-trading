"""智能交易守卫 helpers(智能交易 PR-2)· 开关 + 仓位约束(PR-4 开仓用)。

照搬 managed/guard.py 范式 · 改名 intelligent · 开关 intelligent:enabled(Redis · ★默认 OFF)。
★退出开关/止盈目标不在此(智能交易退出 = ATR止损/2:1止盈/信号反转 · PR-5 定 · 不照搬 managed 的
tp/signal/timeout 开关)。🔴纯虚拟 · 全程零碰引擎撮合。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.models.perp import VirtualPerpPosition

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MAX_PER_ROUND = 5  # ★每轮(单次扫描)最多开 5 个【新】单 · 总活仓数不限(仿 managed)

_ENABLED = "intelligent:enabled"

# ★开仓参数(Hans 可调)· open_scan 每轮读最新 → 即时生效 · 不碰引擎(margin/leverage 是 route 参数)。
#   每单本金(10-10000)· 杠杆(1-20)· 最大总持仓数(到上限不开新 · 智能原本并发不限)· 范围校验在端点。
#   ★杠杆只改保证金/盈亏倍数 · 不改 ATR 止损止盈价(ATR 是纯价格距离 entry∓N×ATR · 不除杠杆)。
_OPEN_MARGIN = "intelligent:open:margin"
DEFAULT_OPEN_MARGIN = Decimal("100")
_OPEN_LEVERAGE = "intelligent:open:leverage"
DEFAULT_OPEN_LEVERAGE = 5
_MAX_POSITIONS = "intelligent:open:max_positions"
DEFAULT_MAX_POSITIONS = 50


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


# ── 开仓参数(margin/leverage/max_positions · open_scan 每轮读 · 即时生效)──
async def get_open_margin(redis: Any) -> Decimal:
    """每单本金(U)· 默认 100 · 范围校验(10-10000)在端点。"""
    raw = await redis.get(_OPEN_MARGIN)
    try:
        return Decimal(raw) if raw is not None else DEFAULT_OPEN_MARGIN
    except (TypeError, ValueError, InvalidOperation):
        return DEFAULT_OPEN_MARGIN


async def set_open_margin(redis: Any, margin: Decimal) -> None:
    """设每单本金 · 调用方校验 10 ≤ margin ≤ 10000。"""
    await redis.set(_OPEN_MARGIN, str(margin))


async def get_open_leverage(redis: Any) -> int:
    """杠杆 · 默认 5 · 范围校验(1-20)在端点 · ★不影响 ATR 止损止盈价(纯价格距离)。"""
    raw = await redis.get(_OPEN_LEVERAGE)
    try:
        return int(raw) if raw is not None else DEFAULT_OPEN_LEVERAGE
    except (TypeError, ValueError):
        return DEFAULT_OPEN_LEVERAGE


async def set_open_leverage(redis: Any, leverage: int) -> None:
    """设杠杆 · 调用方校验 1 ≤ leverage ≤ 20。"""
    await redis.set(_OPEN_LEVERAGE, str(leverage))


async def get_max_positions(redis: Any) -> int:
    """最大总持仓数 · 默认 50 · 到上限不开新(智能原本并发不限)· 校验 > 0 在端点。"""
    raw = await redis.get(_MAX_POSITIONS)
    try:
        return int(raw) if raw is not None else DEFAULT_MAX_POSITIONS
    except (TypeError, ValueError):
        return DEFAULT_MAX_POSITIONS


async def set_max_positions(redis: Any, n: int) -> None:
    """设最大总持仓数 · 调用方校验 n > 0。"""
    await redis.set(_MAX_POSITIONS, str(n))
