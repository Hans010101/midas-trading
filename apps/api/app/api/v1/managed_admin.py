"""托管交易(策略前向测试)· admin 端点(托管交易 PR-1)· 🔴纯虚拟绝不真单。

★独立于 api/v1/admin.py:admin 域有架构守卫(test_admin_domain_no_engine_no_login_import 递归扫
admin import 树,禁 import virtual_trading)· 托管端点要 import virtual_trading.managed,故单独成模块,
直接在 v1 router 注册(admin.py 不 import 本模块)· 仍挂 AdminDep(403 边界)。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.user import User
from app.models.virtual import VirtualAccount
from app.services.virtual_trading.managed import account as managed_account
from app.services.virtual_trading.managed import guard as managed_guard

router = APIRouter(prefix="/admin/managed", tags=["managed"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


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
    acc = await db.scalar(
        select(VirtualAccount).where(
            VirtualAccount.user_id.in_(
                select(User.id).where(User.email == managed_account.MANAGED_BOT_EMAIL),
            ),
            VirtualAccount.market == managed_account.MANAGED_MARKET,
        ),
    )
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
