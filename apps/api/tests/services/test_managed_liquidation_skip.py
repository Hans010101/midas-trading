"""托管交易 PR-1 · ★禁强平核心:强平 worker 候选账户排除 managed(托管)仓。

select_open_cross_account_ids:seed 1 个 managed 账户 + 1 个普通账户(都有 cross 活仓)→
断言【只普通账户】进强平候选,★managed 账户不进(整账户被排除 → 不强平)· 引擎纯函数零改。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.services.virtual_trading.perp_cross_liquidation import (
    select_open_cross_account_ids,
)
from app.services.virtual_trading.perp_fees import q_money
from tests.factories import make_user, make_virtual_account


async def _account(db: AsyncSession) -> int:
    user = await make_user(db)
    acct = await make_virtual_account(
        db, user_id=user.id, market="crypto", initial_capital=Decimal("100000"),
    )
    await db.commit()
    return acct.id


async def _add_cross(
    db: AsyncSession, account_id: int, symbol: str, *, managed: bool,
) -> VirtualPerpPosition:
    q, e = Decimal("1"), Decimal("100")
    pos = VirtualPerpPosition(
        account_id=account_id, symbol=symbol, side=PerpSide.LONG,
        margin_mode=MarginMode.CROSS, leverage=5,
        quantity=q, entry_price=e,
        initial_margin=q_money(q * e / Decimal(5)),
        maintenance_margin_rate=Decimal("0.005"),
        liquidation_price=Decimal("0"),
        managed=managed,
    )
    db.add(pos)
    await db.flush()
    return pos


@pytest.mark.asyncio
async def test_liquidation_candidates_exclude_managed(db_session: AsyncSession) -> None:
    normal_acc = await _account(db_session)
    managed_acc = await _account(db_session)
    await _add_cross(db_session, normal_acc, "BTCUSDT", managed=False)   # 普通仓
    await _add_cross(db_session, managed_acc, "ETHUSDT", managed=True)   # ★托管仓
    await db_session.flush()

    candidates = await select_open_cross_account_ids(db_session)
    # ★只普通账户进强平候选 · 托管账户(全 managed 仓)被排除 → 不强平
    assert normal_acc in candidates
    assert managed_acc not in candidates


@pytest.mark.asyncio
async def test_liquidation_candidates_normal_unaffected(db_session: AsyncSession) -> None:
    # ★零回归:无 managed 仓时,普通账户照常全进候选(现有强平行为不变)
    acc = await _account(db_session)
    await _add_cross(db_session, acc, "BTCUSDT", managed=False)
    await db_session.flush()
    assert acc in await select_open_cross_account_ids(db_session)
