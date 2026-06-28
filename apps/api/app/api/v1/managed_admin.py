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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep, ClickHouseDep
from app.api.v1.perp import make_perp_mark_price_fetcher
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.perp import VirtualPerpPosition
from app.models.user import User
from app.models.virtual import VirtualAccount
from app.services.clickhouse_crypto import select_premium_index_marks
from app.services.virtual_trading.managed import account as managed_account
from app.services.virtual_trading.managed import guard as managed_guard
from app.services.virtual_trading.managed.close import close_one_managed_position
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


class ManagedToggleIn(BaseModel):
    enabled: bool


async def _status(db: AsyncSession, ch: ClickHouseDep) -> ManagedStatus:
    redis = await get_redis()
    enabled = await managed_guard.is_enabled(redis)
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
        initial_capital=float(managed_account.MANAGED_INITIAL_CAPITAL),
        open_positions=open_n,
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


@router.get("/positions", summary="托管当前活仓(含浮盈 · 前向测试)")
async def list_managed_positions(
    _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> list[ManagedPosition]:
    acc = await _managed_account_row(db)
    if acc is None:
        return []
    rows = list(await db.scalars(
        select(VirtualPerpPosition)
        .where(
            VirtualPerpPosition.account_id == acc.id,
            VirtualPerpPosition.managed.is_(True),
            VirtualPerpPosition.closed_at.is_(None),
        )
        .order_by(VirtualPerpPosition.opened_at.desc()),
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
        ))
    return out


@router.get("/history", summary="托管历史平仓(每单明细 · 前向测试)")
async def list_managed_history(
    _admin: AdminDep, db: DbDep,
) -> list[ManagedTrade]:
    acc = await _managed_account_row(db)
    if acc is None:
        return []
    rows = list(await db.scalars(
        select(VirtualPerpPosition)
        .where(
            VirtualPerpPosition.account_id == acc.id,
            VirtualPerpPosition.managed.is_(True),
            VirtualPerpPosition.closed_at.is_not(None),
        )
        .order_by(VirtualPerpPosition.closed_at.desc())
        .limit(200),
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
    return out


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
