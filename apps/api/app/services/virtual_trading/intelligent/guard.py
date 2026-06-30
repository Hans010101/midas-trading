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
    from uuid import UUID

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

# ★策略参数(Hans 可调·前向测试迭代调)· open/close 每轮读传给 decide(纯函数入参)· 即时生效。
#   阈值 · 6 权重 · ATR 止损/止盈倍数 · 默认对齐 strategy.py 常量。
_STRAT_THRESHOLD = "intelligent:strategy:threshold"
DEFAULT_STRAT_THRESHOLD = 3.0
_STRAT_WEIGHT_PREFIX = "intelligent:strategy:weight_"  # + boll/macd/ma/rsi/kdj/extreme
DEFAULT_STRAT_WEIGHTS: dict[str, float] = {
    "boll": 2.0, "macd": 1.5, "ma": 1.5, "rsi": 1.0, "kdj": 1.0, "extreme": 1.0,
}
_STRAT_ATR_STOP = "intelligent:strategy:atr_stop_mult"
DEFAULT_STRAT_ATR_STOP = 2.0
_STRAT_ATR_TP = "intelligent:strategy:atr_tp_mult"
DEFAULT_STRAT_ATR_TP = 4.0


# ── 开关(默认 OFF · worker beat 读)─────────────────────────────────
# ★铂金多账户(PR-3):user_id=None → 全局 key(现在跑的智能交易 + admin toggle·向后兼容不破)。
#   user_id 给定 → per-用户影子开关 key f"{_ENABLED}:{uid}"(各自独立·与全局互不覆盖)。
#   零迁移(纯 Redis)· 引擎零碰(只活编排层)· ★只 gate 开仓·绝不 gate 平仓(平仓永不被拦)。
def _enabled_key(user_id: UUID | None) -> str:
    return _ENABLED if user_id is None else f"{_ENABLED}:{user_id}"


async def is_enabled(redis: Any, user_id: UUID | None = None) -> bool:
    return bool((await redis.get(_enabled_key(user_id))) == "1")


async def set_enabled(redis: Any, enabled: bool, user_id: UUID | None = None) -> None:  # noqa: FBT001
    await redis.set(_enabled_key(user_id), "1" if enabled else "0")


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


# ── 开仓参数 per-user(PR-7a · margin/leverage/max_positions · open_scan 每轮读)──
# ★user_id=None → 全局 key(现在跑的 + admin·一字不变·向后兼容)。给定 → 先读 per-user key
#   f"{base}:{uid}";★铂金没单独设过 → 回退全局 key 当前值(决策③·非硬默认);均无 → DEFAULT。
# ★只【开仓参数】per-user(open 透 enabled_user_id);平仓参数(close 读 weights/atr)调 getter 不传
#   uid → user_id=None → 全局 key(决策 B·close.py 零改)。set 给 uid 只写 per-user key(不动全局)。
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
    """杠杆 · 默认 5 · 范围校验(1-20)在端点 · ★不影响 ATR 止损止盈价(纯价格距离)。"""
    raw = await _read_param(redis, _OPEN_LEVERAGE, user_id)
    try:
        return int(raw) if raw is not None else DEFAULT_OPEN_LEVERAGE
    except (TypeError, ValueError):
        return DEFAULT_OPEN_LEVERAGE


async def set_open_leverage(redis: Any, leverage: int, user_id: UUID | None = None) -> None:
    """设杠杆 · 调用方校验 1 ≤ leverage ≤ 20。"""
    await redis.set(_param_key(_OPEN_LEVERAGE, user_id), str(leverage))


async def get_max_positions(redis: Any, user_id: UUID | None = None) -> int:
    """最大总持仓数 · 默认 50 · 到上限不开新(智能原本并发不限)· 校验 > 0 在端点。"""
    raw = await _read_param(redis, _MAX_POSITIONS, user_id)
    try:
        return int(raw) if raw is not None else DEFAULT_MAX_POSITIONS
    except (TypeError, ValueError):
        return DEFAULT_MAX_POSITIONS


async def set_max_positions(redis: Any, n: int, user_id: UUID | None = None) -> None:
    """设最大总持仓数 · 调用方校验 n > 0。"""
    await redis.set(_param_key(_MAX_POSITIONS, user_id), str(n))


# ── 策略参数(阈值 / 6 权重 / ATR 倍数 · open/close 每轮读传 decide · 即时生效)──
def _to_float(raw: Any, default: float) -> float:
    try:
        return float(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default


async def get_strategy_threshold(redis: Any, user_id: UUID | None = None) -> float:
    """开仓阈值 · 默认 3.0 · 调用方校验 > 0。"""
    return _to_float(await _read_param(redis, _STRAT_THRESHOLD, user_id), DEFAULT_STRAT_THRESHOLD)


async def set_strategy_threshold(redis: Any, v: float, user_id: UUID | None = None) -> None:
    await redis.set(_param_key(_STRAT_THRESHOLD, user_id), str(v))


async def get_strategy_weights(redis: Any, user_id: UUID | None = None) -> dict[str, float]:
    """6 指标权重 dict · 每个缺则回退全局/默认 · 读 6 个 key。"""
    out: dict[str, float] = {}
    for k, default in DEFAULT_STRAT_WEIGHTS.items():
        out[k] = _to_float(await _read_param(redis, _STRAT_WEIGHT_PREFIX + k, user_id), default)
    return out


async def set_strategy_weight(
    redis: Any, indicator: str, v: float, user_id: UUID | None = None,
) -> None:
    """设单个指标权重 · 调用方校验 indicator ∈ 6 指标 · v ≥ 0。"""
    await redis.set(_param_key(_STRAT_WEIGHT_PREFIX + indicator, user_id), str(v))


async def get_strategy_atr_stop_mult(redis: Any, user_id: UUID | None = None) -> float:
    """ATR 止损倍数 · 默认 2.0 · 调用方校验 > 0。"""
    return _to_float(await _read_param(redis, _STRAT_ATR_STOP, user_id), DEFAULT_STRAT_ATR_STOP)


async def set_strategy_atr_stop_mult(redis: Any, v: float, user_id: UUID | None = None) -> None:
    await redis.set(_param_key(_STRAT_ATR_STOP, user_id), str(v))


async def get_strategy_atr_tp_mult(redis: Any, user_id: UUID | None = None) -> float:
    """ATR 止盈倍数 · 默认 4.0 · 调用方校验 > 0。"""
    return _to_float(await _read_param(redis, _STRAT_ATR_TP, user_id), DEFAULT_STRAT_ATR_TP)


async def set_strategy_atr_tp_mult(redis: Any, v: float, user_id: UUID | None = None) -> None:
    await redis.set(_param_key(_STRAT_ATR_TP, user_id), str(v))
