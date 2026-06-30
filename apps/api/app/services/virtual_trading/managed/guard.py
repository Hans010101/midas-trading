"""托管交易守卫 helpers(托管交易 PR-1)· 开关 + 仓位约束(PR-2 用)。

- 开关:managed:enabled(Redis · worker beat 读 · ★默认 OFF)· 仿 x:auto 开关范式。
- 仓位约束(PR-2 开仓编排用):并行仓数 ≤ 5 · 同币已持仓跳过(不重复开)。
★纯虚拟 · 全程零碰引擎撮合。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.models.perp import VirtualPerpPosition

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

MAX_PER_ROUND = 5  # ★每轮(单次扫描)最多开 5 个【新】单 · ★总活仓数不限(Hans 定:下轮可继续累积)

_ENABLED = "managed:enabled"

# ★三个平仓条件开关(Hans 补充)· close_scan 每轮读最新 → 改开关即时生效。
#   ★默认开(未设过 = None ≠ "0" = 开)· 显式 set "0" = 关 · 三个全关 = 自动平仓失效(仅手动平)。
_EXIT_TP = "managed:exit:tp"
_EXIT_SIGNAL = "managed:exit:signal"
_EXIT_TIMEOUT = "managed:exit:timeout"
_EXIT_KEYS = {"tp": _EXIT_TP, "signal": _EXIT_SIGNAL, "timeout": _EXIT_TIMEOUT}

# ★止盈目标(盈利%·Hans 补充)· 默认 100(=ROI 100% = 价涨 100%/杠杆)· close_scan 每轮读 → 即时生效。
#   口径 = 盈利%(保证金赚%)· 价涨幅% = 盈利% ÷ 杠杆 · 仅止盈开关开时生效。
_EXIT_TP_PCT = "managed:exit:tp_pct"
DEFAULT_TP_PCT = 100

# ★开仓参数(Hans 可调)· open_scan 每轮读最新 → 即时生效 · 不碰引擎(margin/leverage 是 route 参数)。
#   每单本金(10-10000)· 杠杆(1-20)· 最大总持仓数(到上限不开新)· 范围校验在端点。
_OPEN_MARGIN = "managed:open:margin"
DEFAULT_OPEN_MARGIN = Decimal("100")
_OPEN_LEVERAGE = "managed:open:leverage"
DEFAULT_OPEN_LEVERAGE = 5
_MAX_POSITIONS = "managed:open:max_positions"
DEFAULT_MAX_POSITIONS = 50
# ★PR-8 方向过滤器(托管恒做多·只 allow_long 单开关·OFF=不开新仓)· 缺省 → ON(!= "0")
_ALLOW_LONG = "managed:open:allow_long"


# ── 开关(默认 OFF · worker beat 读)─────────────────────────────────
# ★铂金多账户(PR-3):user_id=None → 全局 key(现在跑的托管交易 + admin toggle·向后兼容不破)。
#   user_id 给定 → per-用户影子开关 key f"{_ENABLED}:{uid}"(各自独立·与全局互不覆盖)。
#   零迁移(纯 Redis)· 引擎零碰(只活编排层)· ★只 gate 开仓·绝不 gate 平仓(平仓永不被拦)。
def _enabled_key(user_id: UUID | None) -> str:
    return _ENABLED if user_id is None else f"{_ENABLED}:{user_id}"


async def is_enabled(redis: Any, user_id: UUID | None = None) -> bool:
    return bool((await redis.get(_enabled_key(user_id))) == "1")


async def set_enabled(redis: Any, enabled: bool, user_id: UUID | None = None) -> None:  # noqa: FBT001
    await redis.set(_enabled_key(user_id), "1" if enabled else "0")


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


# ── 止盈目标(盈利%·默认 100)─────────────────────────────────────────
async def get_tp_pct(redis: Any) -> int:
    """止盈目标(盈利%)· 默认 DEFAULT_TP_PCT(100)· close_scan 每轮读 → 即时生效。"""
    raw = await redis.get(_EXIT_TP_PCT)
    try:
        return int(raw) if raw is not None else DEFAULT_TP_PCT
    except (TypeError, ValueError):
        return DEFAULT_TP_PCT


async def set_tp_pct(redis: Any, pct: int) -> None:
    """设止盈目标(盈利%)· 调用方校验 pct > 0。"""
    await redis.set(_EXIT_TP_PCT, str(pct))


# ── 开仓参数 per-user(PR-7a · margin/leverage/max_positions · open_scan 每轮读)──
# ★user_id=None → 全局 key(现在跑的 + admin·一字不变)。给定 → 先读 per-user key·缺则回退全局
#   当前值(决策③·非硬默认)·均无 → DEFAULT。set 给 uid 只写 per-user key(不动全局)。
# ★只开仓参数 per-user;平仓参数(exit 开关/tp_pct)保持全局不动(决策 B·close.py 零改)。
def _param_key(base: str, user_id: UUID | None) -> str:
    return base if user_id is None else f"{base}:{user_id}"


async def _read_param(redis: Any, base: str, user_id: UUID | None) -> Any:
    """给 uid 先读 per-user key·缺则回退全局 key(决策③)·均无 → None(调用方用 DEFAULT)。"""
    if user_id is not None:
        per_user = await redis.get(f"{base}:{user_id}")
        if per_user is not None:
            return per_user
    return await redis.get(base)


async def get_open_margin(redis: Any, user_id: UUID | None = None) -> Decimal:
    """每单本金(U)· 默认 100 · 范围校验(10-10000)在端点。"""
    raw = await _read_param(redis, _OPEN_MARGIN, user_id)
    try:
        return Decimal(raw) if raw is not None else DEFAULT_OPEN_MARGIN
    except (TypeError, ValueError, InvalidOperation):
        return DEFAULT_OPEN_MARGIN


async def set_open_margin(redis: Any, margin: Decimal, user_id: UUID | None = None) -> None:
    """设每单本金 · 调用方校验 10 ≤ margin ≤ 10000。"""
    await redis.set(_param_key(_OPEN_MARGIN, user_id), str(margin))


async def get_open_leverage(redis: Any, user_id: UUID | None = None) -> int:
    """杠杆 · 默认 5 · 范围校验(1-20)在端点。"""
    raw = await _read_param(redis, _OPEN_LEVERAGE, user_id)
    try:
        return int(raw) if raw is not None else DEFAULT_OPEN_LEVERAGE
    except (TypeError, ValueError):
        return DEFAULT_OPEN_LEVERAGE


async def set_open_leverage(redis: Any, leverage: int, user_id: UUID | None = None) -> None:
    """设杠杆 · 调用方校验 1 ≤ leverage ≤ 20。"""
    await redis.set(_param_key(_OPEN_LEVERAGE, user_id), str(leverage))


async def get_max_positions(redis: Any, user_id: UUID | None = None) -> int:
    """最大总持仓数 · 默认 50 · 到上限不开新(与每轮≤5 并存)· 校验 > 0 在端点。"""
    raw = await _read_param(redis, _MAX_POSITIONS, user_id)
    try:
        return int(raw) if raw is not None else DEFAULT_MAX_POSITIONS
    except (TypeError, ValueError):
        return DEFAULT_MAX_POSITIONS


async def set_max_positions(redis: Any, n: int, user_id: UUID | None = None) -> None:
    """设最大总持仓数 · 调用方校验 n > 0。"""
    await redis.set(_param_key(_MAX_POSITIONS, user_id), str(n))


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


# ── 方向过滤器(PR-8 · 托管恒做多 · 只 allow_long 单开关 · OFF=不开新仓)· ★默认 ON · != "0" ──
# user_id=None → 全局 key;给定 → 先读 per-user 缺则回退全局(决策③)· 从未设过 → ON(现状不变)。
async def get_allow_long(redis: Any, user_id: UUID | None = None) -> bool:
    """允许开多(默认 ON)· 托管恒做多 → OFF=不开新仓 · open 选币循环前判。"""
    return bool((await _read_param(redis, _ALLOW_LONG, user_id)) != "0")


async def set_allow_long(redis: Any, on: bool, user_id: UUID | None = None) -> None:  # noqa: FBT001
    await redis.set(_param_key(_ALLOW_LONG, user_id), "1" if on else "0")
