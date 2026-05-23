"""加密永续合约虚拟撮合引擎 pytest · ADR-0019 v2 · M2-C.1。

🔴 红线:全程虚拟资金 · 这些只是虚拟撮合数值校验。

覆盖:
- 开多 / 开空 新仓:保证金扣减 + 强平价 + 订单 filled
- 加仓加权均价 + 同杠杆校验
- 平仓(部分 / 全部)盈亏计算 + 软删
- 反手(open opposite > 持仓)
- 强平触发 + 逐仓亏损地板
- 杠杆 / 保证金 / 手续费数值
- 边界:保证金不足 / 超杠杆 / 无活仓平仓 / 未激活市场
- perp_fees 纯函数(强平价 / 滑点 / 盈亏)
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import (
    OrderStatus,
    PerpAction,
    PerpCloseReason,
    PerpSide,
    VirtualPerpPosition,
)
from app.services.virtual_trading.perp_engine import (
    ClosePerpRequest,
    OpenPerpRequest,
    close_perp_position,
    liquidate_position,
    open_perp_position,
)
from app.services.virtual_trading.perp_fees import (
    apply_perp_slippage,
    liquidation_price,
    perp_taker_fee,
    realized_pnl_gross,
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


# ============================================================================
# 开仓
# ============================================================================


@pytest.mark.asyncio
async def test_open_long_fresh(db_session: AsyncSession):
    user, account = await _crypto_account(db_session)
    fetcher = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})

    order = await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
        ),
        fetcher,
    )
    await db_session.commit()

    assert order.status == OrderStatus.FILLED
    assert order.action == PerpAction.OPEN_LONG
    # 滑点 10bp:30000 × 1.001 = 30030
    assert order.price == Decimal("30030.00000000")
    assert order.notional == Decimal("30030.0000")
    assert order.margin_delta == Decimal("3003.0000")  # 30030 / 10
    assert order.fee == Decimal("15.0150")  # 30030 × 0.0005

    # 余额:100000 − (3003 + 15.015) = 96981.985
    await db_session.refresh(account)
    assert account.cash_balance == Decimal("96981.9850")

    pos = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account.id,
        ),
    )
    assert pos is not None
    assert pos.side == PerpSide.LONG
    assert pos.quantity == Decimal("1")
    assert pos.entry_price == Decimal("30030.00000000")
    assert pos.initial_margin == Decimal("3003.0000")
    assert pos.closed_at is None
    # 强平价 long = 30030 × (1 − 1/10 + 0.005) = 30030 × 0.905 = 27177.15
    assert pos.liquidation_price == Decimal("27177.15000000")


@pytest.mark.asyncio
async def test_open_short_fresh(db_session: AsyncSession):
    user, account = await _crypto_account(db_session)
    fetcher = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})

    order = await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.SHORT,
            leverage=5, quantity=Decimal("1"),
        ),
        fetcher,
    )
    await db_session.commit()

    assert order.status == OrderStatus.FILLED
    assert order.action == PerpAction.OPEN_SHORT
    # 开空 = 卖出,滑点下浮:30000 × 0.999 = 29970
    assert order.price == Decimal("29970.00000000")
    assert order.margin_delta == Decimal("5994.0000")  # 29970 / 5

    pos = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account.id,
        ),
    )
    assert pos is not None
    assert pos.side == PerpSide.SHORT
    # 强平价 short = 29970 × (1 + 1/5 − 0.005) = 29970 × 1.195 = 35814.15
    assert pos.liquidation_price == Decimal("35814.15000000")


@pytest.mark.asyncio
async def test_open_by_margin_derives_quantity(db_session: AsyncSession):
    """按保证金开仓 · qty = margin × lev / fill_price。"""
    user, account = await _crypto_account(db_session)
    fetcher = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})

    order = await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, margin=Decimal("3000"),
        ),
        fetcher,
    )
    await db_session.commit()

    assert order.status == OrderStatus.FILLED
    # fill=30030 · qty = 3000 × 10 / 30030 = 0.99900...
    expected_qty = (Decimal("3000") * 10 / Decimal("30030")).quantize(
        Decimal("0.00000001"),
    )
    assert order.quantity == expected_qty
    # 锁定保证金 = 投入的 margin
    assert order.margin_delta == Decimal("3000.0000")


@pytest.mark.asyncio
async def test_open_insufficient_margin_rejected(db_session: AsyncSession):
    user, account = await _crypto_account(db_session, capital="100")
    fetcher = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})

    order = await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
        ),
        fetcher,
    )
    await db_session.commit()

    assert order.status == OrderStatus.REJECTED
    assert "保证金不足" in (order.reject_reason or "")
    await db_session.refresh(account)
    assert account.cash_balance == Decimal("100.0000")


@pytest.mark.asyncio
async def test_leverage_out_of_range_rejected(db_session: AsyncSession):
    user, _ = await _crypto_account(db_session)
    fetcher = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})

    order = await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=50, quantity=Decimal("1"),
        ),
        fetcher,
    )
    await db_session.commit()
    assert order.status == OrderStatus.REJECTED
    assert "杠杆" in (order.reject_reason or "")


@pytest.mark.asyncio
async def test_unactivated_market_rejected(db_session: AsyncSession):
    """没激活 crypto 子账户 → 拒单 + sentinel(id None)。"""
    user = await make_user(db_session)
    await db_session.commit()
    fetcher = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})

    order = await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
        ),
        fetcher,
    )
    assert order.status == OrderStatus.REJECTED
    assert "未设置" in (order.reject_reason or "")
    assert order.id is None


# ============================================================================
# 加仓
# ============================================================================


@pytest.mark.asyncio
async def test_add_to_long_weighted_entry(db_session: AsyncSession):
    user, account = await _crypto_account(db_session)
    f1 = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
        ),
        f1,
    )
    await db_session.commit()

    # 涨价后加仓 1 @ 40000(fill 40040)
    f2 = make_perp_price_fetcher({"BTCUSDT": Decimal("40000")})
    await open_perp_position(
        db_session,
        OpenPerpRequest(
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
    # 加权 = (1×30030 + 1×40040) / 2 = 35035
    assert pos.entry_price == Decimal("35035.00000000")
    assert pos.initial_margin == Decimal("7007.0000")  # 3003 + 4004


@pytest.mark.asyncio
async def test_add_to_different_leverage_rejected(db_session: AsyncSession):
    user, _ = await _crypto_account(db_session)
    f = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
        ),
        f,
    )
    await db_session.commit()

    order = await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=5, quantity=Decimal("1"),
        ),
        f,
    )
    await db_session.commit()
    assert order.status == OrderStatus.REJECTED
    assert "杠杆需与现有持仓一致" in (order.reject_reason or "")


# ============================================================================
# 平仓
# ============================================================================


@pytest.mark.asyncio
async def test_close_long_full_profit(db_session: AsyncSession):
    user, account = await _crypto_account(db_session)
    f_open = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
        ),
        f_open,
    )
    await db_session.commit()

    # 涨到 33000 全平(平多=卖出,fill 33000×0.999=32967)
    f_close = make_perp_price_fetcher({"BTCUSDT": Decimal("33000")})
    order = await close_perp_position(
        db_session,
        ClosePerpRequest(user_id=user.id, symbol="BTCUSDT", close_all=True),
        f_close,
    )
    await db_session.commit()

    assert order.status == OrderStatus.FILLED
    assert order.action == PerpAction.CLOSE_LONG
    # gross = (32967 − 30030) × 1 = 2937 · fee = 32967×0.0005 = 16.4835
    # realized_net = 2937 − 16.4835 = 2920.5165
    assert order.realized_pnl == Decimal("2920.5165")

    pos = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account.id,
        ),
    )
    assert pos is not None
    assert pos.quantity == Decimal("0")
    assert pos.closed_at is not None
    assert pos.close_reason == PerpCloseReason.MANUAL

    # 余额:96981.985(开后) + 释放保证金 3003 + 已实现 2920.5165 = 102905.5015
    await db_session.refresh(account)
    assert account.cash_balance == Decimal("102905.5015")
    assert account.realized_pnl == Decimal("2920.5165")


@pytest.mark.asyncio
async def test_close_partial_keeps_position(db_session: AsyncSession):
    user, account = await _crypto_account(db_session)
    f_open = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("2"),
        ),
        f_open,
    )
    await db_session.commit()

    f_close = make_perp_price_fetcher({"BTCUSDT": Decimal("33000")})
    order = await close_perp_position(
        db_session,
        ClosePerpRequest(user_id=user.id, symbol="BTCUSDT", quantity=Decimal("1")),
        f_close,
    )
    await db_session.commit()

    assert order.status == OrderStatus.FILLED
    pos = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account.id,
            VirtualPerpPosition.closed_at.is_(None),
        ),
    )
    assert pos is not None
    assert pos.quantity == Decimal("1")  # 还剩 1
    # 释放一半保证金:开仓 margin = 2×30030/10 = 6006 → 平 1 释放 3003
    assert pos.initial_margin == Decimal("3003.0000")
    # 部分平不改强平价
    assert pos.liquidation_price == Decimal("27177.15000000")


@pytest.mark.asyncio
async def test_close_no_position_rejected(db_session: AsyncSession):
    user, _ = await _crypto_account(db_session)
    f = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    order = await close_perp_position(
        db_session,
        ClosePerpRequest(user_id=user.id, symbol="BTCUSDT", close_all=True),
        f,
    )
    await db_session.commit()
    assert order.status == OrderStatus.REJECTED
    assert "无活仓" in (order.reject_reason or "")


@pytest.mark.asyncio
async def test_short_close_profit_on_drop(db_session: AsyncSession):
    user, account = await _crypto_account(db_session)
    f_open = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.SHORT,
            leverage=5, quantity=Decimal("1"),
        ),
        f_open,
    )
    await db_session.commit()

    # 跌到 27000 平空(平空=买回,fill 27000×1.001=27027)
    f_close = make_perp_price_fetcher({"BTCUSDT": Decimal("27000")})
    order = await close_perp_position(
        db_session,
        ClosePerpRequest(user_id=user.id, symbol="BTCUSDT", close_all=True),
        f_close,
    )
    await db_session.commit()

    # entry 29970 · gross = (29970 − 27027) × 1 = 2943 · fee 27027×0.0005=13.5135
    # realized = 2943 − 13.5135 = 2929.4865
    assert order.realized_pnl == Decimal("2929.4865")
    await db_session.refresh(account)
    assert account.realized_pnl == Decimal("2929.4865")


# ============================================================================
# 反手
# ============================================================================


@pytest.mark.asyncio
async def test_flip_long_to_short(db_session: AsyncSession):
    """持多 1 · 开空 3 → 平多 1 + 开空 2(净持空 2)。"""
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

    order = await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.SHORT,
            leverage=5, quantity=Decimal("3"),
        ),
        f,
    )
    await db_session.commit()

    # 返回的是 open_short(剩余 2)
    assert order.status == OrderStatus.FILLED
    assert order.action == PerpAction.OPEN_SHORT
    assert order.quantity == Decimal("2")

    # 活仓:净持空 2
    active = await db_session.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account.id,
            VirtualPerpPosition.closed_at.is_(None),
        ),
    )
    assert active is not None
    assert active.side == PerpSide.SHORT
    assert active.quantity == Decimal("2")

    # 原多仓应已进历史、被平
    closed = (
        await db_session.scalars(
            select(VirtualPerpPosition).where(
                VirtualPerpPosition.account_id == account.id,
                VirtualPerpPosition.closed_at.is_not(None),
            ),
        )
    ).all()
    assert len(closed) == 1
    assert closed[0].side == PerpSide.LONG


# ============================================================================
# 强平
# ============================================================================


@pytest.mark.asyncio
async def test_liquidation_long(db_session: AsyncSession):
    """多仓 mark 触及强平价 → 强平 · 亏损封顶 = 保证金。"""
    user, account = await _crypto_account(db_session)
    f = make_perp_price_fetcher({"BTCUSDT": Decimal("30000")})
    await open_perp_position(
        db_session,
        OpenPerpRequest(
            user_id=user.id, symbol="BTCUSDT", side=PerpSide.LONG,
            leverage=10, quantity=Decimal("1"),
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
    # mark 跌破强平价(27177.15)→ 用 27000 强平
    order = await liquidate_position(db_session, pos, Decimal("27000"))
    await db_session.commit()

    assert order.status == OrderStatus.FILLED
    assert order.action == PerpAction.CLOSE_LONG
    assert order.is_liquidation is True
    # 逐仓地板:亏损 = −保证金 3003(不穿仓)
    assert order.realized_pnl == Decimal("-3003.0000")

    await db_session.refresh(pos)
    assert pos.closed_at is not None
    assert pos.close_reason == PerpCloseReason.LIQUIDATED

    # 余额:开后 96981.985 + (释放 3003 + 已实现 −3003) = 96981.985(亏掉全部保证金 + 开仓费)
    await db_session.refresh(account)
    assert account.cash_balance == Decimal("96981.9850")
    assert account.realized_pnl == Decimal("-3003.0000")


# ============================================================================
# perp_fees 纯函数
# ============================================================================


def test_liquidation_price_formula():
    # long:30000 × (1 − 1/10 + 0.005) = 27150
    assert liquidation_price(Decimal("30000"), 10, PerpSide.LONG) == Decimal(
        "27150.00000000",
    )
    # short:30000 × (1 + 1/10 − 0.005) = 32850
    assert liquidation_price(Decimal("30000"), 10, PerpSide.SHORT) == Decimal(
        "32850.00000000",
    )
    # 1x long:30000 × (1 − 1 + 0.005) = 150(几乎跌没才爆)
    assert liquidation_price(Decimal("30000"), 1, PerpSide.LONG) == Decimal(
        "150.00000000",
    )


def test_slippage_direction():
    assert apply_perp_slippage(Decimal("30000"), is_buy=True) == Decimal(
        "30030.00000000",
    )
    assert apply_perp_slippage(Decimal("30000"), is_buy=False) == Decimal(
        "29970.00000000",
    )


def test_taker_fee():
    assert perp_taker_fee(Decimal("30000")) == Decimal("15.0000")  # 0.05%


def test_realized_pnl_gross():
    # long 赚:(33000 − 30000) × 2 = 6000
    assert realized_pnl_gross(
        PerpSide.LONG, Decimal("30000"), Decimal("33000"), Decimal("2"),
    ) == Decimal("6000.0000")
    # short 赚:(30000 − 27000) × 2 = 6000
    assert realized_pnl_gross(
        PerpSide.SHORT, Decimal("30000"), Decimal("27000"), Decimal("2"),
    ) == Decimal("6000.0000")
