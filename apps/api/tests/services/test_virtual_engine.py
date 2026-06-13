"""虚拟交易撮合引擎 pytest · 0008 Q6。

覆盖:
- BUY 成功 · 余额扣减 + 建仓 + filled
- BUY 余额不足 · rejected
- 加仓加权平均成本
- SELL 部分平仓 · 余额加 + position quantity 减 + realized_pnl 累积
- SELL 完整平仓 · 软删 closed_at + realized_pnl 写 row
- SELL 持仓不足 · rejected
- 未激活市场 · rejected with sentinel reject_reason
- 手续费 + 滑点数值正确(三市场对比)
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.virtual import (
    OrderSide,
    OrderStatus,
    SnapshotTrigger,
    VirtualEquitySnapshot,
    VirtualPosition,
)
from app.services.virtual_trading.engine import (
    PlaceOrderRequest,
    place_market_order,
)
from app.services.virtual_trading.fees import (
    apply_slippage,
    calc_commission,
)
from tests.factories import (
    make_static_price_fetcher,
    make_user,
    make_virtual_account,
)


@pytest.mark.asyncio
async def test_buy_success_deducts_cash_and_creates_position(
    db_session: AsyncSession,
):
    user = await make_user(db_session)
    account = await make_virtual_account(
        db_session, user_id=user.id, market="us",
        initial_capital=Decimal("100000"),
    )
    await db_session.commit()

    # NVDA 市场价 $140
    fetcher = make_static_price_fetcher({("NVDA", "us"): Decimal("140")})

    req = PlaceOrderRequest(
        user_id=user.id, symbol="NVDA", market="us",
        side=OrderSide.BUY, quantity=Decimal("10"),
    )
    order = await place_market_order(db_session, req, fetcher)
    await db_session.commit()

    assert order.status == OrderStatus.FILLED
    # 滑点 3bp:140 × 1.0003 = 140.042
    assert order.price == Decimal("140.0420")
    # notional = 10 × 140.0420 = 1400.4200
    assert order.notional == Decimal("1400.4200")
    # us 零佣
    assert order.commission == Decimal("0.0000")
    # 滑点成本 = |140.042 - 140| × 10 = 0.42
    assert order.slippage_cost == Decimal("0.4200")

    await db_session.refresh(account)
    # 余额扣除 notional + commission = 1400.42 + 0 = 1400.42
    assert account.cash_balance == Decimal("98599.5800")

    # 持仓建好
    position = await db_session.scalar(
        select(VirtualPosition).where(
            VirtualPosition.account_id == account.id,
            VirtualPosition.symbol == "NVDA",
        ),
    )
    assert position is not None
    assert position.quantity == Decimal("10")
    assert position.avg_entry_price == Decimal("140.0420")
    assert position.closed_at is None

    # 权益快照
    snapshot = await db_session.scalar(
        select(VirtualEquitySnapshot)
        .where(VirtualEquitySnapshot.account_id == account.id),
    )
    assert snapshot is not None
    assert snapshot.trigger_kind == SnapshotTrigger.ORDER_FILLED


@pytest.mark.asyncio
async def test_buy_insufficient_balance_rejected(db_session: AsyncSession):
    user = await make_user(db_session)
    account = await make_virtual_account(
        db_session, user_id=user.id, market="us",
        initial_capital=Decimal("100"),  # 故意太少
    )
    await db_session.commit()

    fetcher = make_static_price_fetcher({("NVDA", "us"): Decimal("140")})
    req = PlaceOrderRequest(
        user_id=user.id, symbol="NVDA", market="us",
        side=OrderSide.BUY, quantity=Decimal("10"),
    )
    order = await place_market_order(db_session, req, fetcher)
    await db_session.commit()

    assert order.status == OrderStatus.REJECTED
    assert "余额不足" in (order.reject_reason or "")
    # 余额未变
    await db_session.refresh(account)
    assert account.cash_balance == Decimal("100.0000")


@pytest.mark.asyncio
async def test_buy_then_buy_averages_entry_price(db_session: AsyncSession):
    user = await make_user(db_session)
    account = await make_virtual_account(
        db_session, user_id=user.id, market="us",
        initial_capital=Decimal("100000"),
    )
    await db_session.commit()

    fetcher = make_static_price_fetcher({("NVDA", "us"): Decimal("100")})

    # 第一笔:10 股 @ 100(滑点后 100.03)
    req1 = PlaceOrderRequest(
        user_id=user.id, symbol="NVDA", market="us",
        side=OrderSide.BUY, quantity=Decimal("10"),
    )
    await place_market_order(db_session, req1, fetcher)
    await db_session.commit()

    # 涨价后第二笔:10 股 @ 200(滑点后 200.06)
    fetcher2 = make_static_price_fetcher({("NVDA", "us"): Decimal("200")})
    req2 = PlaceOrderRequest(
        user_id=user.id, symbol="NVDA", market="us",
        side=OrderSide.BUY, quantity=Decimal("10"),
    )
    await place_market_order(db_session, req2, fetcher2)
    await db_session.commit()

    position = await db_session.scalar(
        select(VirtualPosition).where(VirtualPosition.account_id == account.id),
    )
    assert position is not None
    assert position.quantity == Decimal("20")
    # 加权 avg = (10×100.03 + 10×200.06) / 20 = 150.045
    assert position.avg_entry_price == Decimal("150.04500000")


@pytest.mark.asyncio
async def test_sell_partial_keeps_position_active(db_session: AsyncSession):
    user = await make_user(db_session)
    account = await make_virtual_account(
        db_session, user_id=user.id, market="us",
        initial_capital=Decimal("100000"),
    )
    await db_session.commit()

    fetcher_buy = make_static_price_fetcher({("NVDA", "us"): Decimal("100")})
    await place_market_order(
        db_session,
        PlaceOrderRequest(
            user_id=user.id, symbol="NVDA", market="us",
            side=OrderSide.BUY, quantity=Decimal("10"),
        ),
        fetcher_buy,
    )
    await db_session.commit()

    # 卖出 4 股 @ 120(滑点后 119.964)
    fetcher_sell = make_static_price_fetcher({("NVDA", "us"): Decimal("120")})
    order = await place_market_order(
        db_session,
        PlaceOrderRequest(
            user_id=user.id, symbol="NVDA", market="us",
            side=OrderSide.SELL, quantity=Decimal("4"),
        ),
        fetcher_sell,
    )
    await db_session.commit()

    assert order.status == OrderStatus.FILLED
    # realized_pnl this = (119.964 - 100.03) × 4 - 0 = 79.736
    assert order.realized_pnl == Decimal("79.7360")

    position = await db_session.scalar(
        select(VirtualPosition).where(VirtualPosition.account_id == account.id),
    )
    assert position is not None
    assert position.quantity == Decimal("6")
    assert position.closed_at is None
    assert position.realized_pnl == Decimal("79.7360")


@pytest.mark.asyncio
async def test_sell_full_closes_position_soft_delete(db_session: AsyncSession):
    user = await make_user(db_session)
    account = await make_virtual_account(
        db_session, user_id=user.id, market="us",
        initial_capital=Decimal("100000"),
    )
    await db_session.commit()

    fetcher_buy = make_static_price_fetcher({("NVDA", "us"): Decimal("100")})
    await place_market_order(
        db_session,
        PlaceOrderRequest(
            user_id=user.id, symbol="NVDA", market="us",
            side=OrderSide.BUY, quantity=Decimal("10"),
        ),
        fetcher_buy,
    )
    await db_session.commit()

    # 全部卖出
    fetcher_sell = make_static_price_fetcher({("NVDA", "us"): Decimal("120")})
    order = await place_market_order(
        db_session,
        PlaceOrderRequest(
            user_id=user.id, symbol="NVDA", market="us",
            side=OrderSide.SELL, quantity=Decimal("10"),
        ),
        fetcher_sell,
    )
    await db_session.commit()

    assert order.status == OrderStatus.FILLED

    position = await db_session.scalar(
        select(VirtualPosition).where(VirtualPosition.account_id == account.id),
    )
    assert position is not None
    # 软删 · quantity 归 0 + closed_at 填值 + realized_pnl 累计写 row
    assert position.quantity == Decimal("0")
    assert position.closed_at is not None
    assert position.realized_pnl is not None
    assert position.realized_pnl > Decimal("0")  # 赚的


@pytest.mark.asyncio
async def test_sell_insufficient_position_rejected(db_session: AsyncSession):
    user = await make_user(db_session)
    await make_virtual_account(
        db_session, user_id=user.id, market="us",
        initial_capital=Decimal("100000"),
    )
    await db_session.commit()

    fetcher = make_static_price_fetcher({("NVDA", "us"): Decimal("100")})
    order = await place_market_order(
        db_session,
        PlaceOrderRequest(
            user_id=user.id, symbol="NVDA", market="us",
            side=OrderSide.SELL, quantity=Decimal("5"),
        ),
        fetcher,
    )
    await db_session.commit()

    assert order.status == OrderStatus.REJECTED
    assert "持仓不足" in (order.reject_reason or "")


@pytest.mark.asyncio
async def test_unactivated_market_rejected(db_session: AsyncSession):
    """用户没激活该市场子账户 → 下单 reject "该市场资金未设置"。"""
    user = await make_user(db_session)
    await db_session.commit()

    fetcher = make_static_price_fetcher({("NVDA", "us"): Decimal("140")})
    order = await place_market_order(
        db_session,
        PlaceOrderRequest(
            user_id=user.id, symbol="NVDA", market="us",
            side=OrderSide.BUY, quantity=Decimal("10"),
        ),
        fetcher,
    )

    assert order.status == OrderStatus.REJECTED
    assert "未设置" in (order.reject_reason or "")
    # 未激活账户的拒单 order 是 sentinel,id 未 flush(无 PK)
    assert order.id is None


@pytest.mark.asyncio
async def test_commission_rates_correct_per_market():
    """A 股买卖费率不对称 / 美股零佣 / 加密双向 / 港股印花税双边 · 数值正确。"""
    notional = Decimal("10000")

    # A 股
    cn_buy = calc_commission("cn", OrderSide.BUY, notional)
    cn_sell = calc_commission("cn", OrderSide.SELL, notional)
    assert cn_buy == Decimal("3.0000")     # 10000 × 0.0003
    assert cn_sell == Decimal("13.0000")   # 10000 × 0.0013

    # 美股
    us_buy = calc_commission("us", OrderSide.BUY, notional)
    us_sell = calc_commission("us", OrderSide.SELL, notional)
    assert us_buy == Decimal("0.0000")
    assert us_sell == Decimal("0.0000")

    # 加密
    crypto_buy = calc_commission("crypto", OrderSide.BUY, notional)
    crypto_sell = calc_commission("crypto", OrderSide.SELL, notional)
    assert crypto_buy == Decimal("10.0000")    # 10000 × 0.001
    assert crypto_sell == Decimal("10.0000")

    # 港股(印花税 0.1% + 佣金 0.1% = 0.2% · 买卖双边对称 · 产品负责人定 2026-06-02)
    hk_buy = calc_commission("hk", OrderSide.BUY, notional)
    hk_sell = calc_commission("hk", OrderSide.SELL, notional)
    assert hk_buy == Decimal("20.0000")    # 10000 × 0.002
    assert hk_sell == Decimal("20.0000")


@pytest.mark.asyncio
async def test_slippage_buy_up_sell_down():
    """滑点:买价上浮,卖价下浮。"""
    price = Decimal("100")

    cn_buy = apply_slippage(price, "cn", OrderSide.BUY)
    cn_sell = apply_slippage(price, "cn", OrderSide.SELL)
    # cn 5bp = 0.0005
    assert cn_buy == Decimal("100.0500")
    assert cn_sell == Decimal("99.9500")

    us_buy = apply_slippage(price, "us", OrderSide.BUY)
    us_sell = apply_slippage(price, "us", OrderSide.SELL)
    # us 3bp
    assert us_buy == Decimal("100.0300")
    assert us_sell == Decimal("99.9700")

    crypto_buy = apply_slippage(price, "crypto", OrderSide.BUY)
    crypto_sell = apply_slippage(price, "crypto", OrderSide.SELL)
    # crypto 10bp
    assert crypto_buy == Decimal("100.1000")
    assert crypto_sell == Decimal("99.9000")

    hk_buy = apply_slippage(price, "hk", OrderSide.BUY)
    hk_sell = apply_slippage(price, "hk", OrderSide.SELL)
    # hk 5bp(同 A 股口径)
    assert hk_buy == Decimal("100.0500")
    assert hk_sell == Decimal("99.9500")
