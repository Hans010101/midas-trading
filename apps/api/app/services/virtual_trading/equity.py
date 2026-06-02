"""权益快照 + 多市场 portfolio 聚合 · 0008 § 6 + § 9。

- snapshot_equity_for_account · 每次成交触发 / daily beat 调用
- aggregate_portfolio · 给 GET /api/v1/virtual/portfolio 用,
  返回当前用户全部已激活账户 + 活仓 + 实时估值

价格来自注入式 PriceFetcher(测试可 mock,生产用 ClickHouse 最新 close)。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.virtual import (
    PositionSide,
    SnapshotTrigger,
    VirtualAccount,
    VirtualEquitySnapshot,
    VirtualPosition,
)

PriceFetcher = Callable[[str, str], Awaitable[Decimal | None]]


@dataclass(frozen=True)
class PositionView:
    """portfolio 聚合用 · 活仓 + 实时价 + 浮盈亏。"""

    id: int
    symbol: str
    market: str
    position_side: str  # 'long' / 'short'(3.4)
    quantity: Decimal
    avg_entry_price: Decimal
    current_price: Decimal | None  # 没拿到价 = None
    unrealized_pnl: Decimal | None
    value: Decimal | None  # long: quantity × current_price · short: 担保 + 浮盈


@dataclass(frozen=True)
class AccountSummary:
    """portfolio 聚合用 · 一个市场子账户的实时全貌。"""

    account_id: int
    market: str
    currency: str
    initial_capital: Decimal
    cash_balance: Decimal
    realized_pnl: Decimal
    positions: list[PositionView]
    positions_value: Decimal  # sum(p.value),None 当 0 算
    total_equity: Decimal     # cash + positions_value


async def snapshot_equity_for_account(
    db: AsyncSession,
    *,
    account_id: int,
    market: str,
    trigger: SnapshotTrigger,
    price_fetcher: PriceFetcher | None = None,
) -> VirtualEquitySnapshot:
    """给某账户写一条 equity_snapshot。

    price_fetcher 为 None 时,持仓估值用 avg_entry_price 兜底(测试 / 没行情场景)。
    """
    account = await db.scalar(
        select(VirtualAccount).where(VirtualAccount.id == account_id),
    )
    if account is None:
        msg = f"VirtualAccount id={account_id} 不存在"
        raise ValueError(msg)

    # 拿活仓
    positions = (
        await db.scalars(
            select(VirtualPosition)
            .where(
                VirtualPosition.account_id == account_id,
                VirtualPosition.closed_at.is_(None),
            ),
        )
    ).all()

    positions_value = Decimal("0")
    for p in positions:
        price = (
            await price_fetcher(p.symbol, p.market) if price_fetcher else None
        )
        if price is None or price <= 0:
            price = p.avg_entry_price  # 兜底,不让快照失败
        if p.position_side == PositionSide.SHORT:
            # 空头估值 = 锁定担保(qty×avg_entry)+ 浮盈((avg_entry−price)×qty)· 3.4
            positions_value += (
                p.quantity * p.avg_entry_price
                + (p.avg_entry_price - price) * p.quantity
            )
        else:
            positions_value += p.quantity * price  # 做多(原有)· 字节不变

    positions_value = positions_value.quantize(Decimal("0.0001"))
    equity = (account.cash_balance + positions_value).quantize(Decimal("0.0001"))

    snapshot = VirtualEquitySnapshot(
        account_id=account_id,
        market=market,
        cash=account.cash_balance,
        positions_value=positions_value,
        equity=equity,
        realized_pnl_cumulative=account.realized_pnl,
        trigger_kind=trigger,
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


async def aggregate_portfolio(
    db: AsyncSession,
    *,
    user_id: UUID,
    price_fetcher: PriceFetcher,
) -> list[AccountSummary]:
    """聚合当前用户所有已激活账户 + 活仓 + 实时估值 · /portfolio 用。"""
    accounts = (
        await db.scalars(
            select(VirtualAccount)
            .where(VirtualAccount.user_id == user_id)
            .order_by(VirtualAccount.market),
        )
    ).all()

    summaries: list[AccountSummary] = []
    for acc in accounts:
        positions = (
            await db.scalars(
                select(VirtualPosition)
                .where(
                    VirtualPosition.account_id == acc.id,
                    VirtualPosition.closed_at.is_(None),
                )
                .order_by(VirtualPosition.symbol),
            )
        ).all()

        position_views: list[PositionView] = []
        total_positions_value = Decimal("0")
        for p in positions:
            price = await price_fetcher(p.symbol, p.market)
            if price is not None and price > 0:
                if p.position_side == PositionSide.SHORT:
                    # 空头(3.4):浮盈 =(avg_entry−price)×qty;估值 = 担保 + 浮盈
                    unrealized = (
                        (p.avg_entry_price - price) * p.quantity
                    ).quantize(Decimal("0.0001"))
                    value = (
                        p.quantity * p.avg_entry_price
                        + (p.avg_entry_price - price) * p.quantity
                    ).quantize(Decimal("0.0001"))
                else:
                    value = (p.quantity * price).quantize(Decimal("0.0001"))  # 做多 原有 字节不变
                    unrealized = (
                        (price - p.avg_entry_price) * p.quantity
                    ).quantize(Decimal("0.0001"))
                total_positions_value += value
            else:
                value = None
                unrealized = None
            position_views.append(
                PositionView(
                    id=p.id, symbol=p.symbol, market=p.market,
                    position_side=p.position_side.value,
                    quantity=p.quantity, avg_entry_price=p.avg_entry_price,
                    current_price=price if price and price > 0 else None,
                    unrealized_pnl=unrealized, value=value,
                ),
            )

        total_positions_value = total_positions_value.quantize(Decimal("0.0001"))
        summaries.append(
            AccountSummary(
                account_id=acc.id,
                market=acc.market,
                currency=acc.currency,
                initial_capital=acc.initial_capital,
                cash_balance=acc.cash_balance,
                realized_pnl=acc.realized_pnl,
                positions=position_views,
                positions_value=total_positions_value,
                total_equity=(acc.cash_balance + total_positions_value).quantize(
                    Decimal("0.0001"),
                ),
            ),
        )
    return summaries
