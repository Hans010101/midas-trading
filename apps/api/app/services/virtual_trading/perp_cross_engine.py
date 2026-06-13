"""加密永续合约 · 全仓(cross)虚拟撮合引擎 · ADR-0027 MC-2。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:全程【虚拟资金】· 绝不接任何真实交易 / 下单通道。
   全仓开 / 加 / 平 / 反手全是点金内部虚拟撮合,行情(mark)只读,绝不 create_order。
═══════════════════════════════════════════════════════════════════════════

与逐仓(perp_engine.py · isolated)的关系 —— 严格独立:
- 本模块【不 import perp_engine】,逐仓引擎核心(_open_fresh / _add_to / _reduce /
  liquidate_position)一行不依赖、一行不改。
- 唯一共享:`perp_fees` 里的【纯函数】(滑点 / 手续费 / 已实现盈亏 / 浮盈 / 量化),
  这些数学与保证金模式无关,逐仓全仓共用,不重复造。
- 复用同一张 `virtual_perp_position` 表:全仓行 = margin_mode='cross'。

全仓 vs 逐仓本质差异(ADR-0027 §2):
- 逐仓:每仓保证金【划出】钱包(存 initial_margin)· 独立强平价 · 亏损封顶本仓保证金。
- 全仓:保证金【不划出】,整个 crypto 钱包 cash_balance 作为所有全仓仓位的【共享抵押池】;
  · 开仓只实扣手续费(fee 是真实成本),保证金不实扣(留作抵押);
  · initial_margin 字段语义 = 初始保证金【要求】(算可用用),不是已划出的钱;
  · 平仓只把【已实现盈亏 realized_net】计回 cash(没有"返还保证金"这一项 —— 当初没划出);
  · 强平是【账户级】(看整账户保证金率)· liquidation_price 字段对全仓不用 → 存 0
    (MC-1 已给逐仓强平 worker 加 margin_mode='isolated' 过滤,全仓的 liq=0 不会被误扫)。

🚫 本期(MC-2)【不实现全仓强平】—— 账户级权益判定 + 一次性全平的多仓位事务在 MC-3 单独严审。
   本模块只到"开 / 加 / 平 / 反手"+ 开仓的共担池可用保证金校验。
   `_cross_available_margin` 算的是【开仓可用】(affordability),不是强平触发,别混。

资金费:与逐仓【完全相同】(payment=sign×rate×mark×qty,扣 cash 不联动强平),
   而 settle_funding 本就扫所有活仓、扣 cash_balance → 全仓天然兼容,perp_funding.py 不改。
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
    perp_taker_fee,
    q_money,
    q_price,
    realized_pnl_gross,
    unrealized_pnl,
)

# perp 现价 fetcher 签名:symbol(Binance 风格 'BTCUSDT')→ 最新价 or None。
# 本地定义(不从 perp_engine import · 保持严格独立)· 与逐仓签名一致,价源可换。
PerpPriceFetcher = Callable[[str], Awaitable[Decimal | None]]

_CRYPTO_MARKET = "crypto"
_ZERO = Decimal("0")
# 全仓 liquidation_price 字段占位(账户级强平,不用每仓 liq;MC-1 worker 已按 mode 过滤)
_CROSS_LIQ_PLACEHOLDER = _ZERO


@dataclass(frozen=True)
class OpenCrossRequest:
    """全仓开仓请求 · margin 与 quantity 二选一(都缺 → 拒单)。"""

    user_id: UUID
    symbol: str  # Binance 风格 'BTCUSDT'
    side: PerpSide
    leverage: int
    margin: Decimal | None = None  # 初始保证金要求(USDT)· 共担不实扣
    quantity: Decimal | None = None  # 直接指定开仓量(币)


@dataclass(frozen=True)
class CloseCrossRequest:
    """全仓平仓请求 · close_all 或 quantity 二选一。"""

    user_id: UUID
    symbol: str
    quantity: Decimal | None = None
    close_all: bool = False


# ============================================================================
# 开仓(全仓 · 含加仓 / 反手)
# ============================================================================


async def open_cross_position(
    db: AsyncSession,
    req: OpenCrossRequest,
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

    is_buy = req.side == PerpSide.LONG
    fill_price = apply_perp_slippage(mark, is_buy=is_buy)

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

    # DP-7:同 symbol 同时只一种模式 —— 该 symbol 已有【逐仓】活仓 → 全仓不可介入。
    if pos is not None and pos.margin_mode != MarginMode.CROSS:
        return await _record_rejected(
            db, account_id=account.id, symbol=req.symbol, action=open_action,
            quantity=qty, leverage=req.leverage,
            reason="该 symbol 已有逐仓活仓 · 同 symbol 不可混用保证金模式(请先平掉逐仓仓)",
        )

    if pos is None:  # flat → 新开全仓
        return await _open_fresh_cross(
            db, account, get_mark_price, symbol=req.symbol, side=req.side, qty=qty,
            fill_price=fill_price, leverage=req.leverage,
            explicit_margin=req.margin if req.quantity is None else None,
        )
    if pos.side == req.side:  # 同向 → 加仓
        return await _add_to_cross(
            db, account, pos, get_mark_price, qty=qty, fill_price=fill_price,
            req_leverage=req.leverage,
        )
    # 反向:减仓(q≤持仓)或 平掉再反手(q>持仓)
    if qty <= pos.quantity:
        return await _reduce_cross(
            db, account, pos, close_qty=qty, fill_price=fill_price,
            reason=PerpCloseReason.MANUAL,
        )
    remainder = q_price(qty - pos.quantity)
    await _reduce_cross(
        db, account, pos, close_qty=pos.quantity, fill_price=fill_price,
        reason=PerpCloseReason.MANUAL,
    )
    return await _open_fresh_cross(
        db, account, get_mark_price, symbol=req.symbol, side=req.side,
        qty=remainder, fill_price=fill_price, leverage=req.leverage,
        explicit_margin=None,
    )


# ============================================================================
# 平仓 · 部分或全部
# ============================================================================


async def close_cross_position(
    db: AsyncSession,
    req: CloseCrossRequest,
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
    # 隔离:全仓平仓只处理全仓仓位,绝不碰逐仓(逐仓走 perp_engine.close_perp_position)
    if pos.margin_mode != MarginMode.CROSS:
        return await _record_rejected(
            db, account_id=account.id, symbol=req.symbol,
            action=_close_action(pos.side), quantity=req.quantity or _ZERO,
            leverage=None, reason="该 symbol 是逐仓活仓 · 请用逐仓平仓",
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

    is_buy = pos.side == PerpSide.SHORT  # 平多→卖出;平空→买回
    fill_price = apply_perp_slippage(mark, is_buy=is_buy)
    return await _reduce_cross(
        db, account, pos, close_qty=close_qty, fill_price=fill_price,
        reason=PerpCloseReason.MANUAL,
    )


# ============================================================================
# 共担池可用保证金(开仓 affordability · ADR-0027 §2.1)· 非强平判定
# ============================================================================


async def _cross_available_margin(
    db: AsyncSession,
    account: VirtualAccount,
    get_mark_price: PerpPriceFetcher,
) -> tuple[Decimal, Decimal, Decimal]:
    """算全仓共担池:返回 (cross_equity, used_margin_req, available)。

    - cross_equity = cash_balance + Σ uPnL(所有【全仓】活仓)· 逐仓仓的 uPnL 不计入(隔离)。
    - used_margin_req = Σ(全仓活仓 initial_margin)· 即已占用的"保证金要求"。
    - available = cross_equity − used_margin_req。
    取不到某全仓仓 mark → 该仓 uPnL 以 entry 兜底(=0 · 中性),不夸大/缩小权益。
    ⚠️ 这是【开仓可用】计算,不是强平触发(强平 MC-3)。
    """
    rows = await db.scalars(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == account.id,
            VirtualPerpPosition.closed_at.is_(None),
            VirtualPerpPosition.margin_mode == MarginMode.CROSS,
        ),
    )
    upnl_sum = _ZERO
    used_req = _ZERO
    for p in rows:
        mark = await get_mark_price(p.symbol)
        valuation = mark if (mark is not None and mark > 0) else p.entry_price
        upnl_sum += unrealized_pnl(p.side, p.entry_price, valuation, p.quantity)
        used_req += p.initial_margin
    equity = q_money(account.cash_balance + upnl_sum)
    used_req = q_money(used_req)
    available = q_money(equity - used_req)
    return equity, used_req, available


# ============================================================================
# 内部 · 开新仓 / 加仓 / 减仓(全仓)
# ============================================================================


async def _open_fresh_cross(
    db: AsyncSession,
    account: VirtualAccount,
    get_mark_price: PerpPriceFetcher,
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
    margin_req = (
        q_money(explicit_margin)
        if explicit_margin is not None
        else q_money(notional / Decimal(leverage))
    )
    fee = perp_taker_fee(notional)

    # 共担池可用保证金校验 · 保证金不实扣 · 只做可用性判断
    _equity, _used, available = await _cross_available_margin(db, account, get_mark_price)
    if available < margin_req:
        return await _record_rejected(
            db, account_id=account.id, symbol=symbol, action=action, quantity=qty,
            leverage=leverage,
            reason=f"全仓可用保证金不足 · 需 {margin_req} USDT(可用 {available})",
        )
    # 手续费是真实成本 · 原子从 cash 扣(保证金不扣)
    if not await _debit_fee(db, account.id, fee):
        return await _record_rejected(
            db, account_id=account.id, symbol=symbol, action=action, quantity=qty,
            leverage=leverage, reason=f"现金不足支付手续费 · 需 {fee} USDT",
        )

    position = VirtualPerpPosition(
        account_id=account.id,
        symbol=symbol,
        side=side,
        margin_mode=MarginMode.CROSS,
        leverage=leverage,
        quantity=qty,
        entry_price=fill_price,
        initial_margin=margin_req,  # 全仓:保证金"要求"(未划出现金),供可用计算
        maintenance_margin_rate=MAINTENANCE_MARGIN_RATE,
        liquidation_price=_CROSS_LIQ_PLACEHOLDER,  # 全仓账户级强平 · 此字段不用
        realized_pnl=_ZERO,
        fee_paid=fee,
        funding_paid=_ZERO,
    )
    db.add(position)
    await db.flush()

    return await _record_filled(
        db, account_id=account.id, position_id=position.id, symbol=symbol,
        action=action, leverage=leverage, quantity=qty, price=fill_price,
        notional=notional, margin_delta=margin_req, fee=fee, realized_pnl=None,
    )


async def _add_to_cross(
    db: AsyncSession,
    account: VirtualAccount,
    pos: VirtualPerpPosition,
    get_mark_price: PerpPriceFetcher,
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
    add_margin_req = q_money(notional / Decimal(pos.leverage))
    fee = perp_taker_fee(notional)

    _equity, _used, available = await _cross_available_margin(db, account, get_mark_price)
    if available < add_margin_req:
        return await _record_rejected(
            db, account_id=account.id, symbol=pos.symbol, action=action,
            quantity=qty, leverage=req_leverage,
            reason=f"全仓可用保证金不足 · 需 {add_margin_req} USDT(可用 {available})",
        )
    if not await _debit_fee(db, account.id, fee):
        return await _record_rejected(
            db, account_id=account.id, symbol=pos.symbol, action=action,
            quantity=qty, leverage=req_leverage,
            reason=f"现金不足支付手续费 · 需 {fee} USDT",
        )

    new_qty = q_price(pos.quantity + qty)
    new_entry = q_price(
        (pos.quantity * pos.entry_price + qty * fill_price) / new_qty,
    )
    pos.quantity = new_qty
    pos.entry_price = new_entry
    pos.initial_margin = q_money(pos.initial_margin + add_margin_req)
    # 全仓不用每仓强平价 · liquidation_price 保持占位 0(账户级强平 · MC-3)
    pos.fee_paid = q_money(pos.fee_paid + fee)
    await db.flush()

    return await _record_filled(
        db, account_id=account.id, position_id=pos.id, symbol=pos.symbol,
        action=action, leverage=pos.leverage, quantity=qty, price=fill_price,
        notional=notional, margin_delta=add_margin_req, fee=fee, realized_pnl=None,
    )


async def _reduce_cross(
    db: AsyncSession,
    account: VirtualAccount,
    pos: VirtualPerpPosition,
    *,
    close_qty: Decimal,
    fill_price: Decimal,
    reason: PerpCloseReason,
) -> VirtualPerpOrder:
    """全仓平仓 / 减仓核心:已实现盈亏【直接进共享池 cash】· 软删(全平)。

    与逐仓 _reduce 的关键差异:全仓开仓没划出保证金,所以平仓【不返还保证金】,
    只把 realized_net(=gross−fee)计回 cash。initial_margin 是"要求"的台账,
    全平归 0 / 部分按比例释放(只影响可用计算,不影响 cash)。
    本期(MC-2)只做手动平仓 · 不设强平地板(穿仓地板在 MC-3 账户级强平里处理)。
    """
    action = _close_action(pos.side)
    notional = q_money(close_qty * fill_price)
    gross = realized_pnl_gross(pos.side, pos.entry_price, fill_price, close_qty)
    fee = perp_taker_fee(notional)
    realized_net = q_money(gross - fee)

    is_full = close_qty >= pos.quantity
    released_req = (
        pos.initial_margin
        if is_full
        else q_money(pos.initial_margin * (close_qty / pos.quantity))
    )

    # 全仓:只把已实现盈亏计回共享池 · 没有"返还保证金"项(开仓时没划出)
    await _credit_cross(db, account.id, realized_net=realized_net)

    if is_full:
        pos.quantity = _ZERO
        pos.closed_at = datetime.now(UTC)
        pos.close_reason = reason
        pos.initial_margin = _ZERO
    else:
        pos.quantity = q_price(pos.quantity - close_qty)
        pos.initial_margin = q_money(pos.initial_margin - released_req)
    pos.realized_pnl = q_money(pos.realized_pnl + realized_net)
    pos.fee_paid = q_money(pos.fee_paid + fee)
    await db.flush()

    return await _record_filled(
        db, account_id=account.id, position_id=pos.id, symbol=pos.symbol,
        action=action, leverage=None, quantity=close_qty, price=fill_price,
        notional=notional, margin_delta=q_money(-released_req), fee=fee,
        realized_pnl=realized_net,
    )


# ============================================================================
# 内部 · 找账户 / 锁活仓 / 现金增减 / 写流水(自包含 · 不依赖 perp_engine)
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


async def _debit_fee(db: AsyncSession, account_id: int, fee: Decimal) -> bool:
    """原子扣手续费:WHERE cash_balance >= fee RETURNING(全仓只扣 fee,不扣保证金)。"""
    res = await db.execute(
        update(VirtualAccount)
        .where(
            VirtualAccount.id == account_id,
            VirtualAccount.cash_balance >= fee,
        )
        .values(cash_balance=VirtualAccount.cash_balance - fee)
        .returning(VirtualAccount.id),
    )
    return res.scalar_one_or_none() is not None


async def _credit_cross(
    db: AsyncSession, account_id: int, *, realized_net: Decimal,
) -> None:
    """全仓平仓回钱:cash += realized_net · account.realized_pnl += realized_net。

    注意:没有"返还保证金"项(全仓开仓未划出保证金),与逐仓 _credit 的语义不同。
    """
    await db.execute(
        update(VirtualAccount)
        .where(VirtualAccount.id == account_id)
        .values(
            cash_balance=VirtualAccount.cash_balance + realized_net,
            realized_pnl=VirtualAccount.realized_pnl + realized_net,
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
        is_liquidation=False,
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
