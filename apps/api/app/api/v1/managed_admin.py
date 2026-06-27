"""托管交易(策略前向测试)· admin 端点(托管交易 PR-1)· 🔴纯虚拟绝不真单。

★独立于 api/v1/admin.py:admin 域有架构守卫(test_admin_domain_no_engine_no_login_import 递归扫
admin import 树,禁 import virtual_trading)· 托管端点要 import virtual_trading.managed,故单独成模块,
直接在 v1 router 注册(admin.py 不 import 本模块)· 仍挂 AdminDep(403 边界)。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep, ClickHouseDep
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.perp import VirtualPerpPosition
from app.models.user import User
from app.models.virtual import VirtualAccount
from app.services.clickhouse_crypto import select_premium_index_marks
from app.services.virtual_trading.managed import account as managed_account
from app.services.virtual_trading.managed import guard as managed_guard
from app.services.virtual_trading.managed.stats import ClosedTrade, compute_managed_stats

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
    cash_balance: float       # 托管账户现金(USDT)
    initial_capital: float    # 起始资金(10万U)
    open_positions: int       # 当前活仓数(≤5)


class ManagedToggleIn(BaseModel):
    enabled: bool


async def _status(db: AsyncSession) -> ManagedStatus:
    redis = await get_redis()
    enabled = await managed_guard.is_enabled(redis)
    acc = await _managed_account_row(db)
    open_n = await managed_guard.count_open_positions(db, acc.id) if acc is not None else 0
    return ManagedStatus(
        enabled=enabled,
        account_ready=acc is not None,
        cash_balance=float(acc.cash_balance) if acc else 0.0,
        initial_capital=float(managed_account.MANAGED_INITIAL_CAPITAL),
        open_positions=open_n,
    )


@router.get("/status", summary="托管交易状态(开关/账户/现金/活仓)")
async def get_managed_status(_admin: AdminDep, db: DbDep) -> ManagedStatus:
    return await _status(db)


@router.post("/toggle", summary="开/关托管交易(★默认 OFF · 开则首次建账户)")
async def toggle_managed(
    payload: ManagedToggleIn, _admin: AdminDep, db: DbDep,
) -> ManagedStatus:
    """★开关 · 开启时幂等建托管账户(系统用户 + 10万U perp 钱包)· 开仓编排 = PR-2。"""
    redis = await get_redis()
    if payload.enabled:
        await managed_account.ensure_managed_account(db)  # 首次开 → 幂等建账户
    await managed_guard.set_enabled(redis, payload.enabled)
    return await _status(db)


# ── 看板:活仓 / 历史 / 统计(PR-4 · 前向测试)──────────────────────────


class ManagedPosition(BaseModel):
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
            symbol=r.symbol, leverage=r.leverage, entry_price=float(r.entry_price),
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
