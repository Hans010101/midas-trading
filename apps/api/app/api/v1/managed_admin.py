"""托管交易(策略前向测试)· admin 端点(托管交易 PR-1)· 🔴纯虚拟绝不真单。

★独立于 api/v1/admin.py:admin 域有架构守卫(test_admin_domain_no_engine_no_login_import 递归扫
admin import 树,禁 import virtual_trading)· 托管端点要 import virtual_trading.managed,故单独成模块,
直接在 v1 router 注册(admin.py 不 import 本模块)· 仍挂 AdminDep(403 边界)。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep, ClickHouseDep
from app.api.v1.perp import make_perp_mark_price_fetcher
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.perp import VirtualPerpPosition
from app.models.user import User
from app.models.virtual import VirtualAccount
from app.services.clickhouse_crypto import select_premium_index_marks
from app.services.virtual_trading import account_admin
from app.services.virtual_trading.managed import account as managed_account
from app.services.virtual_trading.managed import guard as managed_guard
from app.services.virtual_trading.managed.close import (
    close_all_managed_positions,
    close_one_managed_position,
)
from app.services.virtual_trading.managed.stats import ClosedTrade, compute_managed_stats
from app.services.virtual_trading.perp_cross_engine import _cross_available_margin

router = APIRouter(prefix="/admin/managed", tags=["managed"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _managed_account_row(db: AsyncSession) -> VirtualAccount | None:
    acc: VirtualAccount | None = await db.scalar(
        select(VirtualAccount).where(
            VirtualAccount.user_id.in_(
                select(User.id).where(User.email == managed_account.MANAGED_BOT_EMAIL),
            ),
            VirtualAccount.market == managed_account.MANAGED_MARKET,
        ),
    )
    return acc


class ManagedStatus(BaseModel):
    enabled: bool             # 托管开关(默认 OFF)
    account_ready: bool       # 托管账户已建
    account_value: float      # ★账户价值(权益·浮动)= 现金 + Σ未实现浮盈浮亏 · 和活仓浮盈对得上
    available_funds: float    # ★可用资金 = 账户价值 − 已占用保证金 · 还能开多少单
    occupied_margin: float    # 已占用保证金(Σ initial_margin)
    cash_balance: float       # 账户现金(只扣手续费 · 不含浮盈)
    initial_capital: float    # 起始资金(10万U)
    open_positions: int       # 当前活仓数(总数不限)
    exit_tp: bool             # ★止盈平仓开关(默认开)
    exit_signal: bool         # ★信号转换平仓开关(默认开)
    exit_timeout: bool        # ★超时平仓开关(默认开 · 三个全关=仅手动平)
    tp_pct: int               # ★止盈目标(盈利%·默认 100 · 仅止盈开关开时生效)
    open_margin: float        # ★每单本金(U·可调 10-10000·默认 100)
    open_leverage: int        # ★杠杆(可调 1-20·默认 5)
    max_positions: int        # ★最大总持仓数(可调·默认 50·到上限不开新)
    allow_long: bool          # ★PR-8 允许开多(默认 ON·托管恒做多·OFF=不开新仓)


class ManagedToggleIn(BaseModel):
    enabled: bool


class ManagedExitToggleIn(BaseModel):
    which: str                # tp / signal / timeout
    on: bool


class ManagedTpPctIn(BaseModel):
    pct: int                  # 止盈目标(盈利%·> 0)


async def _status(db: AsyncSession, ch: ClickHouseDep) -> ManagedStatus:
    redis = await get_redis()
    enabled = await managed_guard.is_enabled(redis)
    switches = await managed_guard.get_exit_switches(redis)  # ★三平仓条件开关
    tp_pct = await managed_guard.get_tp_pct(redis)           # ★止盈目标(盈利%)
    open_margin = await managed_guard.get_open_margin(redis)       # ★每单本金
    open_leverage = await managed_guard.get_open_leverage(redis)   # ★杠杆
    max_positions = await managed_guard.get_max_positions(redis)   # ★最大总持仓
    allow_long = await managed_guard.get_allow_long(redis)         # ★PR-8 允许开多(全局)
    acc = await _managed_account_row(db)
    account_value = available = occupied = 0.0
    open_n = 0
    if acc is not None:
        open_n = await managed_guard.count_open_positions(db, acc.id)

        async def _fetch_mark(symbol: str) -> Decimal | None:
            marks = await select_premium_index_marks(ch._client, [symbol])  # noqa: SLF001
            return marks.get(symbol)

        # ★复用引擎现成 _cross_available_margin:(cross_equity=现金+ΣuPnL, used=Σ保证金, available)
        #   零重写盈亏 · 看板和活仓浮盈天然对得上(同一算法)。
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
            float(acc.initial_capital) if acc
            else float(managed_account.MANAGED_INITIAL_CAPITAL)
        ),
        open_positions=open_n,
        exit_tp=switches["tp"],
        exit_signal=switches["signal"],
        exit_timeout=switches["timeout"],
        tp_pct=tp_pct,
        open_margin=float(open_margin),
        open_leverage=open_leverage,
        max_positions=max_positions,
        allow_long=allow_long,
    )


@router.get("/status", summary="托管交易状态(开关/账户价值/可用/活仓)")
async def get_managed_status(_admin: AdminDep, db: DbDep, ch: ClickHouseDep) -> ManagedStatus:
    return await _status(db, ch)


@router.post("/toggle", summary="开/关托管交易(★默认 OFF · 开则首次建账户)")
async def toggle_managed(
    payload: ManagedToggleIn, _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> ManagedStatus:
    """★开关 · 开启时幂等建托管账户(系统用户 + 10万U perp 钱包)· 开仓编排 = PR-2。"""
    redis = await get_redis()
    if payload.enabled:
        await managed_account.ensure_managed_account(db)  # 首次开 → 幂等建账户
    await managed_guard.set_enabled(redis, payload.enabled)
    return await _status(db, ch)


class CapitalIn(BaseModel):
    amount: float             # 起始资金(> 0)


@router.post("/account/reset", summary="★清零重来(删托管账户持仓+历史 · cash 重置初始)")
async def reset_account(_admin: AdminDep, db: DbDep, ch: ClickHouseDep) -> ManagedStatus:
    """清零重置:删托管账户【所有持仓+历史】+ cash 重置 initial_capital · ★只该账户 · 不碰引擎。"""
    acc = await managed_account.ensure_managed_account(db)
    await account_admin.reset_account(db, acc)
    return await _status(db, ch)


@router.post("/account/capital", summary="★改起始资金(>0 · 清持仓 + 用新资金重来)")
async def set_capital(
    payload: CapitalIn, _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> ManagedStatus:
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="起始资金必须 > 0")
    acc = await managed_account.ensure_managed_account(db)
    await account_admin.set_account_capital(db, acc, Decimal(str(payload.amount)))
    return await _status(db, ch)


@router.post("/exit-switch", summary="★设单个平仓条件开关(tp/signal/timeout · 即时生效)")
async def set_exit_switch(
    payload: ManagedExitToggleIn, _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> ManagedStatus:
    """单个平仓条件开/关 · close_scan 每轮读最新 → 即时对已有持仓生效。"""
    if payload.which not in ("tp", "signal", "timeout"):
        raise HTTPException(status_code=400, detail="which 必须是 tp/signal/timeout")
    redis = await get_redis()
    await managed_guard.set_exit_switch(redis, payload.which, payload.on)
    return await _status(db, ch)


@router.post("/exit-tp-pct", summary="★设止盈目标(盈利%·>0 · 即时生效)")
async def set_tp_pct(
    payload: ManagedTpPctIn, _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> ManagedStatus:
    """止盈目标(盈利%)· close_scan 每轮读最新 → 即时生效 · 价涨幅% = 盈利% ÷ 杠杆。"""
    if payload.pct <= 0:
        raise HTTPException(status_code=400, detail="止盈目标(盈利%)必须 > 0")
    redis = await get_redis()
    await managed_guard.set_tp_pct(redis, payload.pct)
    return await _status(db, ch)


# ── 开仓参数(每单本金 / 杠杆 / 最大单数 · 即时生效)──────────────────────
class OpenMarginIn(BaseModel):
    margin: float             # 每单本金(U·10-10000)


class OpenLeverageIn(BaseModel):
    leverage: int             # 杠杆(1-20)


class MaxPositionsIn(BaseModel):
    max_positions: int        # 最大总持仓数(> 0)


@router.post("/open-margin", summary="★设每单本金(U·10-10000 · 即时生效)")
async def set_open_margin(
    payload: OpenMarginIn, _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> ManagedStatus:
    if not (10 <= payload.margin <= 10000):  # noqa: PLR2004
        raise HTTPException(status_code=400, detail="每单本金必须在 10-10000 U")
    redis = await get_redis()
    await managed_guard.set_open_margin(redis, Decimal(str(payload.margin)))
    return await _status(db, ch)


@router.post("/open-leverage", summary="★设杠杆(1-20 · 即时生效)")
async def set_open_leverage(
    payload: OpenLeverageIn, _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> ManagedStatus:
    if not (1 <= payload.leverage <= 20):  # noqa: PLR2004
        raise HTTPException(status_code=400, detail="杠杆必须在 1-20 倍")
    redis = await get_redis()
    await managed_guard.set_open_leverage(redis, payload.leverage)
    return await _status(db, ch)


@router.post("/max-positions", summary="★设最大总持仓数(>0 · 到上限不开新 · 即时生效)")
async def set_max_positions(
    payload: MaxPositionsIn, _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> ManagedStatus:
    if payload.max_positions <= 0:
        raise HTTPException(status_code=400, detail="最大总持仓数必须 > 0")
    redis = await get_redis()
    await managed_guard.set_max_positions(redis, payload.max_positions)
    return await _status(db, ch)


# ── 方向过滤器(PR-8 · 托管恒做多·只 allow_long·OFF=不开新仓 · 默认 ON · 即时生效)──
class AllowLongIn(BaseModel):
    on: bool                  # True=允许开多 / False=不开新仓


@router.post("/allow-long", summary="★设允许开多(on · 托管恒做多·OFF=不开新仓 · 即时生效)")
async def set_allow_long(
    payload: AllowLongIn, _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> ManagedStatus:
    redis = await get_redis()
    await managed_guard.set_allow_long(redis, payload.on)
    return await _status(db, ch)


# ── 看板:活仓 / 历史 / 统计(PR-4 · 前向测试)──────────────────────────


class ManagedPosition(BaseModel):
    id: int                  # ★position_id(手动平单用)
    symbol: str
    leverage: int
    entry_price: float
    quantity: float
    margin: float            # 本金(initial_margin)
    opened_at: str
    mark: float | None       # 当前标记价(无则 null)
    unrealized_pnl: float | None  # 浮盈 U =(mark−entry)×qty
    unrealized_pct: float | None  # 浮盈 % = uPnL / 本金
    bias: str | None         # ★维持的信号(last_bias · 偏多/偏空/中性 · 不在快照=维持上一次)


class ManagedTrade(BaseModel):
    symbol: str
    leverage: int
    entry_price: float
    exit_price: float        # ≈ entry + realized_pnl/qty(纯价格反推 · 不算手续费)
    quantity: float
    pnl_usdt: float          # realized_pnl
    pnl_pct: float           # realized_pnl / 本金
    close_reason: str | None  # tp / signal / timeout
    opened_at: str
    closed_at: str | None
    hold_seconds: int


class ManagedPositionsPage(BaseModel):
    items: list[ManagedPosition]
    total: int  # ★全部活仓数(前端算总页数)


@router.get("/positions", summary="托管当前活仓(含浮盈 · ★分页 100/页)")
async def list_managed_positions(
    _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
    offset: int = 0, limit: int = 100,
) -> ManagedPositionsPage:
    acc = await _managed_account_row(db)
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
        select(VirtualPerpPosition)
        .where(*base_where)
        .order_by(VirtualPerpPosition.opened_at.desc())
        .offset(max(offset, 0))
        .limit(max(min(limit, 500), 1)),  # ★限 1~500 防滥用
    ))
    marks = await select_premium_index_marks(ch._client, [r.symbol for r in rows]) if rows else {}  # noqa: SLF001
    out: list[ManagedPosition] = []
    for r in rows:
        mark = marks.get(r.symbol)
        upnl = (mark - r.entry_price) * r.quantity if mark is not None else None  # LONG
        margin = r.initial_margin
        out.append(ManagedPosition(
            id=r.id, symbol=r.symbol, leverage=r.leverage, entry_price=float(r.entry_price),
            quantity=float(r.quantity), margin=float(margin), opened_at=r.opened_at.isoformat(),
            mark=float(mark) if mark is not None else None,
            unrealized_pnl=float(upnl) if upnl is not None else None,
            unrealized_pct=float(upnl / margin) if upnl is not None and margin > 0 else None,
            bias=r.last_bias,  # ★维持的信号(close_scan 维护)
        ))
    return ManagedPositionsPage(items=out, total=total or 0)


class ManagedHistoryPage(BaseModel):
    items: list[ManagedTrade]
    total: int  # ★全部历史单数(前端算总页数)


@router.get("/history", summary="托管历史平仓(每单明细 · ★分页 50/页)")
async def list_managed_history(
    _admin: AdminDep, db: DbDep,
    offset: int = 0, limit: int = 50,
) -> ManagedHistoryPage:
    acc = await _managed_account_row(db)
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
        select(VirtualPerpPosition)
        .where(*base_where)
        .order_by(VirtualPerpPosition.closed_at.desc())
        .offset(max(offset, 0))
        .limit(max(min(limit, 200), 1)),  # ★限 1~200 防滥用
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


@router.get("/stats", summary="托管前向测试统计(胜率/盈亏比/最大回撤/按原因分类)")
async def get_managed_stats(
    _admin: AdminDep, db: DbDep,
) -> dict[str, float | int | dict[str, int]]:
    acc = await _managed_account_row(db)
    if acc is None:
        return compute_managed_stats([])
    rows = list(await db.scalars(
        select(VirtualPerpPosition)
        .where(
            VirtualPerpPosition.account_id == acc.id,
            VirtualPerpPosition.managed.is_(True),
            VirtualPerpPosition.closed_at.is_not(None),
        )
        .order_by(VirtualPerpPosition.closed_at.asc()),  # 升序 · 算最大回撤权益曲线
    ))
    trades = [ClosedTrade(realized_pnl=r.realized_pnl, close_reason=r.managed_close_reason)
              for r in rows]
    return compute_managed_stats(trades)


# ── 手动平单(人工应急出口 · 记 manual)────────────────────────────────


class ManualCloseResult(BaseModel):
    status: str                      # ok / error
    symbol: str | None = None
    realized_pnl: float | None = None
    reason: str | None = None        # error 时:not_found/not_managed/already_closed/rejected/...


@router.post(
    "/positions/{position_id}/close",
    summary="★手动平单(人工应急出口 · 调 route_close_perp · 记 managed_close_reason=manual)",
)
async def close_managed_position(
    position_id: int, _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> ManualCloseResult:
    """手动平掉一个托管活仓(突发应急)· ★唯一入口 route_close_perp · 不重写撮合 · 引擎零碰。"""
    fetcher = make_perp_mark_price_fetcher(ch)  # ★撮合 mark:premium 优先 + perp ticker 兜底
    result = await close_one_managed_position(db, fetcher, position_id)
    if result["status"] == "error":
        reason = str(result.get("reason") or "error")
        code = {"not_found": 404, "not_managed": 403, "already_closed": 409}.get(reason, 400)
        raise HTTPException(status_code=code, detail=reason)
    return ManualCloseResult(
        status="ok",
        symbol=result.get("symbol"),
        realized_pnl=result.get("realized_pnl"),
    )


class BatchCloseResult(BaseModel):
    status: str       # ok
    closed: int       # 实际平掉数
    total: int        # 本次扫到的活仓数(closed ≤ total · 个别被拒不算)


@router.post(
    "/positions/close-all",
    summary="★一键平掉所有托管活仓(人工批量 · 逐个 route_close_perp · 记 manual · 只托管账户)",
)
async def close_all_managed(
    _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> BatchCloseResult:
    """一键平掉全部托管活仓 · ★唯一入口 route_close_perp(逐个)· 只托管账户 · 引擎零碰。"""
    fetcher = make_perp_mark_price_fetcher(ch)
    result = await close_all_managed_positions(db, fetcher)
    return BatchCloseResult(
        status="ok", closed=int(result["closed"]), total=int(result["total"]),
    )
