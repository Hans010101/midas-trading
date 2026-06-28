"""智能交易 PR-2 地基 · service 测:account provisioning + guard 开关 + 通用账户管理。

★account_admin 红线:清零/改金额【只碰指定账户】(不删其他账户的仓)· 用 DB(midas_test · CI)。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.models.virtual import VirtualAccount
from app.services.virtual_trading import account_admin
from app.services.virtual_trading.intelligent import account as iacc
from app.services.virtual_trading.intelligent import guard as iguard
from tests.factories import make_user


class _FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}

    async def get(self, k: str) -> str | None:
        return self.kv.get(k)

    async def set(self, k: str, v: str) -> None:
        self.kv[k] = v


def _pos(account_id: int, symbol: str) -> VirtualPerpPosition:
    return VirtualPerpPosition(
        account_id=account_id, symbol=symbol, side=PerpSide.LONG,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal("100"), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
    )


async def _count_pos(db: AsyncSession, account_id: int) -> int:
    n = await db.scalar(
        select(func.count()).select_from(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account_id,
        ),
    )
    return int(n or 0)


# ── account provisioning + guard ─────────────────────────────────────
@pytest.mark.asyncio
async def test_ensure_intelligent_account_idempotent(db_session: AsyncSession) -> None:
    a1 = await iacc.ensure_intelligent_account(db_session)
    a2 = await iacc.ensure_intelligent_account(db_session)  # ★幂等:不重复建
    assert a1.id == a2.id
    assert a1.market == "crypto"
    assert a1.initial_capital == Decimal("100000")
    uid = await iacc.get_intelligent_user_id(db_session)
    assert uid == a1.user_id


@pytest.mark.asyncio
async def test_guard_switch_default_off() -> None:
    r = _FakeRedis()
    assert await iguard.is_enabled(r) is False  # ★默认 OFF
    await iguard.set_enabled(r, enabled=True)
    assert await iguard.is_enabled(r) is True
    await iguard.set_enabled(r, enabled=False)
    assert await iguard.is_enabled(r) is False


# ── 通用账户管理:清零 / 改金额 ───────────────────────────────────────
@pytest.mark.asyncio
async def test_reset_account_clears_and_resets(db_session: AsyncSession) -> None:
    acc = await iacc.ensure_intelligent_account(db_session)
    acc.cash_balance = Decimal("95000")  # 模拟有浮亏
    acc.realized_pnl = Decimal("-5000")
    db_session.add_all([_pos(acc.id, "BTCUSDT"), _pos(acc.id, "ETHUSDT")])
    await db_session.flush()
    n = await account_admin.reset_account(db_session, acc)
    assert n == 2  # ★删了 2 仓
    await db_session.refresh(acc)
    assert acc.cash_balance == acc.initial_capital  # cash 重置到初始
    assert acc.realized_pnl == Decimal("0")
    assert await _count_pos(db_session, acc.id) == 0


@pytest.mark.asyncio
async def test_reset_only_touches_target_account(db_session: AsyncSession) -> None:
    # ★红线:清零【只删该账户】的仓,绝不碰其他账户
    acc = await iacc.ensure_intelligent_account(db_session)
    db_session.add(_pos(acc.id, "BTCUSDT"))
    other_user = await make_user(db_session, role="user")
    other_acc = VirtualAccount(
        user_id=other_user.id, market="crypto", currency="USDT",
        initial_capital=Decimal("100000"), cash_balance=Decimal("100000"),
    )
    db_session.add(other_acc)
    await db_session.flush()
    db_session.add(_pos(other_acc.id, "BTCUSDT"))
    await db_session.flush()
    await account_admin.reset_account(db_session, acc)
    assert await _count_pos(db_session, acc.id) == 0       # 目标账户清空
    assert await _count_pos(db_session, other_acc.id) == 1  # ★其他账户仓位不动


@pytest.mark.asyncio
async def test_set_capital_changes_initial_and_resets(db_session: AsyncSession) -> None:
    acc = await iacc.ensure_intelligent_account(db_session)
    db_session.add(_pos(acc.id, "BTCUSDT"))
    await db_session.flush()
    await account_admin.set_account_capital(db_session, acc, Decimal("50000"))
    await db_session.refresh(acc)
    assert acc.initial_capital == Decimal("50000")  # ★起始资金改了
    assert acc.cash_balance == Decimal("50000")
    assert acc.realized_pnl == Decimal("0")
    assert await _count_pos(db_session, acc.id) == 0  # 改金额顺带清仓
