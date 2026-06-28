"""托管交易 PR-1 · admin 端点 status / toggle(★AdminDep 403 + 默认 OFF + 开则建账户)。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_clickhouse
from app.main import app
from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.models.virtual import OrderStatus
from app.services.auth import issue_session
from app.services.virtual_trading.managed import account as macc
from app.services.virtual_trading.managed import close as mclose
from tests.factories import make_user


@pytest.fixture(autouse=True)
def _ch_override():  # noqa: ANN202
    # status/toggle 端点要 ClickHouseDep(算账户价值)· 测试无 lifespan → 给假 holder(0 持仓 fetcher 不触发)
    app.dependency_overrides[get_clickhouse] = lambda: SimpleNamespace(_client=object())
    yield
    app.dependency_overrides.pop(get_clickhouse, None)


async def _admin_headers(db: AsyncSession) -> dict[str, str]:
    user = await make_user(db, role="admin")
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_status_normal_user_403(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session, role="user")
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()
    r = await client.get(
        "/api/v1/admin/managed/status", headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_toggle_unauthenticated_401(client: AsyncClient) -> None:
    r = await client.post("/api/v1/admin/managed/toggle", json={"enabled": True})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_status_default_off_no_account(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin_headers(db_session)
    r = await client.get("/api/v1/admin/managed/status", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False        # ★默认 OFF
    assert body["account_ready"] is False  # 还没建账户


@pytest.mark.asyncio
async def test_toggle_on_provisions_account(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin_headers(db_session)
    r = await client.post("/api/v1/admin/managed/toggle", json={"enabled": True}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["account_ready"] is True              # ★开则幂等建账户
    assert body["initial_capital"] == 100000.0        # 10万U
    assert body["cash_balance"] == 100000.0
    assert body["account_value"] == 100000.0          # ★账户价值(0 持仓 → = 现金 10万)
    assert body["available_funds"] == 100000.0        # ★可用资金(0 占用 → = 10万)
    assert body["open_positions"] == 0
    # 关
    r2 = await client.post("/api/v1/admin/managed/toggle", json={"enabled": False}, headers=headers)
    assert r2.json()["enabled"] is False


# ── 手动平单端点(★唯一入口 route_close_perp mock · 记 manual)──────────
@pytest.mark.asyncio
async def test_manual_close_endpoint_ok(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    headers = await _admin_headers(db_session)
    acc = await macc.ensure_managed_account(db_session)
    pos = VirtualPerpPosition(
        account_id=acc.id, symbol="BTCUSDT", side=PerpSide.LONG,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal("100"), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        managed=True,
    )
    db_session.add(pos)
    await db_session.commit()

    async def _fake_close(
        session: AsyncSession, *, symbol: str, close_all: bool, **_kw: Any,  # noqa: ARG001
    ) -> Any:
        p = await session.scalar(select(VirtualPerpPosition).where(
            VirtualPerpPosition.symbol == symbol, VirtualPerpPosition.closed_at.is_(None),
        ))
        if p is not None:
            p.closed_at = datetime(2026, 6, 28, tzinfo=UTC)
            p.realized_pnl = Decimal("5")
        await session.flush()
        return SimpleNamespace(status=OrderStatus.FILLED, reject_reason=None)

    monkeypatch.setattr(mclose, "route_close_perp", _fake_close)
    r = await client.post(f"/api/v1/admin/managed/positions/{pos.id}/close", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["symbol"] == "BTCUSDT"
    assert body["realized_pnl"] == 5.0
    await db_session.refresh(pos)
    assert pos.managed_close_reason == "manual"  # ★记 manual


@pytest.mark.asyncio
async def test_manual_close_normal_user_403(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session, role="user")
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()
    r = await client.post(
        "/api/v1/admin/managed/positions/1/close",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403  # ★AdminDep 拦在 close_one 之前
