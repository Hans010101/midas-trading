"""托管交易 PR-1 · 账户 provisioning 幂等 + 守卫 helpers。

- ensure_managed_account:幂等(调两次只 1 系统用户 + 1 账户 · 不重置资金)。
- guard:开关默认 OFF + 仓位约束(并行数 / 同币去重)· PR-2 用。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.models.user import User
from app.models.virtual import VirtualAccount
from app.services.virtual_trading.managed import account as macc
from app.services.virtual_trading.managed import guard as mguard
from app.services.virtual_trading.perp_fees import q_money


class _FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, Any] = {}

    async def get(self, k: str) -> Any:
        return self.kv.get(k)

    async def set(self, k: str, v: Any) -> None:
        self.kv[k] = v


# ── 账户 provisioning 幂等 ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ensure_managed_account_idempotent(db_session: AsyncSession) -> None:
    a1 = await macc.ensure_managed_account(db_session)
    assert a1.market == "crypto"
    assert a1.initial_capital == macc.MANAGED_INITIAL_CAPITAL  # 10万U
    assert a1.cash_balance == macc.MANAGED_INITIAL_CAPITAL
    # 再调一次 → 同账户(不新建、不重置)
    a2 = await macc.ensure_managed_account(db_session)
    assert a2.id == a1.id
    # ★只 1 个系统用户 + 1 个托管账户
    n_user = await db_session.scalar(
        select(func.count()).select_from(User).where(User.email == macc.MANAGED_BOT_EMAIL),
    )
    n_acc = await db_session.scalar(
        select(func.count()).select_from(VirtualAccount).where(VirtualAccount.id == a1.id),
    )
    assert n_user == 1
    assert n_acc == 1


@pytest.mark.asyncio
async def test_managed_bot_user_not_loginable(db_session: AsyncSession) -> None:
    await macc.ensure_managed_account(db_session)
    user = await db_session.scalar(
        select(User).where(User.email == macc.MANAGED_BOT_EMAIL),
    )
    assert user is not None
    assert user.password_hash is None  # ★无密码 → 不可登录
    assert user.google_sub is None     # ★无 OAuth


@pytest.mark.asyncio
async def test_get_managed_user_id(db_session: AsyncSession) -> None:
    assert await macc.get_managed_user_id(db_session) is None  # 未建 → None
    acc = await macc.ensure_managed_account(db_session)
    uid = await macc.get_managed_user_id(db_session)
    assert uid == acc.user_id


# ── 守卫:开关默认 OFF + 仓位约束 ─────────────────────────────────────
@pytest.mark.asyncio
async def test_managed_switch_default_off() -> None:
    r = _FakeRedis()
    assert await mguard.is_enabled(r) is False  # ★默认 OFF
    await mguard.set_enabled(r, enabled=True)
    assert await mguard.is_enabled(r) is True
    await mguard.set_enabled(r, enabled=False)
    assert await mguard.is_enabled(r) is False


@pytest.mark.asyncio
async def test_position_count_and_dedup(db_session: AsyncSession) -> None:
    acc = await macc.ensure_managed_account(db_session)
    assert await mguard.count_open_positions(db_session, acc.id) == 0
    assert await mguard.has_open_position(db_session, acc.id, "BTCUSDT") is False
    q, e = Decimal("1"), Decimal("100")
    db_session.add(VirtualPerpPosition(
        account_id=acc.id, symbol="BTCUSDT", side=PerpSide.LONG,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=q, entry_price=e,
        initial_margin=q_money(q * e / Decimal(5)),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        managed=True,
    ))
    await db_session.flush()
    assert await mguard.count_open_positions(db_session, acc.id) == 1
    assert await mguard.has_open_position(db_session, acc.id, "BTCUSDT") is True  # ★同币已持
    assert await mguard.has_open_position(db_session, acc.id, "ETHUSDT") is False
