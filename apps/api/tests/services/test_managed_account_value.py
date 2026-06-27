"""托管交易 · 账户价值/可用资金(问题3)· 复用引擎 _cross_available_margin · 和活仓浮盈对得上。

★账户价值 = cash_balance + Σ未实现浮盈浮亏 · 可用 = 账户价值 − Σ已占保证金 · 复用引擎现成算法不重写盈亏。
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.services.virtual_trading.managed import account as macc
from app.services.virtual_trading.perp_cross_engine import _cross_available_margin


async def _mark(price: str):  # noqa: ANN202
    async def f(_symbol: str) -> Decimal:
        return Decimal(price)
    return f


@pytest.mark.asyncio
async def test_account_value_equals_cash_plus_upnl(db_session: AsyncSession) -> None:
    # 托管账户 10万U · 1 个 LONG 仓(entry=100, qty=1, 保证金 20)· mark=110 → 浮盈 +10
    acc = await macc.ensure_managed_account(db_session)
    db_session.add(VirtualPerpPosition(
        account_id=acc.id, symbol="BTCUSDT", side=PerpSide.LONG,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal("100"), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        managed=True,
    ))
    await db_session.flush()
    equity, used, available = await _cross_available_margin(db_session, acc, await _mark("110"))
    # ★账户价值 = 现金 100000 + 浮盈 (110-100)*1 = 100010(浮盈正 → 账户价值 > 10万)
    assert equity == Decimal("100010.0000")
    assert used == Decimal("20.0000")           # 已占保证金 = initial_margin
    assert available == Decimal("99990.0000")   # 可用 = 账户价值 − 已占


@pytest.mark.asyncio
async def test_account_value_reflects_loss(db_session: AsyncSession) -> None:
    # mark=90 < entry=100 → 浮亏 -10 → 账户价值 < 10万
    acc = await macc.ensure_managed_account(db_session)
    db_session.add(VirtualPerpPosition(
        account_id=acc.id, symbol="ETHUSDT", side=PerpSide.LONG,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal("100"), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        managed=True,
    ))
    await db_session.flush()
    equity, _used, _avail = await _cross_available_margin(db_session, acc, await _mark("90"))
    assert equity == Decimal("99990.0000")  # 100000 + (90-100)*1 = 99990
