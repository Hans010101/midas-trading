"""铂金用户自助端点(多账户 PR-5a)· 🔴纯虚拟绝不真单。

铂金用户【自助】开/关自己的智能/托管 per-user 开关 + 看自己影子账户的状态/持仓/历史/统计。
独立模块(不被 admin.py import·架构守卫)· 直接 v1 注册 · 挂 PlatinumDep(登录 + is_platinum)。

★★越权防护(结构性杜绝):
  · 端点签名【绝不出现 user_id】(path/body/query)→ FastAPI 无法注入 → A 指定不了 B。
  · 身份一律 me.id(current_user.id · token 反查 · 前端无法伪造)。
  · 影子账户用 ensure_*_for_user(me.id) 推导(绝不收前端 user_id)· 开关 key={me.id}。
  · 看板 WHERE account_id==影子acc.id + 标志 双重收窄 → 天然只返回自己的仓。

★范围:toggle + 只读 status/positions/history/stats(PR-5a)+ ★开仓参数自助调(PR-7b)。
★PR-7b 参数自助(决策 B·只【开仓参数】per-user·user_id=me.id):
  · 智能:open-margin/leverage/max-positions + strategy-params(阈值/6权重/2 ATR 倍数·开仓算分用)
  · 托管:open-margin/leverage/max-positions
  · ★平仓参数(托管 exit 开关/tp_pct)是全局(决策 B)·不下放铂金自助(admin-only)· 影子平仓跟全局。
★复用 admin In/响应 schema + 服务层(guard/_cross_available_margin/unrealized_pnl/stats)· 引擎零碰 ·
  GET 只读不隐式建账户(get_*_user_id_for_user)· 仅 toggle(on) 才 ensure 建账户 · 参数 set 不建账户。
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ClickHouseDep, PlatinumDep
from app.api.v1.intelligent_admin import (
    CapitalIn,
    IntelligentHistoryPage,
    IntelligentPosition,
    IntelligentPositionsPage,
    IntelligentStatus,
    IntelligentToggleIn,
    IntelligentTrade,
    MaxPositionsIn,
    OpenLeverageIn,
    OpenMarginIn,
    StrategyParams,
)
from app.api.v1.managed_admin import (
    BatchCloseResult,
    ManagedHistoryPage,
    ManagedPosition,
    ManagedPositionsPage,
    ManagedStatus,
    ManagedToggleIn,
    ManagedTrade,
    ManualCloseResult,
)
from app.api.v1.perp import make_perp_mark_price_fetcher
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.perp import PerpSide, VirtualPerpPosition
from app.models.virtual import VirtualAccount
from app.services.clickhouse_crypto import select_premium_index_marks
from app.services.virtual_trading import account_admin
from app.services.virtual_trading.intelligent import account as iacc
from app.services.virtual_trading.intelligent import guard as iguard
from app.services.virtual_trading.intelligent import stats as istats
from app.services.virtual_trading.managed import account as macc
from app.services.virtual_trading.managed import guard as mguard
from app.services.virtual_trading.managed.close import (
    close_all_managed_positions,
    close_one_managed_position,
)
from app.services.virtual_trading.managed.stats import ClosedTrade, compute_managed_stats
from app.services.virtual_trading.perp_cross_engine import _cross_available_margin
from app.services.virtual_trading.perp_fees import unrealized_pnl

if TYPE_CHECKING:
    from uuid import UUID

router = APIRouter(prefix="/platinum", tags=["platinum"])

DbDep = Annotated[AsyncSession, Depends(get_db)]

# 智能策略 6 指标(= intelligent_admin._INDICATORS · 域常量稳定)· strategy-params 校验用
_STRAT_INDICATORS = ("boll", "macd", "ma", "rsi", "kdj", "extreme")


# ── 影子账户只读解析(GET 用 · 不隐式建账户 · 未建返 None)─────────────────
async def _intel_shadow_acc(db: AsyncSession, me_id: UUID) -> VirtualAccount | None:
    """某铂金用户的智能影子账户行(只读 · 未建返 None)· 用 me_id 推导,绝不接受前端 user_id。"""
    shadow_uid = await iacc.get_intelligent_user_id_for_user(db, me_id)
    if shadow_uid is None:
        return None
    acc: VirtualAccount | None = await db.scalar(select(VirtualAccount).where(
        VirtualAccount.user_id == shadow_uid,
        VirtualAccount.market == iacc.INTELLIGENT_MARKET,
    ))
    return acc


async def _managed_shadow_acc(db: AsyncSession, me_id: UUID) -> VirtualAccount | None:
    """某铂金用户的托管影子账户行(只读 · 未建返 None)。"""
    shadow_uid = await macc.get_managed_user_id_for_user(db, me_id)
    if shadow_uid is None:
        return None
    acc: VirtualAccount | None = await db.scalar(select(VirtualAccount).where(
        VirtualAccount.user_id == shadow_uid,
        VirtualAccount.market == macc.MANAGED_MARKET,
    ))
    return acc


# ── 智能交易自助(/platinum/intelligent)─────────────────────────────────
async def _intel_status(
    db: AsyncSession, ch: ClickHouseDep, acc: VirtualAccount | None, me_id: UUID,
) -> IntelligentStatus:
    """组装智能影子账户状态(enabled=per-user 开关·参数仍全局·盈亏复用引擎算法·零碰引擎)。"""
    redis = await get_redis()
    enabled = await iguard.is_enabled(redis, me_id)  # ★per-user 开关(key={me_id})
    open_n = await iguard.count_open_positions(db, acc.id) if acc is not None else 0
    # ★PR-7b 开仓参数 per-user(me_id · 决策③缺则回退全局)
    open_margin = await iguard.get_open_margin(redis, me_id)
    open_leverage = await iguard.get_open_leverage(redis, me_id)
    max_positions = await iguard.get_max_positions(redis, me_id)
    account_value = 0.0
    if acc is not None:
        async def _fetch_mark(symbol: str) -> Decimal | None:
            marks = await select_premium_index_marks(ch._client, [symbol])  # noqa: SLF001
            return marks.get(symbol)
        equity, _used, _avail = await _cross_available_margin(db, acc, _fetch_mark)
        account_value = float(equity)
    return IntelligentStatus(
        enabled=enabled,
        account_ready=acc is not None,
        account_value=account_value,
        initial_capital=(
            float(acc.initial_capital) if acc else float(iacc.INTELLIGENT_INITIAL_CAPITAL)
        ),
        cash_balance=float(acc.cash_balance) if acc else 0.0,
        open_positions=open_n,
        open_margin=float(open_margin),
        open_leverage=open_leverage,
        max_positions=max_positions,
    )


@router.get("/intelligent/status", summary="我的智能交易状态(开关/账户/活仓)")
async def my_intelligent_status(
    me: PlatinumDep, db: DbDep, ch: ClickHouseDep,
) -> IntelligentStatus:
    return await _intel_status(db, ch, await _intel_shadow_acc(db, me.id), me.id)


@router.post("/intelligent/toggle", summary="开/关我的智能交易(★唯一写操作 · 开则幂等建影子账户)")
async def my_intelligent_toggle(
    payload: IntelligentToggleIn, me: PlatinumDep, db: DbDep, ch: ClickHouseDep,
) -> IntelligentStatus:
    """★只写自己的 per-user 开关(key={me.id})· enabled=true 时幂等建自己的影子账户。"""
    redis = await get_redis()
    acc: VirtualAccount | None
    if payload.enabled:
        acc = await iacc.ensure_intelligent_account_for_user(db, me.id)
    else:
        acc = await _intel_shadow_acc(db, me.id)  # 关:不建账户
    await iguard.set_enabled(redis, payload.enabled, user_id=me.id)
    return await _intel_status(db, ch, acc, me.id)


@router.get("/intelligent/positions", summary="我的智能交易活仓(含浮盈 + 共振 · 分页)")
async def my_intelligent_positions(
    me: PlatinumDep, db: DbDep, ch: ClickHouseDep, offset: int = 0, limit: int = 100,
) -> IntelligentPositionsPage:
    acc = await _intel_shadow_acc(db, me.id)
    if acc is None:
        return IntelligentPositionsPage(items=[], total=0)
    base_where = (
        VirtualPerpPosition.account_id == acc.id,  # ★只我的影子账户(双重收窄)
        VirtualPerpPosition.intelligent.is_(True),
        VirtualPerpPosition.closed_at.is_(None),
    )
    total = await db.scalar(
        select(func.count()).select_from(VirtualPerpPosition).where(*base_where),
    )
    rows = list(await db.scalars(
        select(VirtualPerpPosition).where(*base_where)
        .order_by(VirtualPerpPosition.opened_at.desc())
        .offset(max(offset, 0)).limit(max(min(limit, 500), 1)),
    ))
    marks = (
        await select_premium_index_marks(ch._client, [r.symbol for r in rows]) if rows else {}  # noqa: SLF001
    )
    out: list[IntelligentPosition] = []
    for r in rows:
        mark = marks.get(r.symbol)
        upnl = unrealized_pnl(r.side, r.entry_price, mark, r.quantity) if mark is not None else None
        margin = r.initial_margin
        out.append(IntelligentPosition(
            id=r.id, symbol=r.symbol, side=r.side.value, leverage=r.leverage,
            entry_price=float(r.entry_price), quantity=float(r.quantity), margin=float(margin),
            opened_at=r.opened_at.isoformat(),
            mark=float(mark) if mark is not None else None,
            unrealized_pnl=float(upnl) if upnl is not None else None,
            unrealized_pct=float(upnl / margin) if upnl is not None and margin > 0 else None,
            stop_price=float(r.intelligent_stop_price) if r.intelligent_stop_price else None,
            tp_price=float(r.intelligent_tp_price) if r.intelligent_tp_price else None,
            signals=r.intelligent_signals,
        ))
    return IntelligentPositionsPage(items=out, total=total or 0)


@router.get("/intelligent/history", summary="我的智能交易历史平仓(分页)")
async def my_intelligent_history(
    me: PlatinumDep, db: DbDep, offset: int = 0, limit: int = 50,
) -> IntelligentHistoryPage:
    acc = await _intel_shadow_acc(db, me.id)
    if acc is None:
        return IntelligentHistoryPage(items=[], total=0)
    base_where = (
        VirtualPerpPosition.account_id == acc.id,
        VirtualPerpPosition.intelligent.is_(True),
        VirtualPerpPosition.closed_at.is_not(None),
    )
    total = await db.scalar(
        select(func.count()).select_from(VirtualPerpPosition).where(*base_where),
    )
    rows = list(await db.scalars(
        select(VirtualPerpPosition).where(*base_where)
        .order_by(VirtualPerpPosition.closed_at.desc())
        .offset(max(offset, 0)).limit(max(min(limit, 200), 1)),
    ))
    out: list[IntelligentTrade] = []
    for r in rows:
        qty = r.quantity or Decimal("1")
        delta = r.realized_pnl / qty if qty > 0 else Decimal("0")
        exit_price = r.entry_price + delta if r.side == PerpSide.LONG else r.entry_price - delta
        margin = r.initial_margin
        hold = int((r.closed_at - r.opened_at).total_seconds()) if r.closed_at else 0
        out.append(IntelligentTrade(
            symbol=r.symbol, side=r.side.value, leverage=r.leverage,
            entry_price=float(r.entry_price), exit_price=float(exit_price), quantity=float(qty),
            pnl_usdt=float(r.realized_pnl),
            pnl_pct=float(r.realized_pnl / margin) if margin > 0 else 0.0,
            close_reason=r.intelligent_close_reason,
            opened_at=r.opened_at.isoformat(),
            closed_at=r.closed_at.isoformat() if r.closed_at else None,
            hold_seconds=hold,
        ))
    return IntelligentHistoryPage(items=out, total=total or 0)


@router.get("/intelligent/stats", summary="我的智能交易前向测试统计")
async def my_intelligent_stats(
    me: PlatinumDep, db: DbDep,
) -> dict[str, float | int | dict[str, int]]:
    acc = await _intel_shadow_acc(db, me.id)
    if acc is None:
        return istats.compute_intelligent_stats([])
    rows = list(await db.scalars(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == acc.id,
            VirtualPerpPosition.intelligent.is_(True),
            VirtualPerpPosition.closed_at.is_not(None),
        ).order_by(VirtualPerpPosition.closed_at.asc()),
    ))
    trades = [
        istats.ClosedIntelligentTrade(
            realized_pnl=r.realized_pnl, close_reason=r.intelligent_close_reason, side=r.side.value,
        )
        for r in rows
    ]
    return istats.compute_intelligent_stats(trades)


# ── 智能交易开仓参数自助(PR-7b · per-user · user_id=me.id · 决策 B 只开仓参数)──────
@router.post("/intelligent/open-margin", summary="设我的智能每单本金(U·10-10000)")
async def my_intelligent_open_margin(
    payload: OpenMarginIn, me: PlatinumDep, db: DbDep, ch: ClickHouseDep,
) -> IntelligentStatus:
    if not (10 <= payload.margin <= 10000):  # noqa: PLR2004
        raise HTTPException(status_code=400, detail="每单本金必须在 10-10000 U")
    await iguard.set_open_margin(await get_redis(), Decimal(str(payload.margin)), user_id=me.id)
    return await _intel_status(db, ch, await _intel_shadow_acc(db, me.id), me.id)


@router.post("/intelligent/open-leverage", summary="设我的智能杠杆(1-20)")
async def my_intelligent_open_leverage(
    payload: OpenLeverageIn, me: PlatinumDep, db: DbDep, ch: ClickHouseDep,
) -> IntelligentStatus:
    if not (1 <= payload.leverage <= 20):  # noqa: PLR2004
        raise HTTPException(status_code=400, detail="杠杆必须在 1-20 倍")
    await iguard.set_open_leverage(await get_redis(), payload.leverage, user_id=me.id)
    return await _intel_status(db, ch, await _intel_shadow_acc(db, me.id), me.id)


@router.post("/intelligent/max-positions", summary="设我的智能最大总持仓数(>0)")
async def my_intelligent_max_positions(
    payload: MaxPositionsIn, me: PlatinumDep, db: DbDep, ch: ClickHouseDep,
) -> IntelligentStatus:
    if payload.max_positions <= 0:
        raise HTTPException(status_code=400, detail="最大总持仓数必须 > 0")
    await iguard.set_max_positions(await get_redis(), payload.max_positions, user_id=me.id)
    return await _intel_status(db, ch, await _intel_shadow_acc(db, me.id), me.id)


async def _my_intel_strategy_params(me_id: UUID) -> StrategyParams:
    redis = await get_redis()
    return StrategyParams(
        threshold=await iguard.get_strategy_threshold(redis, me_id),
        weights=await iguard.get_strategy_weights(redis, me_id),
        atr_stop_mult=await iguard.get_strategy_atr_stop_mult(redis, me_id),
        atr_tp_mult=await iguard.get_strategy_atr_tp_mult(redis, me_id),
    )


@router.get("/intelligent/strategy-params", summary="读我的智能策略参数")
async def my_intelligent_strategy_params(me: PlatinumDep) -> StrategyParams:
    return await _my_intel_strategy_params(me.id)


@router.post("/intelligent/strategy-params", summary="★设我的智能策略参数(per-user)")
async def my_intelligent_set_strategy_params(
    payload: StrategyParams, me: PlatinumDep,
) -> StrategyParams:
    """前向测试迭代调参 · 范围校验后逐项写 per-user key(user_id=me.id)。"""
    if payload.threshold <= 0:
        raise HTTPException(status_code=400, detail="阈值必须 > 0")
    if payload.atr_stop_mult <= 0 or payload.atr_tp_mult <= 0:
        raise HTTPException(status_code=400, detail="ATR 倍数必须 > 0")
    if set(payload.weights) != set(_STRAT_INDICATORS):
        raise HTTPException(status_code=400, detail=f"权重必须含且仅含 {_STRAT_INDICATORS}")
    if any(v < 0 for v in payload.weights.values()):
        raise HTTPException(status_code=400, detail="权重必须 ≥ 0")
    redis = await get_redis()
    await iguard.set_strategy_threshold(redis, payload.threshold, user_id=me.id)
    await iguard.set_strategy_atr_stop_mult(redis, payload.atr_stop_mult, user_id=me.id)
    await iguard.set_strategy_atr_tp_mult(redis, payload.atr_tp_mult, user_id=me.id)
    for ind, v in payload.weights.items():
        await iguard.set_strategy_weight(redis, ind, v, user_id=me.id)
    return await _my_intel_strategy_params(me.id)


# ── 智能交易账户操作自助(reset/capital · PR-7c · 决策④给清零权·前端二次确认)──
@router.post("/intelligent/account/reset", summary="清零我的智能影子账户(删持仓+历史·重置初始)")
async def my_intelligent_reset(
    me: PlatinumDep, db: DbDep, ch: ClickHouseDep,
) -> IntelligentStatus:
    """★只清零我自己的影子账户(ensure 先建)· 删持仓+历史 + cash 重置 · 引擎零碰。"""
    acc = await iacc.ensure_intelligent_account_for_user(db, me.id)
    await account_admin.reset_account(db, acc)
    return await _intel_status(db, ch, acc, me.id)


@router.post("/intelligent/account/capital", summary="改我的智能起始资金(>0·清持仓重来)")
async def my_intelligent_capital(
    payload: CapitalIn, me: PlatinumDep, db: DbDep, ch: ClickHouseDep,
) -> IntelligentStatus:
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="起始资金必须 > 0")
    acc = await iacc.ensure_intelligent_account_for_user(db, me.id)
    await account_admin.set_account_capital(db, acc, Decimal(str(payload.amount)))
    return await _intel_status(db, ch, acc, me.id)


# ── 托管交易自助(/platinum/managed)─────────────────────────────────────
async def _managed_status(
    db: AsyncSession, ch: ClickHouseDep, acc: VirtualAccount | None, me_id: UUID,
) -> ManagedStatus:
    """组装托管影子账户状态(enabled=per-user 开关·退出开关/参数仍全局·盈亏复用引擎·零碰引擎)。"""
    redis = await get_redis()
    enabled = await mguard.is_enabled(redis, me_id)  # ★per-user 开关
    switches = await mguard.get_exit_switches(redis)  # ★平仓参数=全局(决策 B·admin-only)
    tp_pct = await mguard.get_tp_pct(redis)
    # ★PR-7b 开仓参数 per-user(me_id · 决策③缺则回退全局)
    open_margin = await mguard.get_open_margin(redis, me_id)
    open_leverage = await mguard.get_open_leverage(redis, me_id)
    max_positions = await mguard.get_max_positions(redis, me_id)
    account_value = available = occupied = 0.0
    open_n = 0
    if acc is not None:
        open_n = await mguard.count_open_positions(db, acc.id)

        async def _fetch_mark(symbol: str) -> Decimal | None:
            marks = await select_premium_index_marks(ch._client, [symbol])  # noqa: SLF001
            return marks.get(symbol)
        equity, used, avail = await _cross_available_margin(db, acc, _fetch_mark)
        account_value, occupied, available = float(equity), float(used), float(avail)
    return ManagedStatus(
        enabled=enabled,
        account_ready=acc is not None,
        account_value=account_value,
        available_funds=available,
        occupied_margin=occupied,
        cash_balance=float(acc.cash_balance) if acc else 0.0,
        initial_capital=(
            float(acc.initial_capital) if acc else float(macc.MANAGED_INITIAL_CAPITAL)
        ),
        open_positions=open_n,
        exit_tp=switches["tp"],
        exit_signal=switches["signal"],
        exit_timeout=switches["timeout"],
        tp_pct=tp_pct,
        open_margin=float(open_margin),
        open_leverage=open_leverage,
        max_positions=max_positions,
    )


@router.get("/managed/status", summary="我的托管交易状态(开关/账户价值/可用/活仓)")
async def my_managed_status(
    me: PlatinumDep, db: DbDep, ch: ClickHouseDep,
) -> ManagedStatus:
    return await _managed_status(db, ch, await _managed_shadow_acc(db, me.id), me.id)


@router.post("/managed/toggle", summary="开/关我的托管交易(★唯一写操作 · 开则幂等建影子账户)")
async def my_managed_toggle(
    payload: ManagedToggleIn, me: PlatinumDep, db: DbDep, ch: ClickHouseDep,
) -> ManagedStatus:
    """★只写自己的 per-user 开关(key={me.id})· enabled=true 时幂等建自己的影子账户。"""
    redis = await get_redis()
    acc: VirtualAccount | None
    if payload.enabled:
        acc = await macc.ensure_managed_account_for_user(db, me.id)
    else:
        acc = await _managed_shadow_acc(db, me.id)
    await mguard.set_enabled(redis, payload.enabled, user_id=me.id)
    return await _managed_status(db, ch, acc, me.id)


@router.get("/managed/positions", summary="我的托管活仓(含浮盈 · 分页)")
async def my_managed_positions(
    me: PlatinumDep, db: DbDep, ch: ClickHouseDep, offset: int = 0, limit: int = 100,
) -> ManagedPositionsPage:
    acc = await _managed_shadow_acc(db, me.id)
    if acc is None:
        return ManagedPositionsPage(items=[], total=0)
    base_where = (
        VirtualPerpPosition.account_id == acc.id,
        VirtualPerpPosition.managed.is_(True),
        VirtualPerpPosition.closed_at.is_(None),
    )
    total = await db.scalar(
        select(func.count()).select_from(VirtualPerpPosition).where(*base_where),
    )
    rows = list(await db.scalars(
        select(VirtualPerpPosition).where(*base_where)
        .order_by(VirtualPerpPosition.opened_at.desc())
        .offset(max(offset, 0)).limit(max(min(limit, 500), 1)),
    ))
    marks = (
        await select_premium_index_marks(ch._client, [r.symbol for r in rows]) if rows else {}  # noqa: SLF001
    )
    out: list[ManagedPosition] = []
    for r in rows:
        mark = marks.get(r.symbol)
        upnl = (mark - r.entry_price) * r.quantity if mark is not None else None  # 托管恒做多
        margin = r.initial_margin
        out.append(ManagedPosition(
            id=r.id, symbol=r.symbol, leverage=r.leverage, entry_price=float(r.entry_price),
            quantity=float(r.quantity), margin=float(margin), opened_at=r.opened_at.isoformat(),
            mark=float(mark) if mark is not None else None,
            unrealized_pnl=float(upnl) if upnl is not None else None,
            unrealized_pct=float(upnl / margin) if upnl is not None and margin > 0 else None,
            bias=r.last_bias,
        ))
    return ManagedPositionsPage(items=out, total=total or 0)


@router.get("/managed/history", summary="我的托管历史平仓(分页)")
async def my_managed_history(
    me: PlatinumDep, db: DbDep, offset: int = 0, limit: int = 50,
) -> ManagedHistoryPage:
    acc = await _managed_shadow_acc(db, me.id)
    if acc is None:
        return ManagedHistoryPage(items=[], total=0)
    base_where = (
        VirtualPerpPosition.account_id == acc.id,
        VirtualPerpPosition.managed.is_(True),
        VirtualPerpPosition.closed_at.is_not(None),
    )
    total = await db.scalar(
        select(func.count()).select_from(VirtualPerpPosition).where(*base_where),
    )
    rows = list(await db.scalars(
        select(VirtualPerpPosition).where(*base_where)
        .order_by(VirtualPerpPosition.closed_at.desc())
        .offset(max(offset, 0)).limit(max(min(limit, 200), 1)),
    ))
    out: list[ManagedTrade] = []
    for r in rows:
        qty = r.quantity or Decimal("1")
        exit_price = r.entry_price + (r.realized_pnl / qty if qty > 0 else Decimal("0"))
        margin = r.initial_margin
        hold = int((r.closed_at - r.opened_at).total_seconds()) if r.closed_at else 0
        out.append(ManagedTrade(
            symbol=r.symbol, leverage=r.leverage, entry_price=float(r.entry_price),
            exit_price=float(exit_price), quantity=float(qty),
            pnl_usdt=float(r.realized_pnl),
            pnl_pct=float(r.realized_pnl / margin) if margin > 0 else 0.0,
            close_reason=r.managed_close_reason,
            opened_at=r.opened_at.isoformat(),
            closed_at=r.closed_at.isoformat() if r.closed_at else None,
            hold_seconds=hold,
        ))
    return ManagedHistoryPage(items=out, total=total or 0)


@router.get("/managed/stats", summary="我的托管前向测试统计")
async def my_managed_stats(
    me: PlatinumDep, db: DbDep,
) -> dict[str, float | int | dict[str, int]]:
    acc = await _managed_shadow_acc(db, me.id)
    if acc is None:
        return compute_managed_stats([])
    rows = list(await db.scalars(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == acc.id,
            VirtualPerpPosition.managed.is_(True),
            VirtualPerpPosition.closed_at.is_not(None),
        ).order_by(VirtualPerpPosition.closed_at.asc()),
    ))
    trades = [ClosedTrade(realized_pnl=r.realized_pnl, close_reason=r.managed_close_reason)
              for r in rows]
    return compute_managed_stats(trades)


# ── 托管交易开仓参数自助(PR-7b · per-user · ★不含平仓参数 exit/tp_pct·决策 B 全局 admin-only)──
# In schema 复用 intelligent_admin 的 OpenMarginIn/OpenLeverageIn/MaxPositionsIn(body 形状一致)。
@router.post("/managed/open-margin", summary="设我的托管每单本金(U·10-10000)")
async def my_managed_open_margin(
    payload: OpenMarginIn, me: PlatinumDep, db: DbDep, ch: ClickHouseDep,
) -> ManagedStatus:
    if not (10 <= payload.margin <= 10000):  # noqa: PLR2004
        raise HTTPException(status_code=400, detail="每单本金必须在 10-10000 U")
    await mguard.set_open_margin(await get_redis(), Decimal(str(payload.margin)), user_id=me.id)
    return await _managed_status(db, ch, await _managed_shadow_acc(db, me.id), me.id)


@router.post("/managed/open-leverage", summary="设我的托管杠杆(1-20)")
async def my_managed_open_leverage(
    payload: OpenLeverageIn, me: PlatinumDep, db: DbDep, ch: ClickHouseDep,
) -> ManagedStatus:
    if not (1 <= payload.leverage <= 20):  # noqa: PLR2004
        raise HTTPException(status_code=400, detail="杠杆必须在 1-20 倍")
    await mguard.set_open_leverage(await get_redis(), payload.leverage, user_id=me.id)
    return await _managed_status(db, ch, await _managed_shadow_acc(db, me.id), me.id)


@router.post("/managed/max-positions", summary="设我的托管最大总持仓数(>0)")
async def my_managed_max_positions(
    payload: MaxPositionsIn, me: PlatinumDep, db: DbDep, ch: ClickHouseDep,
) -> ManagedStatus:
    if payload.max_positions <= 0:
        raise HTTPException(status_code=400, detail="最大总持仓数必须 > 0")
    await mguard.set_max_positions(await get_redis(), payload.max_positions, user_id=me.id)
    return await _managed_status(db, ch, await _managed_shadow_acc(db, me.id), me.id)


# ── 托管交易账户操作自助(reset/capital · PR-7c · 决策④给清零权·前端二次确认)──
@router.post("/managed/account/reset", summary="清零我的托管影子账户(删持仓+历史·重置初始)")
async def my_managed_reset(me: PlatinumDep, db: DbDep, ch: ClickHouseDep) -> ManagedStatus:
    """★只清零我自己的影子账户(ensure 先建)· 引擎零碰。"""
    acc = await macc.ensure_managed_account_for_user(db, me.id)
    await account_admin.reset_account(db, acc)
    return await _managed_status(db, ch, acc, me.id)


@router.post("/managed/account/capital", summary="改我的托管起始资金(>0·清持仓重来)")
async def my_managed_capital(
    payload: CapitalIn, me: PlatinumDep, db: DbDep, ch: ClickHouseDep,
) -> ManagedStatus:
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="起始资金必须 > 0")
    acc = await macc.ensure_managed_account_for_user(db, me.id)
    await account_admin.set_account_capital(db, acc, Decimal(str(payload.amount)))
    return await _managed_status(db, ch, acc, me.id)


# ── 托管交易平仓自助(手动平/一键平 · PR-7c · ★越权 owner==caller)──────────────
@router.post(
    "/managed/positions/{position_id}/close",
    summary="手动平我的托管活仓(★越权:仓不属我 → not_found)",
)
async def my_managed_close_one(
    position_id: int, me: PlatinumDep, db: DbDep, ch: ClickHouseDep,
) -> ManualCloseResult:
    """★越权:先校验该仓 account_id == 我影子账户(不属我/不存在 → 统一 not_found 不泄露)。"""
    acc = await _managed_shadow_acc(db, me.id)
    pos = await db.get(VirtualPerpPosition, position_id) if acc is not None else None
    if acc is None or pos is None or pos.account_id != acc.id:
        raise HTTPException(status_code=404, detail="not_found")
    fetcher = make_perp_mark_price_fetcher(ch)
    result = await close_one_managed_position(db, fetcher, position_id)
    if result["status"] == "error":
        reason = str(result.get("reason") or "error")
        code = {"not_found": 404, "not_managed": 403, "already_closed": 409}.get(reason, 400)
        raise HTTPException(status_code=code, detail=reason)
    return ManualCloseResult(
        status="ok", symbol=result.get("symbol"), realized_pnl=result.get("realized_pnl"),
    )


@router.post("/managed/positions/close-all", summary="一键平我的托管活仓(★只我影子账户)")
async def my_managed_close_all(
    me: PlatinumDep, db: DbDep, ch: ClickHouseDep,
) -> BatchCloseResult:
    """★account 收窄到我影子账户(close_all 传 account)· 绝不碰全局/别人的仓。"""
    acc = await _managed_shadow_acc(db, me.id)
    if acc is None:
        return BatchCloseResult(status="ok", closed=0, total=0)  # 没影子账户 → 无仓可平
    fetcher = make_perp_mark_price_fetcher(ch)
    result = await close_all_managed_positions(db, fetcher, account=acc)
    return BatchCloseResult(
        status="ok", closed=int(result["closed"]), total=int(result["total"]),
    )
