"""智能交易 admin 端点(智能交易 PR-2 地基)· 🔴纯虚拟绝不真单。

★独立模块(架构守卫 test_admin_domain_no_engine_no_login_import 禁 admin.py import virtual_trading)·
直接在 v1 router 注册(admin.py 不 import 本模块)· 挂 AdminDep(403 边界)。
PR-2 = 开关 + 账户 + 账户管理(金额可改/清零)· 看板端点(positions/history/stats)= PR-6。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.user import User
from app.models.virtual import VirtualAccount
from app.services.virtual_trading import account_admin
from app.services.virtual_trading.intelligent import account as intelligent_account
from app.services.virtual_trading.intelligent import guard as intelligent_guard

router = APIRouter(prefix="/admin/intelligent", tags=["intelligent"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _intelligent_account_row(db: AsyncSession) -> VirtualAccount | None:
    acc: VirtualAccount | None = await db.scalar(
        select(VirtualAccount).where(
            VirtualAccount.user_id.in_(
                select(User.id).where(User.email == intelligent_account.INTELLIGENT_BOT_EMAIL),
            ),
            VirtualAccount.market == intelligent_account.INTELLIGENT_MARKET,
        ),
    )
    return acc


class IntelligentStatus(BaseModel):
    enabled: bool             # 智能交易开关(默认 OFF)
    account_ready: bool       # 智能交易账户已建
    initial_capital: float    # ★起始资金(可改 · 取自 account.initial_capital · 默认 10万U)
    cash_balance: float       # 账户现金
    open_positions: int       # 当前活仓数


class IntelligentToggleIn(BaseModel):
    enabled: bool


class CapitalIn(BaseModel):
    amount: float             # 起始资金(> 0)


async def _status(db: AsyncSession) -> IntelligentStatus:
    redis = await get_redis()
    enabled = await intelligent_guard.is_enabled(redis)
    acc = await _intelligent_account_row(db)
    open_n = await intelligent_guard.count_open_positions(db, acc.id) if acc is not None else 0
    default_cap = float(intelligent_account.INTELLIGENT_INITIAL_CAPITAL)
    return IntelligentStatus(
        enabled=enabled,
        account_ready=acc is not None,
        initial_capital=float(acc.initial_capital) if acc else default_cap,
        cash_balance=float(acc.cash_balance) if acc else 0.0,
        open_positions=open_n,
    )


@router.get("/status", summary="智能交易状态(开关/账户/起始资金/活仓)")
async def get_status(_admin: AdminDep, db: DbDep) -> IntelligentStatus:
    return await _status(db)


@router.post("/toggle", summary="开/关智能交易(★默认 OFF · 开则首次建账户)")
async def toggle(payload: IntelligentToggleIn, _admin: AdminDep, db: DbDep) -> IntelligentStatus:
    """★开关 · 开启时幂等建智能交易账户(系统用户 + perp 钱包)· 开仓编排 = PR-4。"""
    redis = await get_redis()
    if payload.enabled:
        await intelligent_account.ensure_intelligent_account(db)
    await intelligent_guard.set_enabled(redis, payload.enabled)
    return await _status(db)


@router.post("/account/reset", summary="★清零重来(删智能账户持仓+历史 · cash 重置初始)")
async def reset(_admin: AdminDep, db: DbDep) -> IntelligentStatus:
    """清零重置:删智能账户【持仓+历史】+ cash 重置 initial_capital · ★只该账户 · 不碰引擎。"""
    acc = await intelligent_account.ensure_intelligent_account(db)
    await account_admin.reset_account(db, acc)
    return await _status(db)


@router.post("/account/capital", summary="★改起始资金(>0 · 清持仓 + 用新资金重来)")
async def set_capital(payload: CapitalIn, _admin: AdminDep, db: DbDep) -> IntelligentStatus:
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="起始资金必须 > 0")
    acc = await intelligent_account.ensure_intelligent_account(db)
    await account_admin.set_account_capital(db, acc, Decimal(str(payload.amount)))
    return await _status(db)
