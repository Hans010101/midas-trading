"""加密永续合约虚拟撮合引擎 · ADR-0019 v2 · M2-C.1。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:全程【虚拟资金】· 绝不接任何真实交易 / 下单通道。
   开仓 / 加仓 / 平仓 / 反手 / 强平全部是点金内部的虚拟撮合,
   行情(mark price)只读,绝不调用交易所 create_order。
═══════════════════════════════════════════════════════════════════════════

设计(ADR-0019 §4 + §11 决策):
- 逐仓(isolated · D2)· 单向净持仓(D6)· 杠杆 1–20x(D3)· 手续费 0.05% 计入盈亏(D8)。
- 撮合 / 强平价 = 注入式 perp 现价 fetcher(M2-C.1 用 perp ticker 最新价 · D7/§4.1)。
- 不计资金费(M2-C.2)。

净持仓撮合(开仓按 side 视作 BUY/SELL):
- 开多 = BUY:flat→开多 · 持多→加仓 · 持空→减空(q≤空仓)/ 平空反手开多(q>空仓)
- 开空 = SELL:对称
- 平仓 = 持多卖出 / 持空买回(按当前活仓方向)

事务:每次下单一个 transaction(路由层 commit)· 余额用 0008 同款原子 SQL
(UPDATE … WHERE cash_balance>=x RETURNING)。业务拒单返回
VirtualPerpOrder(status=REJECTED),不抛异常。

解耦说明(M2-C.1 故意不做,避免动 0008/0009):
- 不写 0008 VirtualEquitySnapshot(其 positions_value 只算现货;perp 已实现盈亏
  通过共用钱包 cash_balance / account.realized_pnl 体现,daily beat 仍会快照)。
- 不发 0009 trade_filled 通知(emit 绑定的是 0008 VirtualOrder.id,表不同)。
  强平提示由前端读 positions 端点感知;真推送留 M2-C.2。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import (
    MarginMode,
    PerpAction,
    PerpCloseReason,
    PerpSide,
    VirtualPerpOrder,
    VirtualPerpPosition,
)
from app.models.virtual import OrderStatus, VirtualAccount
from app.services.virtual_trading.perp_fees import (
    MAINTENANCE_MARGIN_RATE,
    MAX_LEVERAGE,
    MIN_LEVERAGE,
    apply_perp_slippage,
    liquidation_price,
    perp_taker_fee,
    q_money,
    q_price,
    realized_pnl_gross,
)

# perp 现价 fetcher 签名:symbol(Binance 风格 'BTCUSDT')→ 最新价 or None
PerpPriceFetcher = Callable[[str], Awaitable[Decimal | None]]

_CRYPTO_MARKET = "crypto"
_ZERO = Decimal("0")


@dataclass(frozen=True)
class OpenPerpRequest:
    """开仓请求 · margin 与 quantity 二选一(都缺 → 拒单)。"""

    user_id: UUID
    symbol: str  # Binance 风格 'BTCUSDT'
    side: PerpSide  # 开多 / 开空
    leverage: int
    margin: Decimal | None = None  # 投入保证金(USDT)
    quantity: Decimal | None = None  # 直接指定开仓量(币)


@dataclass(frozen=True)
class ClosePerpRequest:
    """平仓请求 · close_all 或 quantity 二选一。"""

    user_id: UUID
    symbol: str
    quantity: Decimal | None = None
    close_all: bool = False


# ============================================================================
# 开仓(开多 / 开空 · 含加仓 / 反手)
# ============================================================================


async def open_perp_position(
    db: AsyncSession,
    req: OpenPerpRequest,
    get_mark_price: PerpPriceFetcher,
) -> VirtualPerpOrder:
    open_action = _open_action(req.side)

    account = await _find_crypto_account(db, req.user_id)
    if account is None:
        return await _record_rejected(
            db, account_id=None, symbol=req.symbol, action=open_action,
            quantity=req.quantity or _ZERO, leverage=req.leverage,
            reason="加密资金未设置 · 请先去设置页填写 USDT",
        )

    if not (MIN_LEVERAGE <= req.leverage <= MAX_LEVERAGE):
        return await _record_rejected(
            db, account_id=account.id, symbol=req.symbol, action=open_action,
            quantity=req.quantity or _ZERO, leverage=req.leverage,
            reason=f"杠杆需在 {MIN_LEVERAGE}–{MAX_LEVERAGE}x(教学上限)",
        )

    mark = await get_mark_price(req.symbol)
    if mark is None or mark <= 0:
        return await _record_rejected(
            db, account_id=account.id, symbol=req.symbol, action=open_action,
            quantity=req.quantity or _ZERO, leverage=req.leverage,
            reason="无报价 · 标的可能下架或行情未到达",
        )

    # 开多→买入(滑点上浮);开空→卖出(滑点下浮)
    is_buy = req.side == PerpSide.LONG
    fill_price = apply_perp_slippage(mark, is_buy=is_buy)

    # 数量:优先 quantity,否则由 margin × 杠杆 / 成交价 折算
    if req.quantity is not None:
        qty = q_price(req.quantity)
    elif req.margin is not None:
        qty = q_price(req.margin * Decimal(req.leverage) / fill_price)
    else:
        return await _record_rejected(
            db, account_id=account.id, symbol=req.symbol, action=open_action,
            quantity=_ZERO, leverage=req.leverage,
            reason="开仓需指定保证金或数量",
        )
    if qty <= 0:
        return await _record_rejected(
            db, account_id=account.id, symbol=req.symbol, action=open_action,
            quantity=qty, leverage=req.leverage, reason="开仓数量过小",
        )

    pos = await _active_position(db, account.id, req.symbol)

    if pos is None:  # flat → 新开
        return await _open_fresh(
            db, account, symbol=req.symbol, side=req.side, qty=qty,
            fill_price=fill_price, leverage=req.leverage,
            explicit_margin=req.margin if req.quantity is None else None,
        )
    if pos.side == req.side:  # 同向 → 加仓
        return await _add_to(
            db, account, pos, qty=qty, fill_price=fill_price,
            req_leverage=req.leverage,
        )
    # 反向:减仓(q≤持仓)或 平掉再反手(q>持仓)
    if qty <= pos.quantity:
        return await _reduce(
            db, account, pos, close_qty=qty, fill_price=fill_price,
            reason=PerpCloseReason.MANUAL,
        )
    remainder = q_price(qty - pos.quantity)
    await _reduce(
        db, account, pos, close_qty=pos.quantity, fill_price=fill_price,
        reason=PerpCloseReason.MANUAL,
    )
    return await _open_fresh(
        db, account, symbol=req.symbol, side=req.side, qty=remainder,
        fill_price=fill_price, leverage=req.leverage, explicit_margin=None,
    )


# ============================================================================
# 平仓 · 部分或全部
# ============================================================================


async def close_perp_position(
    db: AsyncSession,
    req: ClosePerpRequest,
    get_mark_price: PerpPriceFetcher,
) -> VirtualPerpOrder:
    account = await _find_crypto_account(db, req.user_id)
    if account is None:
        return await _record_rejected(
            db, account_id=None, symbol=req.symbol, action=PerpAction.CLOSE_LONG,
            quantity=req.quantity or _ZERO, leverage=None,
            reason="加密资金未设置",
        )

    pos = await _active_position(db, account.id, req.symbol)
    if pos is None:
        return await _record_rejected(
            db, account_id=account.id, symbol=req.symbol,
            action=PerpAction.CLOSE_LONG, quantity=req.quantity or _ZERO,
            leverage=None, reason="无活仓可平",
        )

    close_action = _close_action(pos.side)
    close_qty = pos.quantity if req.close_all else q_price(req.quantity or _ZERO)
    if close_qty <= 0 or close_qty > pos.quantity:
        return await _record_rejected(
            db, account_id=account.id, symbol=req.symbol, action=close_action,
            quantity=close_qty, leverage=None,
            reason="平仓数量非法(需 0 < qty ≤ 持仓量)",
        )

    mark = await get_mark_price(req.symbol)
    if mark is None or mark <= 0:
        return await _record_rejected(
            db, account_id=account.id, symbol=req.symbol, action=close_action,
            quantity=close_qty, leverage=None,
            reason="无报价 · 标的可能下架或行情未到达",
        )

    # 平多→卖出(滑点下浮);平空→买回(滑点上浮)
    is_buy = pos.side == PerpSide.SHORT
    fill_price = apply_perp_slippage(mark, is_buy=is_buy)
    return await _reduce(
        db, account, pos, close_qty=close_qty, fill_price=fill_price,
        reason=PerpCloseReason.MANUAL,
    )


# ============================================================================
# 强平(强平 worker 调用)
# ============================================================================


async def liquidate_position(
    db: AsyncSession,
    position: VirtualPerpPosition,
    mark: Decimal,
) -> VirtualPerpOrder:
    """mark 触及强平价 → 按 mark 全平 · close_reason=liquidated · is_liquidation。

    逐仓:亏损上限 = 保证金。用 mark 当成交价(强平已是不利价,不再加滑点)·
    realized 设地板 −释放保证金(worker 滞后也不把钱包打穿,穿仓由平台虚拟承担)。
    """
    account = await db.scalar(
        select(VirtualAccount).where(VirtualAccount.id == position.account_id),
    )
    if account is None:  # FK CASCADE 理论不会 · 防御
        msg = f"VirtualAccount id={position.account_id} 不存在"
        raise ValueError(msg)
    return await _reduce(
        db, account, position, close_qty=position.quantity, fill_price=q_price(mark),
        reason=PerpCloseReason.LIQUIDATED, is_liquidation=True,
    )


# ============================================================================
# 内部 · 开新仓、加仓、减仓
# ============================================================================


async def _open_fresh(
    db: AsyncSession,
    account: VirtualAccount,
    *,
    symbol: str,
    side: PerpSide,
    qty: Decimal,
    fill_price: Decimal,
    leverage: int,
    explicit_margin: Decimal | None,
) -> VirtualPerpOrder:
    action = _open_action(side)
    notional = q_money(qty * fill_price)
    required_margin = (
        q_money(explicit_margin)
        if explicit_margin is not None
        else q_money(notional / Decimal(leverage))
    )
    fee = perp_taker_fee(notional)
    total_cost = q_money(required_margin + fee)

    if not await _atomic_debit(db, account.id, total_cost):
        return await _record_rejected(
            db, account_id=account.id, symbol=symbol, action=action, quantity=qty,
            leverage=leverage, reason=f"保证金不足 · 需 {total_cost} USDT",
        )

    liq = liquidation_price(fill_price, leverage, side, mmr=MAINTENANCE_MARGIN_RATE)
    position = VirtualPerpPosition(
        account_id=account.id,
        symbol=symbol,
        side=side,
        margin_mode=MarginMode.ISOLATED,
        leverage=leverage,
        quantity=qty,
        entry_price=fill_price,
        initial_margin=required_margin,
        maintenance_margin_rate=MAINTENANCE_MARGIN_RATE,
        liquidation_price=liq,
        realized_pnl=_ZERO,
        fee_paid=fee,
        funding_paid=_ZERO,
    )
    db.add(position)
    await db.flush()

    return await _record_filled(
        db, account_id=account.id, position_id=position.id, symbol=symbol,
        action=action, leverage=leverage, quantity=qty, price=fill_price,
        notional=notional, margin_delta=required_margin, fee=fee, realized_pnl=None,
    )


async def _add_to(
    db: AsyncSession,
    account: VirtualAccount,
    pos: VirtualPerpPosition,
    *,
    qty: Decimal,
    fill_price: Decimal,
    req_leverage: int,
) -> VirtualPerpOrder:
    action = _open_action(pos.side)
    if req_leverage != pos.leverage:
        return await _record_rejected(
            db, account_id=account.id, symbol=pos.symbol, action=action,
            quantity=qty, leverage=req_leverage,
            reason=f"加仓杠杆需与现有持仓一致({pos.leverage}x)",
        )

    notional = q_money(qty * fill_price)
    required_margin = q_money(notional / Decimal(pos.leverage))
    fee = perp_taker_fee(notional)
    total_cost = q_money(required_margin + fee)

    if not await _atomic_debit(db, account.id, total_cost):
        return await _record_rejected(
            db, account_id=account.id, symbol=pos.symbol, action=action,
            quantity=qty, leverage=req_leverage,
            reason=f"保证金不足 · 需 {total_cost} USDT",
        )

    new_qty = q_price(pos.quantity + qty)
    new_entry = q_price(
        (pos.quantity * pos.entry_price + qty * fill_price) / new_qty,
    )
    pos.quantity = new_qty
    pos.entry_price = new_entry
    pos.initial_margin = q_money(pos.initial_margin + required_margin)
    pos.liquidation_price = liquidation_price(
        new_entry, pos.leverage, pos.side, mmr=MAINTENANCE_MARGIN_RATE,
    )
    pos.fee_paid = q_money(pos.fee_paid + fee)
    await db.flush()

    return await _record_filled(
        db, account_id=account.id, position_id=pos.id, symbol=pos.symbol,
        action=action, leverage=pos.leverage, quantity=qty, price=fill_price,
        notional=notional, margin_delta=required_margin, fee=fee, realized_pnl=None,
    )


async def _reduce(
    db: AsyncSession,
    account: VirtualAccount,
    pos: VirtualPerpPosition,
    *,
    close_qty: Decimal,
    fill_price: Decimal,
    reason: PerpCloseReason,
    is_liquidation: bool = False,
) -> VirtualPerpOrder:
    """平仓 / 减仓核心:实现盈亏 + 释放保证金 + 回钱 + 软删(全平)。"""
    action = _close_action(pos.side)
    notional = q_money(close_qty * fill_price)
    gross = realized_pnl_gross(pos.side, pos.entry_price, fill_price, close_qty)
    fee = perp_taker_fee(notional)
    realized_net = q_money(gross - fee)

    is_full = close_qty >= pos.quantity
    released_margin = (
        pos.initial_margin
        if is_full
        else q_money(pos.initial_margin * (close_qty / pos.quantity))
    )
    # 逐仓地板 · 强平时亏损不超过释放的保证金(穿仓由平台虚拟承担)
    if is_liquidation and realized_net < -released_margin:
        realized_net = q_money(-released_margin)

    credit = q_money(released_margin + realized_net)
    await _credit(db, account.id, credit=credit, realized_delta=realized_net)

    if is_full:
        pos.quantity = _ZERO
        pos.closed_at = datetime.now(UTC)
        pos.close_reason = reason
        pos.initial_margin = _ZERO
    else:
        pos.quantity = q_price(pos.quantity - close_qty)
        pos.initial_margin = q_money(pos.initial_margin - released_margin)
        # 逐仓部分平:entry / leverage 不变 → 强平价不变
    pos.realized_pnl = q_money(pos.realized_pnl + realized_net)
    pos.fee_paid = q_money(pos.fee_paid + fee)
    await db.flush()

    return await _record_filled(
        db, account_id=account.id, position_id=pos.id, symbol=pos.symbol,
        action=action, leverage=None, quantity=close_qty, price=fill_price,
        notional=notional, margin_delta=q_money(-released_margin), fee=fee,
        realized_pnl=realized_net, is_liquidation=is_liquidation,
    )


# ============================================================================
# 内部 · 找账户、锁持仓、余额原子增减、写流水
# ============================================================================


async def _find_crypto_account(
    db: AsyncSession, user_id: UUID,
) -> VirtualAccount | None:
    acct: VirtualAccount | None = await db.scalar(
        select(VirtualAccount).where(
            VirtualAccount.user_id == user_id,
            VirtualAccount.market == _CRYPTO_MARKET,
        ),
    )
    return acct


async def _active_position(
    db: AsyncSession, account_id: int, symbol: str,
) -> VirtualPerpPosition | None:
    pos: VirtualPerpPosition | None = await db.scalar(
        select(VirtualPerpPosition)
        .where(
            VirtualPerpPosition.account_id == account_id,
            VirtualPerpPosition.symbol == symbol,
            VirtualPerpPosition.closed_at.is_(None),
        )
        .with_for_update(),
    )
    return pos


async def _atomic_debit(db: AsyncSession, account_id: int, total: Decimal) -> bool:
    """原子扣保证金 + 手续费:WHERE cash_balance >= total RETURNING(0008 同款)。"""
    res = await db.execute(
        update(VirtualAccount)
        .where(
            VirtualAccount.id == account_id,
            VirtualAccount.cash_balance >= total,
        )
        .values(cash_balance=VirtualAccount.cash_balance - total)
        .returning(VirtualAccount.id),
    )
    return res.scalar_one_or_none() is not None


async def _credit(
    db: AsyncSession, account_id: int, *, credit: Decimal, realized_delta: Decimal,
) -> None:
    """平仓回钱:cash += (释放保证金 + 已实现) · account.realized_pnl += 已实现。"""
    await db.execute(
        update(VirtualAccount)
        .where(VirtualAccount.id == account_id)
        .values(
            cash_balance=VirtualAccount.cash_balance + credit,
            realized_pnl=VirtualAccount.realized_pnl + realized_delta,
        ),
    )


async def _record_filled(
    db: AsyncSession,
    *,
    account_id: int,
    position_id: int | None,
    symbol: str,
    action: PerpAction,
    leverage: int | None,
    quantity: Decimal,
    price: Decimal,
    notional: Decimal,
    margin_delta: Decimal,
    fee: Decimal,
    realized_pnl: Decimal | None,
    is_liquidation: bool = False,
) -> VirtualPerpOrder:
    order = VirtualPerpOrder(
        account_id=account_id,
        position_id=position_id,
        symbol=symbol,
        action=action,
        leverage=leverage,
        quantity=quantity,
        price=price,
        notional=notional,
        margin_delta=margin_delta,
        fee=fee,
        realized_pnl=realized_pnl,
        status=OrderStatus.FILLED,
        is_liquidation=is_liquidation,
        filled_at=datetime.now(UTC),
    )
    db.add(order)
    await db.flush()
    return order


async def _record_rejected(
    db: AsyncSession,
    *,
    account_id: int | None,
    symbol: str,
    action: PerpAction,
    quantity: Decimal,
    leverage: int | None,
    reason: str,
) -> VirtualPerpOrder:
    # 未激活市场:account_id None · 返回未持久化 sentinel(路由层看 id is None)
    if account_id is None:
        return VirtualPerpOrder(
            account_id=0, symbol=symbol, action=action,
            quantity=quantity, leverage=leverage,
            status=OrderStatus.REJECTED, reject_reason=reason,
            is_liquidation=False,
        )
    order = VirtualPerpOrder(
        account_id=account_id, symbol=symbol, action=action,
        quantity=quantity, leverage=leverage,
        status=OrderStatus.REJECTED, reject_reason=reason, is_liquidation=False,
    )
    db.add(order)
    await db.flush()
    return order


def _open_action(side: PerpSide) -> PerpAction:
    return PerpAction.OPEN_LONG if side == PerpSide.LONG else PerpAction.OPEN_SHORT


def _close_action(side: PerpSide) -> PerpAction:
    return PerpAction.CLOSE_LONG if side == PerpSide.LONG else PerpAction.CLOSE_SHORT
