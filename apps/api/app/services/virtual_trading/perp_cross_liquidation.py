"""加密永续 · 全仓(cross)账户级强平核心 · ADR-0027 MC-3。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:全程【虚拟资金】· 绝不接任何真实交易 / 平仓 / 转账通道。
   账户级强平全是点金内部虚拟撮合,mark 只读,绝不 create_order。
═══════════════════════════════════════════════════════════════════════════

算法(ADR-0027 §2.2 + 产品方 2026-05-28 拍板):
- 触发:`cross_equity ≤ Σ维持保证金`,其中
  · cross_equity = cash_balance + Σ uPnL(所有 cross 活仓 · 用 mark)
  · Σ维持保证金 = Σ(qty × mark × MMR)，MMR 用每仓快照(默认 0.005)
  · 两量各自 q_money 量化到 0.0001 后做 Decimal 精确比较(**相等即触发** · 无 epsilon)
- 触发 → **一次性全平**该账户所有 cross 活仓(DP-2)· symbol 字典序(结果可复现)
  · 每仓用其 mark 当成交价 **不加滑点**(与逐仓 liquidate_position 一致 · 强平已是不利价)
  · realized_net = gross − fee(沿用 perp_fees 规则)
- 穿仓地板(DP-8 + 拍板"地板后净亏 · 账户层勾稽"):全平后若 cash < 0 →
  · cash 置 0;account.realized_pnl 只记到亏光开仓前 cash 为止(净亏 = −pre_cash);
  · 单仓 position.realized_pnl 仍记各自真实 realized_net(Σ单仓 与 账户 差额 = 平台兜底)。
- 缺 mark(DP-9):该账户任一 cross 活仓缺 mark → **跳过整账户**,一仓不动(宁可不平)。

隔离(MC-3 红线):
- 不 import perp_engine(逐仓)/ perp_liquidation(逐仓 worker)/ perp_cross_engine(MC-2);
  只复用 perp_fees 纯函数(逐仓全仓共用的数学)。
- 只作用于 margin_mode='cross' 活仓,绝不碰逐仓('isolated')仓位。
- 不取行情(marks 由调用方/worker 传入)· 不 commit(调用方负责事务边界)。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
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
    perp_taker_fee,
    q_money,
    realized_pnl_gross,
    unrealized_pnl,
)

_ZERO = Decimal("0")

# 强平结果状态(给 worker 记日志 / 测试断言用)
STATUS_NO_POSITIONS = "no_positions"      # 该账户无 cross 活仓
STATUS_SKIPPED_NO_MARK = "skipped_no_mark"  # 缺 mark · 跳过整账户(DP-9)
STATUS_SAFE = "safe"                      # 未触发(权益在维持线上)
STATUS_LIQUIDATED = "liquidated"          # 已触发并全平


@dataclass(frozen=True)
class CrossLiquidationOutcome:
    status: str
    liquidated_count: int = 0
    equity: Decimal | None = None
    maint_margin: Decimal | None = None
    floored: bool = False  # 是否触发穿仓地板(cash<0 → 0)


# ============================================================================
# 纯函数 · 权益 / 维持保证金 / 触发判定(无 IO · 便于逐项核数值)
# ============================================================================


async def select_open_cross_account_ids(session: AsyncSession) -> list[int]:
    """选「有 cross 活仓」的账户 id(强平 worker 候选)· ★排除 managed(托管)仓 → 禁强平。

    ★禁强平实现:托管交易是独立系统账户(仓全 managed=True)→ 加 managed=False 过滤后,
    托管账户的仓全被排除 → 它的 account_id 不进候选 → 整个托管账户【不进强平扫描】。
    引擎纯函数(cross_equity_and_maint / should_liquidate_cross / _liquidate_one)一字不改;
    非托管账户的仓全 managed=False,一个不漏全进扫描 → 现有强平【零回归】。
    """
    rows = await session.scalars(
        select(VirtualPerpPosition.account_id)
        .where(
            VirtualPerpPosition.closed_at.is_(None),
            VirtualPerpPosition.margin_mode == MarginMode.CROSS,
            VirtualPerpPosition.managed.is_(False),  # ★禁强平:托管单不进强平扫描
        )
        .distinct()
        .order_by(VirtualPerpPosition.account_id),
    )
    return list(rows.all())


def cross_equity_and_maint(
    cash: Decimal,
    positions: Sequence[VirtualPerpPosition],
    marks: Mapping[str, Decimal],
) -> tuple[Decimal, Decimal]:
    """算 (cross_equity, Σ维持保证金)。调用方须保证 positions 全是 cross 活仓、marks 齐备。

    cross_equity = cash + Σ uPnL(mark);  Σmm = Σ(qty × mark × MMR)。
    全程 Decimal · 末尾 q_money 量化到 0.0001(钱 = Decimal · 0002 教训)。
    """
    upnl_sum = _ZERO
    maint = _ZERO
    for p in positions:
        mark = marks[p.symbol]
        upnl_sum += unrealized_pnl(p.side, p.entry_price, mark, p.quantity)
        maint += p.quantity * mark * p.maintenance_margin_rate
    return q_money(cash + upnl_sum), q_money(maint)


def should_liquidate_cross(equity: Decimal, maint_margin: Decimal) -> bool:
    """触发条件(拍板:**≤**,相等即强平)。"""
    return equity <= maint_margin


# ============================================================================
# 账户级强平(单事务 · 不 commit)
# ============================================================================


async def _liquidate_one(
    session: AsyncSession, pos: VirtualPerpPosition, mark: Decimal,
) -> Decimal:
    """平掉一个 cross 仓位(mark 当成交价 · 不加滑点)· 写强平流水 · 返回 realized_net。

    单独抽出便于:① 复用;② 测试用 monkeypatch 模拟"中途某仓平仓失败"验事务原子性。
    """
    notional = q_money(pos.quantity * mark)
    gross = realized_pnl_gross(pos.side, pos.entry_price, mark, pos.quantity)
    fee = perp_taker_fee(notional)
    realized_net = q_money(gross - fee)
    released_req = pos.initial_margin  # 全仓:释放的是"保证金要求"台账(非现金)
    qty_closed = pos.quantity
    action = (
        PerpAction.CLOSE_LONG if pos.side == PerpSide.LONG else PerpAction.CLOSE_SHORT
    )

    pos.realized_pnl = q_money(pos.realized_pnl + realized_net)
    pos.fee_paid = q_money(pos.fee_paid + fee)
    pos.quantity = _ZERO
    pos.closed_at = datetime.now(UTC)
    pos.close_reason = PerpCloseReason.LIQUIDATED
    pos.initial_margin = _ZERO

    session.add(
        VirtualPerpOrder(
            account_id=pos.account_id,
            position_id=pos.id,
            symbol=pos.symbol,
            action=action,
            leverage=None,
            quantity=qty_closed,
            price=mark,
            notional=notional,
            margin_delta=q_money(-released_req),
            fee=fee,
            realized_pnl=realized_net,
            status=OrderStatus.FILLED,
            is_liquidation=True,
            filled_at=datetime.now(UTC),
        ),
    )
    await session.flush()
    return realized_net


async def liquidate_cross_account(
    session: AsyncSession,
    account: VirtualAccount,
    marks: Mapping[str, Decimal],
) -> CrossLiquidationOutcome:
    """对单个账户判定并(若触发)一次性全平所有 cross 活仓。

    ⚠️ 原子性:本函数在【调用方的同一事务】内完成所有持仓平仓 + 账户结算;
       中途任一步抛错则整体不 commit(调用方 rollback)→ 要么 N 仓全平 + 账户结算,
       要么完全不变,绝无"平了一半"的半成品。本函数**不 commit**。
    """
    positions = list(
        (
            await session.scalars(
                select(VirtualPerpPosition)
                .where(
                    VirtualPerpPosition.account_id == account.id,
                    VirtualPerpPosition.closed_at.is_(None),
                    VirtualPerpPosition.margin_mode == MarginMode.CROSS,
                )
                .order_by(VirtualPerpPosition.symbol)  # 字典序 · 结果可复现
                .with_for_update(),
            )
        ).all(),
    )
    if not positions:
        return CrossLiquidationOutcome(status=STATUS_NO_POSITIONS)

    # DP-9:任一 cross 仓缺 mark → 跳过整账户(绝不用旧值/估值硬算)
    for p in positions:
        m = marks.get(p.symbol)
        if m is None or m <= 0:
            return CrossLiquidationOutcome(status=STATUS_SKIPPED_NO_MARK)

    equity, maint = cross_equity_and_maint(account.cash_balance, positions, marks)
    if not should_liquidate_cross(equity, maint):
        return CrossLiquidationOutcome(
            status=STATUS_SAFE, equity=equity, maint_margin=maint,
        )

    # ── 触发 · 一次性全平(symbol 字典序)──────────────────────────────────
    pre_cash = account.cash_balance
    total_realized = _ZERO
    for p in positions:
        total_realized += await _liquidate_one(session, p, marks[p.symbol])

    post_cash_raw = q_money(pre_cash + total_realized)
    if post_cash_raw < _ZERO:
        # 穿仓地板(DP-8)· 账户净亏封顶 = 亏光开仓前 cash(地板后净亏 · 账户层勾稽)
        account.cash_balance = _ZERO
        account.realized_pnl = q_money(account.realized_pnl - pre_cash)
        floored = True
    else:
        account.cash_balance = post_cash_raw
        account.realized_pnl = q_money(account.realized_pnl + total_realized)
        floored = False
    await session.flush()

    return CrossLiquidationOutcome(
        status=STATUS_LIQUIDATED,
        liquidated_count=len(positions),
        equity=equity,
        maint_margin=maint,
        floored=floored,
    )
