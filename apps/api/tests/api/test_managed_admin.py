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
from app.services.virtual_trading.intelligent import account as iacc
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


# ── 三平仓条件开关端点(exit-switch · 即时生效)──────────────────────────
@pytest.mark.asyncio
async def test_exit_switch_endpoint_toggle(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin_headers(db_session)
    r = await client.post(
        "/api/v1/admin/managed/exit-switch", json={"which": "tp", "on": False}, headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["exit_tp"] is False  # ★关了
    # 恢复(默认开 · 不污染其他测)
    r2 = await client.post(
        "/api/v1/admin/managed/exit-switch", json={"which": "tp", "on": True}, headers=headers,
    )
    assert r2.json()["exit_tp"] is True


@pytest.mark.asyncio
async def test_exit_switch_endpoint_invalid_which(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin_headers(db_session)
    r = await client.post(
        "/api/v1/admin/managed/exit-switch", json={"which": "xxx", "on": True}, headers=headers,
    )
    assert r.status_code == 400  # ★which 非法


@pytest.mark.asyncio
async def test_allow_long_endpoint_global(client: AsyncClient, db_session: AsyncSession) -> None:
    """★PR-8 admin 全局允许开多(托管恒做多·OFF=不开新仓)· 关→开回(默认 ON·不污染其他测)。"""
    headers = await _admin_headers(db_session)
    r = await client.post("/api/v1/admin/managed/allow-long", json={"on": False}, headers=headers)
    assert r.status_code == 200
    assert r.json()["allow_long"] is False
    r2 = await client.post("/api/v1/admin/managed/allow-long", json={"on": True}, headers=headers)
    assert r2.json()["allow_long"] is True  # 恢复默认 ON


# ── 止盈目标(盈利%)端点(exit-tp-pct)──────────────────────────────────
@pytest.mark.asyncio
async def test_exit_tp_pct_endpoint_ok(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin_headers(db_session)
    r = await client.post(
        "/api/v1/admin/managed/exit-tp-pct", json={"pct": 30}, headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["tp_pct"] == 30  # ★盈利目标 30%
    # 恢复默认(不污染其他测)
    await client.post("/api/v1/admin/managed/exit-tp-pct", json={"pct": 100}, headers=headers)


@pytest.mark.asyncio
async def test_exit_tp_pct_endpoint_invalid(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _admin_headers(db_session)
    r = await client.post(
        "/api/v1/admin/managed/exit-tp-pct", json={"pct": 0}, headers=headers,
    )
    assert r.status_code == 400  # ★pct ≤ 0 非法


def _managed_pos(account_id: int, symbol: str) -> VirtualPerpPosition:
    return VirtualPerpPosition(
        account_id=account_id, symbol=symbol, side=PerpSide.LONG,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal("100"), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        managed=True,
    )


@pytest.mark.asyncio
async def test_close_all_only_managed_not_intelligent(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    # ★一键平仓:只平【托管账户】活仓 · 绝不碰智能交易账户的仓(account_id + managed 双重隔离)
    headers = await _admin_headers(db_session)
    macc_acc = await macc.ensure_managed_account(db_session)
    iacc_acc = await iacc.ensure_intelligent_account(db_session)
    db_session.add(_managed_pos(macc_acc.id, "BTCUSDT"))
    db_session.add(_managed_pos(macc_acc.id, "ETHUSDT"))
    # ★智能交易活仓(intelligent=True/managed=False · 另一账户)→ 不该被一键平仓碰
    sol = VirtualPerpPosition(
        account_id=iacc_acc.id, symbol="SOLUSDT", side=PerpSide.SHORT,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal("100"), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        intelligent=True,
    )
    db_session.add(sol)
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
    r = await client.post("/api/v1/admin/managed/positions/close-all", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["closed"] == 2  # ★只平了 2 个托管仓
    assert body["total"] == 2
    await db_session.refresh(sol)
    assert sol.closed_at is None  # ★★红线:智能交易仓没被碰


@pytest.mark.asyncio
async def test_close_all_normal_user_403(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session, role="user")
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()
    r = await client.post(
        "/api/v1/admin/managed/positions/close-all",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_history_pagination(client: AsyncClient, db_session: AsyncSession) -> None:
    # ★历史分页:60 单已平 → 每页 50 · total=60 · offset 翻页
    headers = await _admin_headers(db_session)
    acc = await macc.ensure_managed_account(db_session)
    now = datetime(2026, 6, 28, tzinfo=UTC)
    for i in range(60):
        p = _managed_pos(acc.id, f"C{i}USDT")
        p.realized_pnl = Decimal("1")
        p.managed_close_reason = "tp"
        p.opened_at = now
        p.closed_at = now
        db_session.add(p)
    await db_session.commit()

    r = await client.get("/api/v1/admin/managed/history?offset=0&limit=50", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 60          # ★全部数(算总页数)
    assert len(body["items"]) == 50     # ★每页 50

    r2 = await client.get("/api/v1/admin/managed/history?offset=50&limit=50", headers=headers)
    body2 = r2.json()
    assert body2["total"] == 60
    assert len(body2["items"]) == 10    # ★第二页剩 10


@pytest.mark.asyncio
async def test_positions_pagination(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    # ★托管活仓分页(100/页):建 3 活仓 + limit=2 → 第一页 2 + total=3
    from app.api.v1 import managed_admin  # noqa: PLC0415
    acc = await macc.ensure_managed_account(db_session)
    for i in range(3):
        db_session.add(_managed_pos(acc.id, f"C{i}USDT"))
    await db_session.commit()

    async def _fake_marks(_c: object, _s: object) -> dict[str, Decimal]:
        return {}

    monkeypatch.setattr(managed_admin, "select_premium_index_marks", _fake_marks)
    headers = await _admin_headers(db_session)
    r1 = await client.get("/api/v1/admin/managed/positions?offset=0&limit=2", headers=headers)
    b1 = r1.json()
    assert b1["total"] == 3
    assert len(b1["items"]) == 2
    r2 = await client.get("/api/v1/admin/managed/positions?offset=2&limit=2", headers=headers)
    assert len(r2.json()["items"]) == 1
