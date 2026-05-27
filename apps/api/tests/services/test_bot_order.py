"""bot 下单 facade pytest · 0025 M1-G G4。

重点:① 复用现货 / perp 引擎(虚拟)成交 / 拒单;② 🔴 facade 只作用于【传入的 user_id】
的账号(跨用户隔离);③ 默认参数(常量)折算下单量。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import VirtualPerpPosition
from app.models.virtual import VirtualPosition
from app.services.bot import order as order_mod
from tests.factories import make_user, make_virtual_account


class _FakeCH:
    def __init__(self, klines: list[Any] | None = None) -> None:
        self._klines = klines or []
        self._client = object()

    async def select_kline(self, **_kwargs: Any) -> list[Any]:
        return list(self._klines)


def _bar(close: float) -> SimpleNamespace:
    return SimpleNamespace(close=Decimal(str(close)), volume=Decimal("1"))


# ── 现货(走 FakeCH K 线价 · 无需 mock 引擎)─────────────────────────────


@pytest.mark.asyncio
async def test_spot_buy_filled(db_session: AsyncSession):
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="us")
    await db_session.commit()
    ch = _FakeCH([_bar(100.0)])

    result = await order_mod.execute(
        db_session, ch, user.id,  # type: ignore[arg-type]
        order_mod.OrderIntent(market="us", symbol="NVDA", direction="buy"),
    )
    assert result.filled is True
    # 持仓已建 + 现金减少(默认名义 1000 USD / 100 = 10 股)
    pos = await db_session.scalar(
        select(VirtualPosition).where(VirtualPosition.symbol == "NVDA"),
    )
    assert pos is not None
    assert float(pos.quantity) == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_spot_buy_rejected_when_no_account(db_session: AsyncSession):
    user = await make_user(db_session)
    await db_session.commit()
    ch = _FakeCH([_bar(100.0)])
    result = await order_mod.execute(
        db_session, ch, user.id,  # type: ignore[arg-type]
        order_mod.OrderIntent(market="us", symbol="NVDA", direction="buy"),
    )
    assert result.filled is False
    assert "未设置" in result.detail or "未激活" in result.detail


@pytest.mark.asyncio
async def test_spot_sell_no_position_unavailable(db_session: AsyncSession):
    """卖出(平多)但无持仓 → 下单失败(无可平),不调引擎乱卖。"""
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="us")
    await db_session.commit()
    ch = _FakeCH([_bar(100.0)])
    result = await order_mod.execute(
        db_session, ch, user.id,  # type: ignore[arg-type]
        order_mod.OrderIntent(market="us", symbol="NVDA", direction="sell"),
    )
    assert result.filled is False


# ── 永续(mock 标记价 → 真引擎成交)──────────────────────────────────────


@pytest.mark.asyncio
async def test_perp_open_long_filled(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_mark(_ch: object, _sym: str) -> Decimal:
        return Decimal("60000")

    monkeypatch.setattr(order_mod, "_perp_mark", _fake_mark)
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="crypto")
    await db_session.commit()

    result = await order_mod.execute(
        db_session, _FakeCH(), user.id,  # type: ignore[arg-type]
        order_mod.OrderIntent(market="crypto", symbol="BTC/USDT", direction="open_long"),
    )
    assert result.filled is True
    pos = await db_session.scalar(
        select(VirtualPerpPosition).where(VirtualPerpPosition.symbol == "BTCUSDT"),
    )
    assert pos is not None
    assert pos.leverage == order_mod.DEFAULT_PERP_LEVERAGE


# ── 🔴 跨用户隔离:facade 只动【传入 user_id】的账号 ────────────────────


@pytest.mark.asyncio
async def test_facade_only_touches_passed_user(db_session: AsyncSession):
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    acct_a = await make_virtual_account(db_session, user_id=user_a.id, market="us")
    acct_b = await make_virtual_account(db_session, user_id=user_b.id, market="us")
    await db_session.commit()
    cash_b_before = acct_b.cash_balance
    ch = _FakeCH([_bar(100.0)])

    # 以 A 下单
    result = await order_mod.execute(
        db_session, ch, user_a.id,  # type: ignore[arg-type]
        order_mod.OrderIntent(market="us", symbol="NVDA", direction="buy"),
    )
    assert result.filled is True

    await db_session.refresh(acct_a)
    await db_session.refresh(acct_b)
    assert acct_a.cash_balance < Decimal("100000")  # A 扣了钱
    assert acct_b.cash_balance == cash_b_before       # B 一分没动
    # 持仓只在 A 账户
    a_pos = await db_session.scalars(
        select(VirtualPosition).where(VirtualPosition.account_id == acct_a.id),
    )
    b_pos = await db_session.scalars(
        select(VirtualPosition).where(VirtualPosition.account_id == acct_b.id),
    )
    assert len(list(a_pos)) == 1
    assert len(list(b_pos)) == 0


def test_direction_valid_per_market():
    assert order_mod.direction_valid("crypto", "open_long")
    assert order_mod.direction_valid("us", "short")
    assert not order_mod.direction_valid("cn", "short")   # A股无卖空
    assert not order_mod.direction_valid("crypto", "buy")  # 加密走合约
