"""bot 核心查询层 pytest · 0025 M1-G G3。

query_symbol / query_watchlist / query_positions —— 只读 CH(用 FakeCH 替身)+ PG(真库)。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.models.virtual import PositionSide, VirtualPosition
from app.services.bot import query as q
from tests.factories import make_user, make_virtual_account, make_watchlist_item


class _FakeCH:
    """最小 ClickHouseClient 替身 · 只实现 select_kline + _client(crypto 衍生取不到→None)。"""

    def __init__(self, klines: list[Any] | None = None) -> None:
        self._klines = klines or []
        self._client = object()  # crypto 衍生 select_* 拿它会失败 → fail-soft None

    async def select_kline(self, **_kwargs: Any) -> list[Any]:
        return list(self._klines)


def _bar(close: float, volume: float) -> SimpleNamespace:
    return SimpleNamespace(close=Decimal(str(close)), volume=Decimal(str(volume)))


@pytest.mark.asyncio
async def test_query_symbol_no_data_returns_none():
    quote = await q.query_symbol(_FakeCH([]), "us", "NVDA")  # type: ignore[arg-type]
    assert quote is None


@pytest.mark.asyncio
async def test_query_symbol_price_and_change():
    ch = _FakeCH([_bar(100.0, 1000), _bar(110.0, 2000)])
    quote = await q.query_symbol(ch, "us", "NVDA")  # type: ignore[arg-type]
    assert quote is not None
    assert quote.price == 110.0
    assert quote.volume == 2000.0
    assert quote.change_pct == pytest.approx(10.0)  # (110-100)/100
    assert quote.currency == "USD"
    # 非 crypto · 衍生字段全 None
    assert quote.funding_rate is None
    assert quote.basis_pct is None


@pytest.mark.asyncio
async def test_query_symbol_crypto_extras_failsoft():
    """crypto 标的:K 线有价,衍生指标 FakeCH 取不到 → 各 None(不抛)。"""
    ch = _FakeCH([_bar(60000.0, 5), _bar(61200.0, 6)])
    quote = await q.query_symbol(ch, "crypto", "BTC/USDT")  # type: ignore[arg-type]
    assert quote is not None
    assert quote.price == 61200.0
    assert quote.currency == "USDT"
    assert quote.funding_rate is None
    assert quote.open_interest_usd is None
    assert quote.long_short_ratio is None
    assert quote.basis_pct is None


@pytest.mark.asyncio
async def test_query_watchlist(db_session: AsyncSession):
    user = await make_user(db_session)
    await make_watchlist_item(db_session, user_id=user.id, symbol="NVDA", market="us", sort_order=0)
    await make_watchlist_item(db_session, user_id=user.id, symbol="AAPL", market="us", sort_order=1)
    await db_session.commit()

    ch = _FakeCH([_bar(100.0, 10), _bar(105.0, 12)])
    rows = await q.query_watchlist(db_session, ch, user.id)  # type: ignore[arg-type]
    assert {r.symbol for r in rows} == {"NVDA", "AAPL"}
    assert all(r.price == 105.0 for r in rows)
    assert all(r.change_pct == pytest.approx(5.0) for r in rows)


@pytest.mark.asyncio
async def test_query_positions_spot_and_perp(db_session: AsyncSession):
    user = await make_user(db_session)
    crypto_acct = await make_virtual_account(db_session, user_id=user.id, market="crypto")
    us_acct = await make_virtual_account(db_session, user_id=user.id, market="us")

    # 现货活仓(美股)
    db_session.add(
        VirtualPosition(
            account_id=us_acct.id, symbol="NVDA", market="us",
            position_side=PositionSide.LONG,
            quantity=Decimal("10"), avg_entry_price=Decimal("100"),
        ),
    )
    # 永续活仓(加密 · 10x 多)
    db_session.add(
        VirtualPerpPosition(
            account_id=crypto_acct.id, symbol="BTCUSDT", side=PerpSide.LONG,
            margin_mode=MarginMode.ISOLATED, leverage=10,
            quantity=Decimal("0.5"), entry_price=Decimal("60000"),
            initial_margin=Decimal("3000"), maintenance_margin_rate=Decimal("0.005"),
            liquidation_price=Decimal("54500"),
        ),
    )
    await db_session.commit()

    rows = await q.query_positions(db_session, user.id)
    by_kind = {r.kind: r for r in rows}
    assert set(by_kind) == {"spot", "perp"}
    assert by_kind["spot"].symbol == "NVDA"
    assert by_kind["spot"].side == "long"
    assert by_kind["spot"].quantity == 10.0
    assert by_kind["perp"].symbol == "BTCUSDT"
    assert by_kind["perp"].leverage == 10
    assert by_kind["perp"].currency == "USDT"


@pytest.mark.asyncio
async def test_query_positions_empty_when_no_account(db_session: AsyncSession):
    user = await make_user(db_session)
    await db_session.commit()
    rows = await q.query_positions(db_session, user.id)
    assert rows == []
