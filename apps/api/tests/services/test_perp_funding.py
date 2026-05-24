"""加密永续合约资金费结算 pytest · ADR-0020 Block1 · M2-C.2.2。

🔴 红线:全程虚拟资金 · 这些只校验虚拟资金费结算的数值 / 时机,绝不接真实资金费。

覆盖:
- funding_payment 纯函数:rate>0 多头付 / 空头收 · rate<0 方向反转
- aligned_for_settlement:8h(0/8/16)/ 4h(0/4/8/12/16/20)/ 1h / 非法 interval
- settle_funding:扣 / 收现金 + funding_paid 累加 + 写流水
- 按币周期对齐:4h 币在 hour=4 结算、hour=3 不结算
- 幂等:同一结算整点重跑不重复扣(E4 不重结)
- 扣为负不报错、不强平(E4=A)
- 无 premium(无 mark)跳过,不猜价
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import (
    MarginMode,
    PerpSide,
    VirtualPerpFunding,
    VirtualPerpPosition,
)
from app.services.virtual_trading.perp_funding import (
    PremiumSnapshot,
    aligned_for_settlement,
    funding_payment,
    settle_funding,
)
from tests.factories import make_user, make_virtual_account


async def _account_with_position(
    db: AsyncSession,
    *,
    side: PerpSide = PerpSide.LONG,
    qty: str = "1",
    symbol: str = "BTCUSDT",
    capital: str = "100000",
    entry: str = "30000",
    leverage: int = 10,
) -> tuple[object, object, VirtualPerpPosition]:
    user = await make_user(db)
    account = await make_virtual_account(
        db, user_id=user.id, market="crypto", initial_capital=Decimal(capital),
    )
    pos = VirtualPerpPosition(
        account_id=account.id, symbol=symbol, side=side,
        margin_mode=MarginMode.ISOLATED, leverage=leverage,
        quantity=Decimal(qty), entry_price=Decimal(entry),
        initial_margin=Decimal("3000"), maintenance_margin_rate=Decimal("0.005"),
        liquidation_price=Decimal("27000"),
    )
    db.add(pos)
    await db.flush()
    await db.commit()
    return user, account, pos


# UTC 整点 · hour=8 是 8h/4h/2h/1h 全部周期的结算点
_NOW_H8 = datetime(2026, 5, 24, 8, 0, 0, tzinfo=UTC)


# ============================================================================
# 1 · 纯函数:funding_payment(多付空收 + rate<0 反转)
# ============================================================================


def test_funding_payment_long_pays_when_rate_positive() -> None:
    # 0.0001 × 30000 × 1 = 3 · long 付(正 = 现金减少)
    assert funding_payment(
        PerpSide.LONG, Decimal("0.0001"), Decimal("30000"), Decimal("1"),
    ) == Decimal("3.0000")


def test_funding_payment_short_receives_when_rate_positive() -> None:
    # short 收(负 = 现金增加)
    assert funding_payment(
        PerpSide.SHORT, Decimal("0.0001"), Decimal("30000"), Decimal("1"),
    ) == Decimal("-3.0000")


def test_funding_payment_negative_rate_reverses() -> None:
    # rate<0:long 收、short 付
    assert funding_payment(
        PerpSide.LONG, Decimal("-0.0001"), Decimal("30000"), Decimal("1"),
    ) == Decimal("-3.0000")
    assert funding_payment(
        PerpSide.SHORT, Decimal("-0.0001"), Decimal("30000"), Decimal("1"),
    ) == Decimal("3.0000")


def test_aligned_for_settlement() -> None:
    # 8h → 0/8/16
    assert aligned_for_settlement(8, 0)
    assert aligned_for_settlement(8, 8)
    assert aligned_for_settlement(8, 16)
    assert not aligned_for_settlement(8, 4)
    assert not aligned_for_settlement(8, 3)
    # 4h → 0/4/8/12/16/20
    assert aligned_for_settlement(4, 4)
    assert aligned_for_settlement(4, 12)
    assert aligned_for_settlement(4, 20)
    assert not aligned_for_settlement(4, 3)
    assert not aligned_for_settlement(4, 2)
    # 1h → 每点;非法 interval → 永不结算(不除零)
    assert aligned_for_settlement(1, 7)
    assert not aligned_for_settlement(0, 0)


# ============================================================================
# 2 · settle_funding:扣 / 收现金 + funding_paid + 流水
# ============================================================================


@pytest.mark.asyncio
async def test_settle_long_charges_cash(db_session: AsyncSession) -> None:
    _u, account, pos = await _account_with_position(db_session, side=PerpSide.LONG)
    premium = {
        "BTCUSDT": PremiumSnapshot(Decimal("30000"), Decimal("0.0001"), 8),
    }
    result = await settle_funding(db_session, premium, now=_NOW_H8)
    assert result == {"settled": 1, "skipped": 0}

    await db_session.refresh(account)
    await db_session.refresh(pos)
    # 100000 − 3 = 99997(long 付)
    assert account.cash_balance == Decimal("99997.0000")
    assert pos.funding_paid == Decimal("3.0000")

    rows = (
        await db_session.scalars(
            select(VirtualPerpFunding).where(VirtualPerpFunding.position_id == pos.id),
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].payment == Decimal("3.0000")
    assert rows[0].funding_rate == Decimal("0.0001")
    assert rows[0].side == PerpSide.LONG


@pytest.mark.asyncio
async def test_settle_short_credits_cash(db_session: AsyncSession) -> None:
    _u, account, pos = await _account_with_position(db_session, side=PerpSide.SHORT)
    premium = {
        "BTCUSDT": PremiumSnapshot(Decimal("30000"), Decimal("0.0001"), 8),
    }
    result = await settle_funding(db_session, premium, now=_NOW_H8)
    assert result["settled"] == 1

    await db_session.refresh(account)
    await db_session.refresh(pos)
    # 100000 − (−3) = 100003(short 收)
    assert account.cash_balance == Decimal("100003.0000")
    assert pos.funding_paid == Decimal("-3.0000")


# ============================================================================
# 3 · 按币周期对齐(E3)
# ============================================================================


@pytest.mark.asyncio
async def test_4h_coin_settles_at_4h_boundary(db_session: AsyncSession) -> None:
    """4h 币在 hour=4 结算(8h 币此刻不会结)。"""
    _u, account, _pos = await _account_with_position(db_session, symbol="BSBUSDT")
    premium = {
        "BSBUSDT": PremiumSnapshot(Decimal("30000"), Decimal("0.0001"), 4),
    }
    now_h4 = datetime(2026, 5, 24, 4, 0, 0, tzinfo=UTC)
    result = await settle_funding(db_session, premium, now=now_h4)
    assert result["settled"] == 1
    await db_session.refresh(account)
    assert account.cash_balance == Decimal("99997.0000")


@pytest.mark.asyncio
async def test_4h_coin_not_settled_off_boundary(db_session: AsyncSession) -> None:
    """4h 币在 hour=3 不结算(未对齐)· 现金不动、无流水。"""
    _u, account, _pos = await _account_with_position(db_session, symbol="BSBUSDT")
    premium = {
        "BSBUSDT": PremiumSnapshot(Decimal("30000"), Decimal("0.0001"), 4),
    }
    now_h3 = datetime(2026, 5, 24, 3, 0, 0, tzinfo=UTC)
    result = await settle_funding(db_session, premium, now=now_h3)
    assert result["settled"] == 0
    await db_session.refresh(account)
    assert account.cash_balance == Decimal("100000.0000")
    rows = (await db_session.scalars(select(VirtualPerpFunding))).all()
    assert len(rows) == 0


# ============================================================================
# 4 · 幂等 / 扣为负不强平 / 无 premium 跳过
# ============================================================================


@pytest.mark.asyncio
async def test_idempotent_same_settlement_hour(db_session: AsyncSession) -> None:
    _u, account, pos = await _account_with_position(db_session, side=PerpSide.LONG)
    premium = {
        "BTCUSDT": PremiumSnapshot(Decimal("30000"), Decimal("0.0001"), 8),
    }
    r1 = await settle_funding(db_session, premium, now=_NOW_H8)
    await db_session.commit()
    r2 = await settle_funding(db_session, premium, now=_NOW_H8)  # 同 funding_ts
    assert r1["settled"] == 1
    assert r2["settled"] == 0  # 幂等 · 不重复扣

    await db_session.refresh(account)
    assert account.cash_balance == Decimal("99997.0000")  # 只扣一次
    rows = (
        await db_session.scalars(
            select(VirtualPerpFunding).where(VirtualPerpFunding.position_id == pos.id),
        )
    ).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_cash_can_go_negative_no_liquidation(db_session: AsyncSession) -> None:
    """E4=A:资金费扣为负也不报错、不联动强平。"""
    _u, account, pos = await _account_with_position(
        db_session, side=PerpSide.LONG, capital="1",
    )
    # payment = 0.01 × 30000 × 1 = 300 → cash 1 − 300 = −299
    premium = {
        "BTCUSDT": PremiumSnapshot(Decimal("30000"), Decimal("0.01"), 8),
    }
    result = await settle_funding(db_session, premium, now=_NOW_H8)
    assert result["settled"] == 1

    await db_session.refresh(account)
    await db_session.refresh(pos)
    assert account.cash_balance == Decimal("-299.0000")  # 允许为负
    assert pos.closed_at is None  # 资金费不强平 · 仓位仍在


@pytest.mark.asyncio
async def test_missing_premium_skips(db_session: AsyncSession) -> None:
    _u, account, _pos = await _account_with_position(db_session, symbol="WIFUSDT")
    result = await settle_funding(db_session, {}, now=_NOW_H8)  # 无 premium
    assert result == {"settled": 0, "skipped": 1}
    await db_session.refresh(account)
    assert account.cash_balance == Decimal("100000.0000")
