"""美股卖空(虚拟负持仓 · 无杠杆 1:1)撮合 pytest · 0023 阶段③ · 3.4 批1。

覆盖(模型 A · 锁定等额现金担保):
- 开空:扣现金 = notional + 手续费(担保)· 建 SHORT 仓 · position_side 正确
- 平空盈利(回补价 < 开仓价):返还担保 + 已实现 · 现金/持仓正确
- 平空亏损(回补价 > 开仓价):已实现为负 · 现金相应减少(无强平 · 允许走低)
- 部分平空:活仓保留 + 已实现累积
- 卖空加仓加权平均
- 现金担保不足 → reject
- 平空数量超持仓 → reject
- 跨方向守卫:已有做多仓时开空被拒(反之亦然)→ 保护现货做多
- 空头权益估值:positions_value = 担保 + 浮盈

现货做多零回归在 test_virtual_engine.py(原有)· 本文件只测新增 SHORT 路径 +
做多/卖空共存时的隔离。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.virtual import (
    OrderSide,
    OrderStatus,
    PositionSide,
    SnapshotTrigger,
    VirtualPosition,
)
from app.services.virtual_trading.engine import PlaceOrderRequest, place_market_order
from app.services.virtual_trading.equity import snapshot_equity_for_account
from tests.factories import (
    make_static_price_fetcher,
    make_user,
    make_virtual_account,
)


def _short(user_id, qty: str) -> PlaceOrderRequest:
    return PlaceOrderRequest(
        user_id=user_id, symbol="NVDA", market="us",
        side=OrderSide.SELL, position_side=PositionSide.SHORT,
        quantity=Decimal(qty),
    )


def _cover(user_id, qty: str) -> PlaceOrderRequest:
    return PlaceOrderRequest(
        user_id=user_id, symbol="NVDA", market="us",
        side=OrderSide.BUY, position_side=PositionSide.SHORT,
        quantity=Decimal(qty),
    )


async def _acct(db: AsyncSession, capital: str = "100000"):
    user = await make_user(db)
    account = await make_virtual_account(
        db, user_id=user.id, market="us", initial_capital=Decimal(capital),
    )
    await db.commit()
    return user, account


@pytest.mark.asyncio
async def test_open_short_locks_collateral_and_creates_short_position(
    db_session: AsyncSession,
):
    user, account = await _acct(db_session)
    # 卖空 10 @ 100 · us SELL 滑点 3bp → 99.97 · us 零佣 · 担保 = 999.70
    fetcher = make_static_price_fetcher({("NVDA", "us"): Decimal("100")})
    order = await place_market_order(db_session, _short(user.id, "10"), fetcher)
    await db_session.commit()

    assert order.status == OrderStatus.FILLED
    assert order.position_side == PositionSide.SHORT
    assert order.side == OrderSide.SELL
    assert order.price == Decimal("99.9700")
    assert order.realized_pnl is None

    await db_session.refresh(account)
    assert account.cash_balance == Decimal("99000.3000")  # 100000 - 999.70 担保

    pos = await db_session.scalar(
        select(VirtualPosition).where(VirtualPosition.account_id == account.id),
    )
    assert pos is not None
    assert pos.position_side == PositionSide.SHORT
    assert pos.quantity == Decimal("10")
    assert pos.avg_entry_price == Decimal("99.9700")
    assert pos.closed_at is None


@pytest.mark.asyncio
async def test_cover_profit_releases_collateral_plus_pnl(db_session: AsyncSession):
    user, account = await _acct(db_session)
    await place_market_order(
        db_session, _short(user.id, "10"),
        make_static_price_fetcher({("NVDA", "us"): Decimal("100")}),
    )
    await db_session.commit()

    # 平空 @ 80 · BUY 滑点上浮 → 80.024 · 已实现 = (99.97-80.024)×10 = 199.46
    order = await place_market_order(
        db_session, _cover(user.id, "10"),
        make_static_price_fetcher({("NVDA", "us"): Decimal("80")}),
    )
    await db_session.commit()

    assert order.status == OrderStatus.FILLED
    assert order.position_side == PositionSide.SHORT
    assert order.realized_pnl == Decimal("199.4600")

    await db_session.refresh(account)
    # 返还担保 999.70 + 已实现 199.46 → 99000.30 + 1199.16 = 100199.46
    assert account.cash_balance == Decimal("100199.4600")
    assert account.realized_pnl == Decimal("199.4600")

    pos = await db_session.scalar(
        select(VirtualPosition).where(VirtualPosition.account_id == account.id),
    )
    assert pos.quantity == Decimal("0")
    assert pos.closed_at is not None
    assert pos.realized_pnl == Decimal("199.4600")


@pytest.mark.asyncio
async def test_cover_loss_reduces_cash_no_liquidation(db_session: AsyncSession):
    user, account = await _acct(db_session)
    await place_market_order(
        db_session, _short(user.id, "10"),
        make_static_price_fetcher({("NVDA", "us"): Decimal("100")}),
    )
    await db_session.commit()

    # 逆向:价涨到 150 · 平空 fill 150.045 · 已实现 = (99.97-150.045)×10 = -500.75
    order = await place_market_order(
        db_session, _cover(user.id, "10"),
        make_static_price_fetcher({("NVDA", "us"): Decimal("150")}),
    )
    await db_session.commit()

    assert order.status == OrderStatus.FILLED
    assert order.realized_pnl == Decimal("-500.7500")
    await db_session.refresh(account)
    # 99000.30 + (999.70 - 500.75) = 99499.25(亏损 · 无强平)
    assert account.cash_balance == Decimal("99499.2500")


@pytest.mark.asyncio
async def test_partial_cover_keeps_short_active(db_session: AsyncSession):
    user, account = await _acct(db_session)
    await place_market_order(
        db_session, _short(user.id, "10"),
        make_static_price_fetcher({("NVDA", "us"): Decimal("100")}),
    )
    await db_session.commit()
    order = await place_market_order(
        db_session, _cover(user.id, "4"),
        make_static_price_fetcher({("NVDA", "us"): Decimal("80")}),
    )
    await db_session.commit()

    assert order.realized_pnl == Decimal("79.7840")  # (99.97-80.024)×4
    pos = await db_session.scalar(
        select(VirtualPosition).where(VirtualPosition.account_id == account.id),
    )
    assert pos.quantity == Decimal("6")
    assert pos.closed_at is None
    assert pos.position_side == PositionSide.SHORT


@pytest.mark.asyncio
async def test_short_add_averages_entry(db_session: AsyncSession):
    user, account = await _acct(db_session)
    await place_market_order(
        db_session, _short(user.id, "10"),
        make_static_price_fetcher({("NVDA", "us"): Decimal("100")}),
    )
    await db_session.commit()
    # 再卖空 10 @ 200(fill 199.94)· 加权 = (10×99.97 + 10×199.94)/20 = 149.955
    await place_market_order(
        db_session, _short(user.id, "10"),
        make_static_price_fetcher({("NVDA", "us"): Decimal("200")}),
    )
    await db_session.commit()
    pos = await db_session.scalar(
        select(VirtualPosition).where(VirtualPosition.account_id == account.id),
    )
    assert pos.quantity == Decimal("20")
    assert pos.avg_entry_price == Decimal("149.95500000")


@pytest.mark.asyncio
async def test_short_insufficient_collateral_rejected(db_session: AsyncSession):
    user, account = await _acct(db_session, capital="100")  # 担保不足
    order = await place_market_order(
        db_session, _short(user.id, "10"),
        make_static_price_fetcher({("NVDA", "us"): Decimal("100")}),
    )
    await db_session.commit()
    assert order.status == OrderStatus.REJECTED
    assert "担保不足" in (order.reject_reason or "")
    await db_session.refresh(account)
    assert account.cash_balance == Decimal("100.0000")  # 未扣


@pytest.mark.asyncio
async def test_cover_more_than_held_rejected(db_session: AsyncSession):
    user, _ = await _acct(db_session)
    await place_market_order(
        db_session, _short(user.id, "5"),
        make_static_price_fetcher({("NVDA", "us"): Decimal("100")}),
    )
    await db_session.commit()
    order = await place_market_order(
        db_session, _cover(user.id, "10"),
        make_static_price_fetcher({("NVDA", "us"): Decimal("80")}),
    )
    await db_session.commit()
    assert order.status == OrderStatus.REJECTED
    assert "空头持仓不足" in (order.reject_reason or "")


@pytest.mark.asyncio
async def test_cross_direction_guard_protects_long(db_session: AsyncSession):
    """已有做多仓时开空被拒(反向)· 保护现货做多不被卖空路径污染。"""
    user, _ = await _acct(db_session)
    fetcher = make_static_price_fetcher({("NVDA", "us"): Decimal("100")})
    # 先做多 10
    await place_market_order(
        db_session,
        PlaceOrderRequest(
            user_id=user.id, symbol="NVDA", market="us",
            side=OrderSide.BUY, position_side=PositionSide.LONG, quantity=Decimal("10"),
        ),
        fetcher,
    )
    await db_session.commit()
    # 再开空同标的 → 拒
    order = await place_market_order(db_session, _short(user.id, "5"), fetcher)
    await db_session.commit()
    assert order.status == OrderStatus.REJECTED
    assert "反向持仓" in (order.reject_reason or "")


@pytest.mark.asyncio
async def test_short_equity_valuation(db_session: AsyncSession):
    """空头权益估值:positions_value = 担保(qty×avg_entry)+ 浮盈((avg_entry-price)×qty)。"""
    user, account = await _acct(db_session)
    await place_market_order(
        db_session, _short(user.id, "10"),
        make_static_price_fetcher({("NVDA", "us"): Decimal("100")}),
    )
    await db_session.commit()
    # 现价 80(空头浮盈)· 估值 = 10×99.97 + (99.97-80)×10 = 999.70 + 199.70 = 1199.40
    snap = await snapshot_equity_for_account(
        db_session, account_id=account.id, market="us",
        trigger=SnapshotTrigger.ORDER_FILLED,
        price_fetcher=make_static_price_fetcher({("NVDA", "us"): Decimal("80")}),
    )
    assert snap.positions_value == Decimal("1199.4000")
    # equity = cash 99000.30 + 1199.40 = 100199.70(浮盈 +199.70)
    assert snap.equity == Decimal("100199.7000")
