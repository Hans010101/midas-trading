"""接入分流层 pytest · ADR-0027 MC-4 · perp_dispatcher。

🔴 红线:全程虚拟资金 · 分流不含撮合数学。

核心证明:
- flat + preferred → 走对应引擎(isolated/cross)
- 有活仓 + preferred==活仓.mode → 走活仓 mode 引擎(加仓/反向减仓正确分流)
- 🔴 有活仓 + preferred≠活仓.mode → 拒单(DP-7 守护 · 防 cross 仓被送进 isolated 引擎误算)
- 平仓按活仓 mode 自动分流 · cross 仓走 close_cross_position、isolated 仓走 close_perp_position
- 跨用户隔离:user_id 仅落到自己账户
- 零回归:默认 preferred=isolated 时行为 == MC-3 之前直调 perp_engine
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import (
    MarginMode,
    OrderStatus,
    PerpSide,
    VirtualPerpPosition,
)
from app.services.virtual_trading.perp_dispatcher import (
    route_close_perp,
    route_open_perp,
)
from tests.factories import (
    make_perp_price_fetcher,
    make_user,
    make_virtual_account,
)


async def _crypto_account(db: AsyncSession, capital: str = "100000"):
    user = await make_user(db)
    acct = await make_virtual_account(
        db, user_id=user.id, market="crypto", initial_capital=Decimal(capital),
    )
    await db.commit()
    return user, acct


async def _only_position(db: AsyncSession, account_id: int) -> VirtualPerpPosition:
    pos = await db.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account_id,
            VirtualPerpPosition.closed_at.is_(None),
        ),
    )
    assert pos is not None
    return pos


# ============================================================================
# flat 开仓:按 preferred 分流
# ============================================================================


@pytest.mark.asyncio
async def test_flat_preferred_isolated_routes_to_isolated_engine(db_session: AsyncSession):
    """flat + preferred=isolated → 落到 perp_engine,产物 margin_mode='isolated'。"""
    user, acct = await _crypto_account(db_session)
    f = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})

    order = await route_open_perp(
        db_session, user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
        leverage=10, margin=None, quantity=Decimal("1"),
        preferred_mode=MarginMode.ISOLATED, get_mark_price=f,
    )
    await db_session.commit()
    assert order.status == OrderStatus.FILLED
    pos = await _only_position(db_session, acct.id)
    assert pos.margin_mode == MarginMode.ISOLATED
    # 逐仓:保证金从 cash 划出 → cash 显著下降
    await db_session.refresh(acct)
    assert acct.cash_balance < Decimal("100000")  # 划了 margin+fee
    # 逐仓的 liquidation_price 真算
    assert pos.liquidation_price > Decimal("0")


@pytest.mark.asyncio
async def test_flat_preferred_cross_routes_to_cross_engine(db_session: AsyncSession):
    """flat + preferred=cross → 落到 perp_cross_engine,只扣 fee、liq=0。"""
    user, acct = await _crypto_account(db_session)
    f = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})

    order = await route_open_perp(
        db_session, user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
        leverage=10, margin=None, quantity=Decimal("1"),
        preferred_mode=MarginMode.CROSS, get_mark_price=f,
    )
    await db_session.commit()
    assert order.status == OrderStatus.FILLED
    pos = await _only_position(db_session, acct.id)
    assert pos.margin_mode == MarginMode.CROSS
    assert pos.liquidation_price == Decimal("0.00000000")  # cross 占位 0
    # cross:只扣 fee(15.015),margin 3003 不动 → cash = 100000 − 15.015
    await db_session.refresh(acct)
    assert acct.cash_balance == Decimal("99984.9850")


# ============================================================================
# 有活仓:按活仓 mode 分流(加仓 / 反向减仓走对应引擎)
# ============================================================================


@pytest.mark.asyncio
async def test_existing_isolated_add_routes_to_isolated(db_session: AsyncSession):
    """同向加仓 · 活仓 isolated → dispatcher 仍走 isolated 引擎,初始保证金累加。"""
    user, acct = await _crypto_account(db_session)
    f = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    await route_open_perp(
        db_session, user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
        leverage=10, margin=None, quantity=Decimal("1"),
        preferred_mode=MarginMode.ISOLATED, get_mark_price=f,
    )
    await db_session.commit()

    # 同向加仓(preferred 也 isolated,与活仓一致)
    await route_open_perp(
        db_session, user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
        leverage=10, margin=None, quantity=Decimal("1"),
        preferred_mode=MarginMode.ISOLATED, get_mark_price=f,
    )
    await db_session.commit()
    pos = await _only_position(db_session, acct.id)
    assert pos.margin_mode == MarginMode.ISOLATED
    assert pos.quantity == Decimal("2")  # 加仓后 qty=2


@pytest.mark.asyncio
async def test_existing_cross_add_routes_to_cross(db_session: AsyncSession):
    """同向加仓 · 活仓 cross → dispatcher 仍走 cross 引擎,只扣 fee。"""
    user, acct = await _crypto_account(db_session)
    f = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    await route_open_perp(
        db_session, user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
        leverage=10, margin=None, quantity=Decimal("1"),
        preferred_mode=MarginMode.CROSS, get_mark_price=f,
    )
    await db_session.commit()
    cash_after_first = (await db_session.scalar(
        select(type(acct).cash_balance).where(type(acct).id == acct.id),
    ))

    await route_open_perp(
        db_session, user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
        leverage=10, margin=None, quantity=Decimal("1"),
        preferred_mode=MarginMode.CROSS, get_mark_price=f,
    )
    await db_session.commit()
    pos = await _only_position(db_session, acct.id)
    assert pos.margin_mode == MarginMode.CROSS
    assert pos.quantity == Decimal("2")
    # 加仓只扣第二次的 fee 15.015 · cash 比加仓前减 15.015(margin 不动)
    await db_session.refresh(acct)
    assert acct.cash_balance == cash_after_first - Decimal("15.0150")


# ============================================================================
# 🔴 DP-7:活仓与偏好模式不一致 → 拒单(防 cross 仓被送进逐仓引擎误算)
# ============================================================================


@pytest.mark.asyncio
async def test_existing_isolated_preferred_cross_rejects(db_session: AsyncSession):
    """活仓 isolated,偏好 cross → 拒单 · isolated 仓纹丝不动。"""
    user, acct = await _crypto_account(db_session)
    f = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    await route_open_perp(
        db_session, user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
        leverage=10, margin=None, quantity=Decimal("1"),
        preferred_mode=MarginMode.ISOLATED, get_mark_price=f,
    )
    await db_session.commit()
    iso_pos = await _only_position(db_session, acct.id)
    iso_margin_before = iso_pos.initial_margin

    order = await route_open_perp(
        db_session, user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
        leverage=10, margin=None, quantity=Decimal("1"),
        preferred_mode=MarginMode.CROSS, get_mark_price=f,
    )
    # 不 commit · 拒单 sentinel
    assert order.status == OrderStatus.REJECTED
    assert "逐仓" in (order.reject_reason or "")
    assert "全仓" in (order.reject_reason or "")
    # 活仓 isolated 完全没被碰
    await db_session.refresh(iso_pos)
    assert iso_pos.margin_mode == MarginMode.ISOLATED
    assert iso_pos.initial_margin == iso_margin_before


@pytest.mark.asyncio
async def test_existing_cross_preferred_isolated_rejects(db_session: AsyncSession):
    """🔴 关键:活仓 cross,偏好 isolated → 拒单 · 防 cross 仓被 perp_engine 误算。"""
    user, acct = await _crypto_account(db_session)
    f = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    await route_open_perp(
        db_session, user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
        leverage=10, margin=None, quantity=Decimal("1"),
        preferred_mode=MarginMode.CROSS, get_mark_price=f,
    )
    await db_session.commit()
    cross_pos = await _only_position(db_session, acct.id)
    cross_qty_before = cross_pos.quantity
    cross_margin_before = cross_pos.initial_margin

    order = await route_open_perp(
        db_session, user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
        leverage=10, margin=None, quantity=Decimal("1"),
        preferred_mode=MarginMode.ISOLATED, get_mark_price=f,
    )
    assert order.status == OrderStatus.REJECTED
    assert "全仓" in (order.reject_reason or "")
    # cross 活仓 完全没被 perp_engine 算成 isolated
    await db_session.refresh(cross_pos)
    assert cross_pos.margin_mode == MarginMode.CROSS
    assert cross_pos.quantity == cross_qty_before
    assert cross_pos.initial_margin == cross_margin_before
    assert cross_pos.liquidation_price == Decimal("0.00000000")


# ============================================================================
# 平仓按活仓 mode 自动分流
# ============================================================================


@pytest.mark.asyncio
async def test_close_routes_by_position_margin_mode(db_session: AsyncSession):
    """同账户两个 symbol:cross BTC 走 close_cross,isolated ETH 走 close_perp。"""
    user, acct = await _crypto_account(db_session)
    f = make_perp_price_fetcher({
        "BTCUSDT": Decimal("30000"),
        "ETHUSDT": Decimal("2000"),
    })
    # 开 isolated ETH
    await route_open_perp(
        db_session, user_id=user.id, symbol="ETHUSDT", side=PerpSide.LONG,
        leverage=5, margin=None, quantity=Decimal("1"),
        preferred_mode=MarginMode.ISOLATED, get_mark_price=f,
    )
    # 开 cross BTC
    await route_open_perp(
        db_session, user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
        leverage=10, margin=None, quantity=Decimal("1"),
        preferred_mode=MarginMode.CROSS, get_mark_price=f,
    )
    await db_session.commit()

    # 平 cross BTC(同一 mark,平掉)
    close_btc = await route_close_perp(
        db_session, user_id=user.id, symbol="BTCUSDT",
        quantity=None, close_all=True, get_mark_price=f,
    )
    await db_session.commit()
    assert close_btc.status == OrderStatus.FILLED

    btc_pos = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == acct.id,
            VirtualPerpPosition.symbol == "BTCUSDT",
        ),
    )
    assert btc_pos is not None
    assert btc_pos.margin_mode == MarginMode.CROSS  # 历史行 mode 不变
    assert btc_pos.closed_at is not None  # 已平

    # 平 isolated ETH
    close_eth = await route_close_perp(
        db_session, user_id=user.id, symbol="ETHUSDT",
        quantity=None, close_all=True, get_mark_price=f,
    )
    await db_session.commit()
    assert close_eth.status == OrderStatus.FILLED
    eth_pos = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == acct.id,
            VirtualPerpPosition.symbol == "ETHUSDT",
        ),
    )
    assert eth_pos is not None
    assert eth_pos.margin_mode == MarginMode.ISOLATED
    assert eth_pos.closed_at is not None


@pytest.mark.asyncio
async def test_close_no_position_returns_engine_reject(db_session: AsyncSession):
    """无活仓 → 走 isolated 引擎的"无活仓可平"标准拒单(行为同 MC-3 之前)。"""
    user, _acct = await _crypto_account(db_session)
    f = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    order = await route_close_perp(
        db_session, user_id=user.id, symbol="BTCUSDT",
        quantity=None, close_all=True, get_mark_price=f,
    )
    assert order.status == OrderStatus.REJECTED
    assert "无活仓可平" in (order.reject_reason or "")


# ============================================================================
# 跨用户隔离
# ============================================================================


@pytest.mark.asyncio
async def test_dispatcher_cross_user_isolation(db_session: AsyncSession):
    """A 走 dispatcher 开仓 · B 账户一字未动。"""
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    acct_a = await make_virtual_account(
        db_session, user_id=user_a.id, market="crypto", initial_capital=Decimal("100000"),
    )
    acct_b = await make_virtual_account(
        db_session, user_id=user_b.id, market="crypto", initial_capital=Decimal("100000"),
    )
    await db_session.commit()
    cash_b_before = acct_b.cash_balance
    f = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})

    await route_open_perp(
        db_session, user_id=user_a.id, symbol="BTCUSDT", side=PerpSide.LONG,
        leverage=10, margin=None, quantity=Decimal("1"),
        preferred_mode=MarginMode.CROSS, get_mark_price=f,
    )
    await db_session.commit()
    # A 有仓
    a_pos = await _only_position(db_session, acct_a.id)
    assert a_pos.margin_mode == MarginMode.CROSS
    # B 没动
    await db_session.refresh(acct_b)
    assert acct_b.cash_balance == cash_b_before
    b_pos = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == acct_b.id,
        ),
    )
    assert b_pos is None
