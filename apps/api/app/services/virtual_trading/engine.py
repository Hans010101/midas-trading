"""市价单撮合 · 0008 § 3 · 纯 SQL 原子语义,无应用层 lock。

撮合流程(全部一个 transaction):
1. 找子账户 · 未激活 → reject
2. 拿当前市场价(注入式 price fetcher,便于 mock)
3. 滑点 → 成交价(原币种)
4. 算 notional + commission(原币种)
5. BUY: 原子 UPDATE WHERE cash >= total_cost / SELL: SELECT FOR UPDATE active position
6. UPSERT 活仓 / 减持仓 / 软删完整平仓
7. 写订单流水 (FILLED)
8. 写权益快照 (trigger=order_filled)

业务拒单返回 VirtualOrder(status=REJECTED, reject_reason=...) · 不抛异常。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.virtual import (
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    SnapshotTrigger,
    VirtualAccount,
    VirtualOrder,
    VirtualPosition,
)
from app.services.notifications.emit import emit_trade_filled
from app.services.virtual_trading.equity import snapshot_equity_for_account
from app.services.virtual_trading.fees import apply_slippage, calc_commission

# Price fetcher 签名:(symbol, market) → 最新价 or None
PriceFetcher = Callable[[str, str], Awaitable[Decimal | None]]


@dataclass(frozen=True)
class PlaceOrderRequest:
    user_id: UUID
    symbol: str
    market: str
    side: OrderSide
    quantity: Decimal
    # 3.4 · 持仓方向 · 默认 LONG(现货做多 · A股/加密/美股做多 不传即原行为)。
    # SHORT 仅美股卖空:side=SELL+SHORT=开空,side=BUY+SHORT=平空(买回)。
    position_side: PositionSide = PositionSide.LONG
    # #296 去重:bot 下单走自己的富回执,传 notify=False 抑制异步成交推送(避免双发);
    # 网页 / 默认 True 行为不变。仅控通知开关 · 不影响撮合 / 结算 / 下单计算任何逻辑。
    notify: bool = True


async def place_market_order(
    db: AsyncSession,
    req: PlaceOrderRequest,
    get_market_price: PriceFetcher,
) -> VirtualOrder:
    """市价单撮合入口 · 返回 VirtualOrder(filled / rejected)。"""
    # 1. 找子账户
    account = await db.scalar(
        select(VirtualAccount).where(
            VirtualAccount.user_id == req.user_id,
            VirtualAccount.market == req.market,
        ),
    )
    if account is None:
        return await _record_rejected(
            db, req, account_id=None,
            reason="该市场虚拟资金未设置 · 请先去个人设置页填写",
        )

    # 2. 当前市场价
    market_price = await get_market_price(req.symbol, req.market)
    if market_price is None or market_price <= 0:
        return await _record_rejected(
            db, req, account_id=account.id,
            reason="无最新报价 · 标的可能停牌或数据未到达",
        )

    # 3. 滑点 + 名义金额 + 手续费
    fill_price = apply_slippage(market_price, req.market, req.side)
    notional = (req.quantity * fill_price).quantize(Decimal("0.0001"))
    commission = calc_commission(req.market, req.side, notional)
    slippage_cost = (
        abs(fill_price - market_price) * req.quantity
    ).quantize(Decimal("0.0001"))

    # 3.4 · 跨方向守卫:同标的同时只允许一个方向活仓(已有反向 → 拒,先平再反向开)。
    # 纯做多流程(A股/加密/美股做多)永远命中不到(无 SHORT 活仓)· 现货做多行为零变化。
    active = await _active_position(db, account.id, req.symbol)
    if active is not None and active.position_side != req.position_side:
        return await _record_rejected(
            db, req, account_id=account.id,
            reason="已有反向持仓 · 请先平仓再反向开仓",
            position_side=req.position_side,
        )

    if req.position_side == PositionSide.LONG:
        # ↓↓↓ 现货做多(0008 原有路径)· 调用与计算一行不动 ↓↓↓
        if req.side == OrderSide.BUY:
            return await _execute_buy(
                db, req, account,
                fill_price=fill_price, notional=notional,
                commission=commission, slippage_cost=slippage_cost,
            )
        return await _execute_sell(
            db, req, account,
            fill_price=fill_price, notional=notional,
            commission=commission, slippage_cost=slippage_cost,
        )

    # ↓↓↓ 卖空(SHORT)· 美股专用 · 全新独立路径 · 不碰上面做多 ↓↓↓
    if req.side == OrderSide.SELL:
        return await _execute_sell_short(
            db, req, account,
            fill_price=fill_price, notional=notional,
            commission=commission, slippage_cost=slippage_cost,
        )
    return await _execute_buy_to_cover(
        db, req, account,
        fill_price=fill_price, notional=notional,
        commission=commission, slippage_cost=slippage_cost,
    )


# ===== 内部:BUY 路径 =====


async def _execute_buy(
    db: AsyncSession,
    req: PlaceOrderRequest,
    account: VirtualAccount,
    *,
    fill_price: Decimal,
    notional: Decimal,
    commission: Decimal,
    slippage_cost: Decimal,
) -> VirtualOrder:
    total_cost = notional + commission

    # 原子扣钱(WHERE cash >= total_cost RETURNING)
    debited = await db.execute(
        update(VirtualAccount)
        .where(
            VirtualAccount.id == account.id,
            VirtualAccount.cash_balance >= total_cost,
        )
        .values(cash_balance=VirtualAccount.cash_balance - total_cost)
        .returning(VirtualAccount.id),
    )
    if debited.scalar_one_or_none() is None:
        return await _record_rejected(
            db, req, account_id=account.id,
            reason=f"余额不足 · 需要 {total_cost}",
        )

    # UPSERT 活仓(同账户同标的最多一个活仓 · partial unique)
    existing = await db.scalar(
        select(VirtualPosition)
        .where(
            VirtualPosition.account_id == account.id,
            VirtualPosition.symbol == req.symbol,
            VirtualPosition.closed_at.is_(None),
        )
        .with_for_update(),
    )
    if existing is None:
        position = VirtualPosition(
            account_id=account.id,
            symbol=req.symbol,
            market=req.market,
            quantity=req.quantity,
            avg_entry_price=fill_price,
        )
        db.add(position)
    else:
        # 加权平均:(old_qty × old_avg + new_qty × fill_price) / (old_qty + new_qty)
        new_qty = existing.quantity + req.quantity
        new_avg = (
            existing.quantity * existing.avg_entry_price
            + req.quantity * fill_price
        ) / new_qty
        existing.quantity = new_qty
        existing.avg_entry_price = new_avg.quantize(Decimal("0.00000001"))

    order = await _record_filled(
        db, req, account_id=account.id,
        price=fill_price, notional=notional,
        commission=commission, slippage_cost=slippage_cost,
        realized_pnl=None,
    )

    # 权益快照
    await db.flush()
    await snapshot_equity_for_account(
        db, account_id=account.id, market=req.market,
        trigger=SnapshotTrigger.ORDER_FILLED,
    )
    return order


# ===== 内部:SELL 路径 =====


async def _execute_sell(
    db: AsyncSession,
    req: PlaceOrderRequest,
    account: VirtualAccount,
    *,
    fill_price: Decimal,
    notional: Decimal,
    commission: Decimal,
    slippage_cost: Decimal,
) -> VirtualOrder:
    # 锁活仓 + 检查 quantity 够
    position = await db.scalar(
        select(VirtualPosition)
        .where(
            VirtualPosition.account_id == account.id,
            VirtualPosition.symbol == req.symbol,
            VirtualPosition.closed_at.is_(None),
        )
        .with_for_update(),
    )
    if position is None or position.quantity < req.quantity:
        return await _record_rejected(
            db, req, account_id=account.id,
            reason="持仓不足",
        )

    proceeds = notional - commission
    # 本笔 realized_pnl = (fill_price - avg_entry) × qty - commission
    realized_pnl_this = (
        (fill_price - position.avg_entry_price) * req.quantity - commission
    ).quantize(Decimal("0.0001"))

    new_qty = position.quantity - req.quantity
    accumulated = (position.realized_pnl or Decimal("0")) + realized_pnl_this

    if new_qty == 0:
        # 完整平仓 → 软删 + realized_pnl 一次性
        position.quantity = Decimal("0")
        position.closed_at = datetime.now(UTC)
        position.realized_pnl = accumulated.quantize(Decimal("0.0001"))
    else:
        position.quantity = new_qty
        position.realized_pnl = accumulated.quantize(Decimal("0.0001"))

    # 加钱 + 累计 realized
    await db.execute(
        update(VirtualAccount)
        .where(VirtualAccount.id == account.id)
        .values(
            cash_balance=VirtualAccount.cash_balance + proceeds,
            realized_pnl=VirtualAccount.realized_pnl + realized_pnl_this,
        ),
    )

    order = await _record_filled(
        db, req, account_id=account.id,
        price=fill_price, notional=notional,
        commission=commission, slippage_cost=slippage_cost,
        realized_pnl=realized_pnl_this,
    )

    # 权益快照
    await db.flush()
    await snapshot_equity_for_account(
        db, account_id=account.id, market=req.market,
        trigger=SnapshotTrigger.ORDER_FILLED,
    )
    return order


# ===== 内部:卖空路径(3.4 · 美股 · 无杠杆 1:1 · 全新,不碰做多)=====


async def _active_position(
    db: AsyncSession, account_id: int, symbol: str,
) -> VirtualPosition | None:
    """读当前活仓(不加锁)· 给跨方向守卫用 · 不影响撮合路径自己的 with_for_update 锁。"""
    result: VirtualPosition | None = await db.scalar(
        select(VirtualPosition).where(
            VirtualPosition.account_id == account_id,
            VirtualPosition.symbol == symbol,
            VirtualPosition.closed_at.is_(None),
        ),
    )
    return result


async def _execute_sell_short(
    db: AsyncSession,
    req: PlaceOrderRequest,
    account: VirtualAccount,
    *,
    fill_price: Decimal,
    notional: Decimal,
    commission: Decimal,
    slippage_cost: Decimal,
) -> VirtualOrder:
    """卖空开仓(美股 · 无杠杆 1:1)· 锁定等额现金(notional)+ 手续费作担保。

    现金机制与做多买入同(扣 notional + commission),但建 SHORT 仓 · 卖空规模被现金 1:1 限死。
    """
    total_collateral = notional + commission
    debited = await db.execute(
        update(VirtualAccount)
        .where(
            VirtualAccount.id == account.id,
            VirtualAccount.cash_balance >= total_collateral,
        )
        .values(cash_balance=VirtualAccount.cash_balance - total_collateral)
        .returning(VirtualAccount.id),
    )
    if debited.scalar_one_or_none() is None:
        return await _record_rejected(
            db, req, account_id=account.id,
            reason=f"现金担保不足 · 卖空需锁定 {total_collateral}(无杠杆 1:1)",
            position_side=PositionSide.SHORT,
        )

    existing = await db.scalar(
        select(VirtualPosition)
        .where(
            VirtualPosition.account_id == account.id,
            VirtualPosition.symbol == req.symbol,
            VirtualPosition.closed_at.is_(None),
        )
        .with_for_update(),
    )
    if existing is None:
        position = VirtualPosition(
            account_id=account.id,
            symbol=req.symbol,
            market=req.market,
            position_side=PositionSide.SHORT,
            quantity=req.quantity,
            avg_entry_price=fill_price,
        )
        db.add(position)
    else:
        # 加权平均空头入场价(量、价均正 · 跟做多加仓同公式)
        new_qty = existing.quantity + req.quantity
        new_avg = (
            existing.quantity * existing.avg_entry_price
            + req.quantity * fill_price
        ) / new_qty
        existing.quantity = new_qty
        existing.avg_entry_price = new_avg.quantize(Decimal("0.00000001"))

    order = await _record_filled(
        db, req, account_id=account.id,
        price=fill_price, notional=notional,
        commission=commission, slippage_cost=slippage_cost,
        realized_pnl=None, position_side=PositionSide.SHORT,
    )
    await db.flush()
    await snapshot_equity_for_account(
        db, account_id=account.id, market=req.market,
        trigger=SnapshotTrigger.ORDER_FILLED,
    )
    return order


async def _execute_buy_to_cover(
    db: AsyncSession,
    req: PlaceOrderRequest,
    account: VirtualAccount,
    *,
    fill_price: Decimal,
    notional: Decimal,
    commission: Decimal,
    slippage_cost: Decimal,
) -> VirtualOrder:
    """平空(买回 · 美股)· 释放等额现金担保 + 已实现盈亏。

    已实现 =(avg_entry − fill)× qty − commission(空头:回补价低于开仓价 → 盈利)。
    现金返还 = qty × avg_entry(释放担保)+ 已实现。无强平 · 大幅逆向时现金可为负(同 perp E4=A)。
    """
    position = await db.scalar(
        select(VirtualPosition)
        .where(
            VirtualPosition.account_id == account.id,
            VirtualPosition.symbol == req.symbol,
            VirtualPosition.closed_at.is_(None),
        )
        .with_for_update(),
    )
    if position is None or position.quantity < req.quantity:
        return await _record_rejected(
            db, req, account_id=account.id,
            reason="空头持仓不足",
            position_side=PositionSide.SHORT,
        )

    realized_pnl_this = (
        (position.avg_entry_price - fill_price) * req.quantity - commission
    ).quantize(Decimal("0.0001"))
    collateral_release = (req.quantity * position.avg_entry_price).quantize(
        Decimal("0.0001"),
    )
    cash_credit = collateral_release + realized_pnl_this

    new_qty = position.quantity - req.quantity
    accumulated = (position.realized_pnl or Decimal("0")) + realized_pnl_this
    if new_qty == 0:
        position.quantity = Decimal("0")
        position.closed_at = datetime.now(UTC)
        position.realized_pnl = accumulated.quantize(Decimal("0.0001"))
    else:
        position.quantity = new_qty
        position.realized_pnl = accumulated.quantize(Decimal("0.0001"))

    await db.execute(
        update(VirtualAccount)
        .where(VirtualAccount.id == account.id)
        .values(
            cash_balance=VirtualAccount.cash_balance + cash_credit,
            realized_pnl=VirtualAccount.realized_pnl + realized_pnl_this,
        ),
    )

    order = await _record_filled(
        db, req, account_id=account.id,
        price=fill_price, notional=notional,
        commission=commission, slippage_cost=slippage_cost,
        realized_pnl=realized_pnl_this, position_side=PositionSide.SHORT,
    )
    await db.flush()
    await snapshot_equity_for_account(
        db, account_id=account.id, market=req.market,
        trigger=SnapshotTrigger.ORDER_FILLED,
    )
    return order


# ===== 内部:订单流水写入 =====


async def _record_filled(
    db: AsyncSession,
    req: PlaceOrderRequest,
    *,
    account_id: int,
    price: Decimal,
    notional: Decimal,
    commission: Decimal,
    slippage_cost: Decimal,
    realized_pnl: Decimal | None,
    position_side: PositionSide = PositionSide.LONG,
) -> VirtualOrder:
    now = datetime.now(UTC)
    order = VirtualOrder(
        account_id=account_id,
        symbol=req.symbol,
        market=req.market,
        side=req.side,
        position_side=position_side,
        order_type=OrderType.MARKET,
        quantity=req.quantity,
        price=price,
        notional=notional,
        commission=commission,
        slippage_cost=slippage_cost,
        realized_pnl=realized_pnl,
        status=OrderStatus.FILLED,
        filled_at=now,
    )
    db.add(order)
    await db.flush()

    # 0009 § 3 · 异步 emit · 绝不阻塞下单主链路
    # broker IO ~5ms · broker 挂了 emit 内部捕获不抛
    # #296:bot 路径传 req.notify=False 抑制(走自己的富回执去重)· 默认 True 行为不变
    if req.notify:
        emit_trade_filled(order.id)

    return order


async def _record_rejected(
    db: AsyncSession,
    req: PlaceOrderRequest,
    *,
    account_id: int | None,
    reason: str,
    position_side: PositionSide = PositionSide.LONG,
) -> VirtualOrder:
    # 未激活市场 · account_id 为 None · 不能写入 virtual_order(FK CASCADE)
    # 这种情况返回一个未持久化的临时 VirtualOrder 表示拒单 · 路由层判断 id 是否 None
    if account_id is None:
        return VirtualOrder(
            account_id=0,  # sentinel,路由层不会读
            symbol=req.symbol,
            market=req.market,
            side=req.side,
            position_side=position_side,
            order_type=OrderType.MARKET,
            quantity=req.quantity,
            status=OrderStatus.REJECTED,
            reject_reason=reason,
        )

    order = VirtualOrder(
        account_id=account_id,
        symbol=req.symbol,
        market=req.market,
        side=req.side,
        position_side=position_side,
        order_type=OrderType.MARKET,
        quantity=req.quantity,
        status=OrderStatus.REJECTED,
        reject_reason=reason,
    )
    db.add(order)
    await db.flush()
    return order
