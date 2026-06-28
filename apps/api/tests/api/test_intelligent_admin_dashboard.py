"""智能交易 PR-6 · 看板端点测(positions/history/stats · ★做多做空浮盈 + 共振 + 403)。

★grep-refs 教训:positions 加 ClickHouseDep → autouse override get_clickhouse(假 holder)·
有活仓时 monkeypatch select_premium_index_marks(不触发真 CH)。
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_clickhouse
from app.api.v1 import intelligent_admin
from app.main import app
from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.services.auth import issue_session
from app.services.virtual_trading.intelligent import account as iacc
from tests.factories import make_user


@pytest.fixture(autouse=True)
def _ch_override():  # noqa: ANN202
    # positions 端点要 ClickHouseDep · 测试无 lifespan → 假 holder(marks 由 monkeypatch 提供)
    app.dependency_overrides[get_clickhouse] = lambda: SimpleNamespace(_client=object())
    yield
    app.dependency_overrides.pop(get_clickhouse, None)


async def _admin_headers(db: AsyncSession) -> dict[str, str]:
    user = await make_user(db, role="admin")
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


def _pos(account_id: int, symbol: str, side: PerpSide, **extra: object) -> VirtualPerpPosition:
    return VirtualPerpPosition(
        account_id=account_id, symbol=symbol, side=side,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal("100"), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        intelligent=True, **extra,
    )


@pytest.mark.asyncio
async def test_positions_normal_user_403(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session, role="user")
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()
    r = await client.get("/api/v1/admin/intelligent/positions",
                         headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_stats_empty_no_account(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin_headers(db_session)
    r = await client.get("/api/v1/admin/intelligent/stats", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total_trades"] == 0
    assert body["by_reason"] == {"stop_loss": 0, "take_profit": 0, "signal_reversal": 0}
    assert body["by_side"] == {"long": 0, "short": 0}


@pytest.mark.asyncio
async def test_positions_long_short_upnl(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    headers = await _admin_headers(db_session)
    acc = await iacc.ensure_intelligent_account(db_session)
    # ★做多做空各一仓 + 止损止盈 + 共振
    db_session.add(_pos(
        acc.id, "BTCUSDT", PerpSide.LONG,
        intelligent_stop_price=Decimal("80"), intelligent_tp_price=Decimal("140"),
        intelligent_signals={"score": 8.0, "contributions": {"boll": 1}},
    ))
    db_session.add(_pos(
        acc.id, "ETHUSDT", PerpSide.SHORT,
        intelligent_stop_price=Decimal("120"), intelligent_tp_price=Decimal("60"),
        intelligent_signals={"score": -8.0, "contributions": {"boll": -1}},
    ))
    await db_session.commit()
    # ★mark:BTC 涨到 110(LONG 赚)· ETH 跌到 90(SHORT 赚)· 端点 await 它 → mock 必须 async
    async def _fake_marks(_c: object, _s: object) -> dict[str, Decimal]:
        return {"BTCUSDT": Decimal("110"), "ETHUSDT": Decimal("90")}

    monkeypatch.setattr(intelligent_admin, "select_premium_index_marks", _fake_marks)
    r = await client.get("/api/v1/admin/intelligent/positions", headers=headers)
    assert r.status_code == 200
    by_sym = {p["symbol"]: p for p in r.json()}
    # LONG entry=100 mark=110 qty=1 → upnl=+10
    assert by_sym["BTCUSDT"]["side"] == "long"
    assert by_sym["BTCUSDT"]["unrealized_pnl"] == 10.0
    assert by_sym["BTCUSDT"]["stop_price"] == 80.0
    assert by_sym["BTCUSDT"]["tp_price"] == 140.0
    assert by_sym["BTCUSDT"]["signals"]["score"] == 8.0
    # ★SHORT entry=100 mark=90 qty=1 → upnl=+10(做空跌赚)
    assert by_sym["ETHUSDT"]["side"] == "short"
    assert by_sym["ETHUSDT"]["unrealized_pnl"] == 10.0


@pytest.mark.asyncio
async def test_history_records_side_and_reason(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    headers = await _admin_headers(db_session)
    acc = await iacc.ensure_intelligent_account(db_session)
    now = datetime.now(tz=UTC)
    pos = _pos(
        acc.id, "BTCUSDT", PerpSide.SHORT,
        realized_pnl=Decimal("40"), intelligent_close_reason="take_profit",
    )
    pos.closed_at = now
    db_session.add(pos)
    await db_session.commit()
    r = await client.get("/api/v1/admin/intelligent/history", headers=headers)
    assert r.status_code == 200
    trades = r.json()
    assert len(trades) == 1
    assert trades[0]["side"] == "short"
    assert trades[0]["close_reason"] == "take_profit"
    assert trades[0]["pnl_usdt"] == 40.0
