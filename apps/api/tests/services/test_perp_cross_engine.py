"""全仓(cross)永续虚拟引擎 pytest · ADR-0027 MC-2。

🔴 红线:全程虚拟资金 · 纯虚拟撮合数值校验。

覆盖:
- 开全仓:保证金【不划出】cash(只扣 fee)· margin_mode='cross' · liquidation_price=0
- 共担池可用保证金校验(开仓 affordability · 超可用 → 拒单)
- 平全仓:只把 realized_net 计回 cash(没有"返还保证金"项 —— 与逐仓的关键差异)
- 加仓加权均价 · 反手
- 🔴 全仓 + 逐仓【同账户不同 symbol 共存】互不干扰 + 逐仓强平 worker 过滤仍正确
- 🔴 跨用户隔离:全仓只动传入 user_id 账户
- DP-7:同 symbol 已有逐仓活仓 → 全仓开仓拒绝
- 资金费对全仓天然生效(settle_funding 不改一行)

本期【不测全仓强平】—— 强平是 MC-3。
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import (
    MarginMode,
    OrderStatus,
    PerpAction,
    PerpSide,
    VirtualPerpPosition,
)
from app.services.virtual_trading.perp_cross_engine import (
    CloseCrossRequest,
    OpenCrossRequest,
    close_cross_position,
    open_cross_position,
)
from tests.factories import (
    make_perp_price_fetcher,
    make_user,
    make_virtual_account,
)


async def _crypto_account(db: AsyncSession, capital: str = "100000"):
    user = await make_user(db)
    account = await make_virtual_account(
        db, user_id=user.id, market="crypto", initial_capital=Decimal(capital),
    )
    await db.commit()
    return user, account


def _isolated_scan_ids(positions: list[VirtualPerpPosition]) -> set[int]:
    """复刻 MC-1 逐仓强平 worker 的过滤谓词命中集(account 内)。"""
    return {
        p.id
        for p in positions
        if p.closed_at is None and p.margin_mode == MarginMode.ISOLATED
    }


# ============================================================================
# 开全仓:保证金不划出 · 只扣 fee
# ============================================================================


@pytest.mark.asyncio
async def test_open_cross_fresh_margin_not_drawn(db_session: AsyncSession):
    user, account = await _crypto_account(db_session)
    fetcher = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})

    order = await open_cross_position(
        db_session,
        OpenCrossRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
        ),
        fetcher,
    )
    await db_session.commit()

    assert order.status == OrderStatus.FILLED
    assert order.action == PerpAction.OPEN_LONG
    # fill = 30000 × 1.001 = 30030 · notional 30030 · fee 30030×0.0005 = 15.015
    assert order.price == Decimal("30030.00000000")
    assert order.fee == Decimal("15.0150")
    # 🔴 只扣 fee · 保证金(3003)不划出 cash:100000 − 15.015 = 99984.985
    await db_session.refresh(account)
    assert account.cash_balance == Decimal("99984.9850")

    pos = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account.id,
        ),
    )
    assert pos is not None
    assert pos.margin_mode == MarginMode.CROSS
    assert pos.margin_mode == "cross"
    # initial_margin = 保证金"要求"(notional/lev = 3003)· 非已划出现金
    assert pos.initial_margin == Decimal("3003.0000")
    # 全仓不用每仓强平价 → 占位 0(MC-1 逐仓 worker 已按 mode 过滤,不会误扫)
    assert pos.liquidation_price == Decimal("0.00000000")


@pytest.mark.asyncio
async def test_cross_open_blocked_when_over_available(db_session: AsyncSession):
    """共担池可用保证金不足 → 拒单(lev1 让保证金要求=名义额)。"""
    user, account = await _crypto_account(db_session, capital="5000")
    fetcher = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})

    order = await open_cross_position(
        db_session,
        OpenCrossRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=1, quantity=Decimal("1"),  # 需 ~30030 保证金 · 可用仅 5000
        ),
        fetcher,
    )
    await db_session.commit()

    assert order.status == OrderStatus.REJECTED
    assert "可用保证金不足" in (order.reject_reason or "")
    # 拒单不建仓、不扣钱
    await db_session.refresh(account)
    assert account.cash_balance == Decimal("5000.0000")
    cnt = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account.id,
        ),
    )
    assert cnt is None


# ============================================================================
# 平全仓:只把 realized_net 计回 cash(无"返还保证金"项)
# ============================================================================


@pytest.mark.asyncio
async def test_close_cross_credits_only_realized_net(db_session: AsyncSession):
    user, account = await _crypto_account(db_session)
    fetcher = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    await open_cross_position(
        db_session,
        OpenCrossRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
        ),
        fetcher,
    )
    await db_session.commit()
    # 开后 cash = 99984.9850(只扣了 fee)

    # mark 涨到 31000 · 平多→卖出 滑点下浮:31000×0.999 = 30969
    close_fetcher = make_perp_price_fetcher({"BTCUSDT": Decimal("31000")})
    result = await close_cross_position(
        db_session,
        CloseCrossRequest(user_id=user.id, symbol="BTCUSDT", close_all=True),
        close_fetcher,
    )
    await db_session.commit()

    assert result.status == OrderStatus.FILLED
    # gross =(30969−30030)×1 = 939 · fee_close = 30969×0.0005 = 15.4845
    # realized_net = 939 − 15.4845 = 923.5155
    assert result.realized_pnl == Decimal("923.5155")
    # 🔴 cash = 99984.985 + 923.5155 = 100908.5005(只加 realized_net · 不加 3003 保证金)
    await db_session.refresh(account)
    assert account.cash_balance == Decimal("100908.5005")
    assert account.realized_pnl == Decimal("923.5155")

    pos = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account.id,
        ),
    )
    assert pos is not None
    assert pos.closed_at is not None  # 全平软删
    assert pos.quantity == Decimal("0")


@pytest.mark.asyncio
async def test_add_to_cross_weighted_entry(db_session: AsyncSession):
    user, account = await _crypto_account(db_session)
    f1 = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    await open_cross_position(
        db_session,
        OpenCrossRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
        ),
        f1,
    )
    await db_session.commit()

    f2 = make_perp_price_fetcher({"BTCUSDT": Decimal("32000")})  # fill 32032
    await open_cross_position(
        db_session,
        OpenCrossRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
        ),
        f2,
    )
    await db_session.commit()

    pos = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account.id,
            VirtualPerpPosition.closed_at.is_(None),
        ),
    )
    assert pos is not None
    assert pos.quantity == Decimal("2")
    # 加权均价 =(30030 + 32032)/2 = 31031
    assert pos.entry_price == Decimal("31031.00000000")
    # initial_margin 要求累加:3003 + 3203.2 = 6206.2
    assert pos.initial_margin == Decimal("6206.2000")
    assert pos.margin_mode == MarginMode.CROSS


@pytest.mark.asyncio
async def test_reverse_cross_flips_side(db_session: AsyncSession):
    user, account = await _crypto_account(db_session)
    f = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    await open_cross_position(
        db_session,
        OpenCrossRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
        ),
        f,
    )
    await db_session.commit()

    # 反向开空 qty3 > 持多 1 → 平掉 1 + 反手开空 2
    await open_cross_position(
        db_session,
        OpenCrossRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.SHORT,
            leverage=10, quantity=Decimal("3"),
        ),
        f,
    )
    await db_session.commit()

    pos = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account.id,
            VirtualPerpPosition.closed_at.is_(None),
        ),
    )
    assert pos is not None
    assert pos.side == PerpSide.SHORT
    assert pos.quantity == Decimal("2")
    assert pos.margin_mode == MarginMode.CROSS


# ============================================================================
# 🔴 全仓 + 逐仓 同账户不同 symbol 共存(DP-1 per-symbol)
# ============================================================================


@pytest.mark.asyncio
async def test_cross_and_isolated_coexist_same_account(db_session: AsyncSession):
    """同账户:ETH 走逐仓、BTC 走全仓 · 互不干扰 · 逐仓 worker 过滤仍只扫逐仓。"""
    from app.services.virtual_trading.perp_engine import (
        OpenPerpRequest,
        open_perp_position,
    )

    user, account = await _crypto_account(db_session)

    # ETH 逐仓(走逐仓引擎)· lev5 qty1 mark2000 → 划出保证金 400.4 + fee 1.001
    iso_fetcher = make_perp_price_fetcher({"ETHUSDT": Decimal("2000")})
    await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="ETHUSDT", side=PerpSide.LONG,
            leverage=5, quantity=Decimal("1"),
        ),
        iso_fetcher,
    )
    await db_session.commit()
    await db_session.refresh(account)
    assert account.cash_balance == Decimal("99598.5990")  # 100000 − 401.401

    # BTC 全仓(走全仓引擎)· lev10 qty0.1 mark30000 → 只扣 fee 1.5015
    cross_fetcher = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    await open_cross_position(
        db_session,
        OpenCrossRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("0.1"),
        ),
        cross_fetcher,
    )
    await db_session.commit()
    await db_session.refresh(account)
    # 99598.599 − 1.5015 = 99597.0975(全仓只扣 fee)
    assert account.cash_balance == Decimal("99597.0975")

    positions = list(
        (
            await db_session.scalars(
                select(VirtualPerpPosition).where(
                    VirtualPerpPosition.account_id == account.id,
                ),
            )
        ).all(),
    )
    by_sym = {p.symbol: p for p in positions}
    assert by_sym["ETHUSDT"].margin_mode == MarginMode.ISOLATED
    assert by_sym["BTCUSDT"].margin_mode == MarginMode.CROSS
    # 逐仓有每仓强平价;全仓 liq 占位 0
    assert by_sym["ETHUSDT"].liquidation_price > 0
    assert by_sym["BTCUSDT"].liquidation_price == Decimal("0.00000000")

    # 🔴 MC-1 逐仓 worker 过滤:只命中 ETH(逐仓),BTC(全仓)被排除 → 不会被逐仓误扫
    scanned = _isolated_scan_ids(positions)
    assert by_sym["ETHUSDT"].id in scanned
    assert by_sym["BTCUSDT"].id not in scanned


@pytest.mark.asyncio
async def test_cross_open_rejected_when_symbol_has_isolated(db_session: AsyncSession):
    """DP-7:同 symbol 已有逐仓活仓 → 全仓开仓拒绝,且逐仓仓纹丝不动。"""
    from app.services.virtual_trading.perp_engine import (
        OpenPerpRequest,
        open_perp_position,
    )

    user, account = await _crypto_account(db_session)
    f = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=5, quantity=Decimal("1"),
        ),
        f,
    )
    await db_session.commit()
    iso_pos = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account.id,
        ),
    )
    assert iso_pos is not None
    iso_margin_before = iso_pos.initial_margin

    order = await open_cross_position(
        db_session,
        OpenCrossRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
        ),
        f,
    )
    await db_session.commit()

    assert order.status == OrderStatus.REJECTED
    assert "不可混用保证金模式" in (order.reject_reason or "")
    # 逐仓仓未被改成 cross、保证金没动
    await db_session.refresh(iso_pos)
    assert iso_pos.margin_mode == MarginMode.ISOLATED
    assert iso_pos.initial_margin == iso_margin_before


@pytest.mark.asyncio
async def test_cross_cross_user_isolation(db_session: AsyncSession):
    """🔴 全仓只动传入 user_id 的账户 · A 开全仓,B 一分没动、没仓。"""
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

    order = await open_cross_position(
        db_session,
        OpenCrossRequest(
            user_id=user_a.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
        ),
        f,
    )
    await db_session.commit()
    assert order.status == OrderStatus.FILLED

    await db_session.refresh(acct_a)
    await db_session.refresh(acct_b)
    assert acct_a.cash_balance < Decimal("100000")  # A 扣了 fee
    assert acct_b.cash_balance == cash_b_before       # B 一分没动
    b_pos = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == acct_b.id,
        ),
    )
    assert b_pos is None  # B 没有任何仓


# ============================================================================
# 资金费对全仓天然兼容(perp_funding.py 不改一行)
# ============================================================================


@pytest.mark.asyncio
async def test_funding_applies_to_cross_position(db_session: AsyncSession):
    from app.models.perp import VirtualPerpFunding
    from app.services.virtual_trading.perp_funding import (
        PremiumSnapshot,
        settle_funding,
    )

    user, account = await _crypto_account(db_session)
    f = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    await open_cross_position(
        db_session,
        OpenCrossRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
        ),
        f,
    )
    await db_session.commit()
    await db_session.refresh(account)
    cash_before = account.cash_balance

    # rate>0 · 多头付:payment = +1 × 0.0001 × 30000 × 1 = 3 · 整点 0 对齐 8h 周期
    now = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    snaps = {
        "BTCUSDT": PremiumSnapshot(
            mark_price=Decimal("30000"), funding_rate=Decimal("0.0001"),
            funding_interval_hours=8,
        ),
    }
    stats = await settle_funding(db_session, snaps, now=now)
    await db_session.commit()

    assert stats["settled"] == 1
    await db_session.refresh(account)
    assert account.cash_balance == cash_before - Decimal("3.0000")  # 多头付 3 USDT

    pos = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account.id,
        ),
    )
    assert pos is not None
    assert pos.funding_paid == Decimal("3.0000")
    funding_rows = list(
        (
            await db_session.scalars(
                select(VirtualPerpFunding).where(
                    VirtualPerpFunding.account_id == account.id,
                ),
            )
        ).all(),
    )
    assert len(funding_rows) == 1
