"""铂金影子账户 provisioning pytest(多账户 PR-2)。

★重点:① ensure_*_for_user 幂等 + 影子账户独立(不同铂金用户互不串)· ② ★全局账户隔离(影子不影响
全局系统账户·现在跑的智能交易用全局·向后兼容)· ③ get_platinum_user_ids · ④ 真人 crypto 账户不受影响。
需 PG · 本地 collect · CI 真跑。
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.virtual import VirtualAccount
from app.services.virtual_trading.intelligent import account as iacc
from app.services.virtual_trading.managed import account as macc
from app.services.virtual_trading.platinum import get_platinum_user_ids
from tests.factories import make_user


@pytest.mark.asyncio
async def test_ensure_intelligent_for_user_idempotent(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    await db_session.commit()
    a1 = await iacc.ensure_intelligent_account_for_user(db_session, user.id)
    a2 = await iacc.ensure_intelligent_account_for_user(db_session, user.id)  # 幂等
    assert a1.id == a2.id
    assert float(a1.initial_capital) == 100000.0  # 10万 U
    # 影子系统用户不可登录
    shadow = await db_session.scalar(
        select(User).where(User.email == f"intelligent-{user.id}@system.midas.local"),
    )
    assert shadow is not None
    assert shadow.password_hash is None
    assert shadow.google_sub is None


@pytest.mark.asyncio
async def test_shadow_accounts_isolated_per_user(db_session: AsyncSession) -> None:
    # ★不同铂金用户的影子账户互相独立(不串户)
    u1 = await make_user(db_session)
    u2 = await make_user(db_session)
    await db_session.commit()
    a1 = await iacc.ensure_intelligent_account_for_user(db_session, u1.id)
    a2 = await iacc.ensure_intelligent_account_for_user(db_session, u2.id)
    assert a1.id != a2.id
    assert a1.user_id != a2.user_id


@pytest.mark.asyncio
async def test_global_account_not_affected(db_session: AsyncSession) -> None:
    # ★★向后兼容铁证:建影子账户【不影响】全局系统账户(现在跑的智能交易用全局·不破)
    global_acc = await iacc.ensure_intelligent_account(db_session)  # 全局(现在跑的)
    user = await make_user(db_session)
    await db_session.commit()
    shadow_acc = await iacc.ensure_intelligent_account_for_user(db_session, user.id)
    # 全局账户 user_id ≠ 影子账户 user_id · 两套独立
    assert global_acc.user_id != shadow_acc.user_id
    # 全局账户仍可正常解析(现在跑的逻辑不破)
    assert await iacc.get_intelligent_user_id(db_session) == global_acc.user_id


@pytest.mark.asyncio
async def test_managed_for_user_idempotent(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    await db_session.commit()
    a1 = await macc.ensure_managed_account_for_user(db_session, user.id)
    a2 = await macc.ensure_managed_account_for_user(db_session, user.id)
    assert a1.id == a2.id
    # ★托管影子 + 智能影子是同一真人用户的两个不同影子(market 都 crypto·但不同影子 user)
    intel = await iacc.ensure_intelligent_account_for_user(db_session, user.id)
    assert a1.user_id != intel.user_id  # 托管影子 user ≠ 智能影子 user


@pytest.mark.asyncio
async def test_get_platinum_user_ids(db_session: AsyncSession) -> None:
    normal = await make_user(db_session)
    plat1 = await make_user(db_session)
    plat2 = await make_user(db_session)
    plat1.is_platinum = True
    plat2.is_platinum = True
    await db_session.commit()
    ids = await get_platinum_user_ids(db_session)
    assert plat1.id in ids
    assert plat2.id in ids
    assert normal.id not in ids  # ★非铂金不在列表


@pytest.mark.asyncio
async def test_real_user_crypto_account_untouched(db_session: AsyncSession) -> None:
    # ★影子账户 email 含真人 uid,但影子是【独立 user】·真人自己的 crypto 账户完全不受影响
    user = await make_user(db_session)
    await db_session.commit()
    await iacc.ensure_intelligent_account_for_user(db_session, user.id)
    # 真人 user_id 名下【没有】被建 crypto 账户(影子挂在影子 user 名下·非真人)
    real_acc_count = await db_session.scalar(
        select(func.count()).select_from(VirtualAccount).where(
            VirtualAccount.user_id == user.id,
            VirtualAccount.market == "crypto",
        ),
    )
    assert real_acc_count == 0  # ★真人 crypto 账户零影响(影子隔离)
