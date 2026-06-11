"""条件单挂单簿 API pytest(ADR 0041 刀1)· 挂 / 撤 / 列 · 越权 · 软校验。

🔴 本刀边界:条件单只能挂/撤/看,【不会触发成交】(刀2 扫描器)· 不碰 engine。
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import PerpSide, VirtualPerpPosition
from app.models.user import User
from app.models.virtual import PositionSide, VirtualPosition
from app.services.auth import issue_session
from tests.factories import make_user, make_virtual_account


async def _auth(user: User, db: AsyncSession) -> dict[str, str]:
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


async def _spot_position(db: AsyncSession, account_id: int, symbol: str = "NVDA") -> None:
    db.add(
        VirtualPosition(
            account_id=account_id, symbol=symbol, market="us",
            position_side=PositionSide.LONG,
            quantity=Decimal("10"), avg_entry_price=Decimal("100"),
            opened_at=datetime.now(UTC),
        ),
    )
    await db.flush()


async def _perp_position(db: AsyncSession, account_id: int, symbol: str = "BTCUSDT") -> None:
    db.add(
        VirtualPerpPosition(
            account_id=account_id, symbol=symbol, side=PerpSide.LONG,
            margin_mode="isolated", leverage=3,
            quantity=Decimal("0.1"), entry_price=Decimal("100000"),
            initial_margin=Decimal("3334"), maintenance_margin_rate=Decimal("0.005"),
            liquidation_price=Decimal("70000"),
        ),
    )
    await db.flush()


# ── 挂单 ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_limit_create_ok(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    r = await client.post(
        "/api/v1/virtual/conditional-orders",
        json={"symbol": "NVDA", "market": "us", "order_kind": "limit",
              "side": "buy", "trigger_price": "90", "quantity": "5"},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "active"
    assert body["order_kind"] == "limit"
    assert Decimal(body["trigger_price"]) == Decimal("90")
    assert body["triggered_order_id"] is None  # 本刀不会触发成交(刀2 分界)


@pytest.mark.asyncio
async def test_crypto_limit_rejected_400(client: AsyncClient, db_session: AsyncSession) -> None:
    """刀2 缺口补:perp 限价单范围外(ADR 0041 只含 perp SL/TP)→ 400。"""
    user = await make_user(db_session)
    r = await client.post(
        "/api/v1/virtual/conditional-orders",
        json={"symbol": "BTCUSDT", "market": "crypto", "order_kind": "limit",
              "side": "buy", "trigger_price": "100000", "quantity": "1"},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 400
    assert "perp 限价单暂不支持" in r.json()["detail"]


@pytest.mark.asyncio
async def test_limit_requires_quantity(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    r = await client.post(
        "/api/v1/virtual/conditional-orders",
        json={"symbol": "NVDA", "market": "us", "order_kind": "limit",
              "side": "buy", "trigger_price": "90"},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 400
    assert "数量" in r.json()["detail"]


@pytest.mark.asyncio
async def test_stop_loss_requires_active_position(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="us")
    r = await client.post(
        "/api/v1/virtual/conditional-orders",
        json={"symbol": "NVDA", "market": "us", "order_kind": "stop_loss",
              "side": "sell", "trigger_price": "80"},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 400
    assert "活仓" in r.json()["detail"]


@pytest.mark.asyncio
async def test_stop_loss_with_spot_position_ok(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)
    account = await make_virtual_account(db_session, user_id=user.id, market="us")
    await _spot_position(db_session, account.id)
    r = await client.post(
        "/api/v1/virtual/conditional-orders",
        json={"symbol": "NVDA", "market": "us", "order_kind": "stop_loss",
              "side": "sell", "trigger_price": "80"},  # quantity 省略 = 平全仓
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    assert r.json()["quantity"] is None


@pytest.mark.asyncio
async def test_stop_loss_wrong_side_rejected(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """LONG 仓的 SL 必须 SELL(触发矩阵自洽 · 防脏数据)。"""
    user = await make_user(db_session)
    account = await make_virtual_account(db_session, user_id=user.id, market="us")
    await _spot_position(db_session, account.id)
    r = await client.post(
        "/api/v1/virtual/conditional-orders",
        json={"symbol": "NVDA", "market": "us", "order_kind": "stop_loss",
              "side": "buy", "trigger_price": "80"},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 400
    assert "平仓" in r.json()["detail"]


@pytest.mark.asyncio
async def test_take_profit_with_perp_position_ok(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """crypto 语义=perp:TP 挂在 perp 活仓上(symbol 自动归一 btc/usdt→BTCUSDT)。"""
    user = await make_user(db_session)
    account = await make_virtual_account(
        db_session, user_id=user.id, market="crypto", initial_capital=Decimal("10000"),
    )
    await _perp_position(db_session, account.id)
    r = await client.post(
        "/api/v1/virtual/conditional-orders",
        json={"symbol": "btc/usdt", "market": "crypto", "order_kind": "take_profit",
              "side": "sell", "trigger_price": "120000"},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    assert r.json()["symbol"] == "BTCUSDT"


# ── 撤单 ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_own_active_204_and_status_cancelled(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)
    headers = await _auth(user, db_session)
    created = await client.post(
        "/api/v1/virtual/conditional-orders",
        json={"symbol": "NVDA", "market": "us", "order_kind": "limit",
              "side": "buy", "trigger_price": "90", "quantity": "5"},
        headers=headers,
    )
    cond_id = created.json()["id"]

    r = await client.delete(f"/api/v1/virtual/conditional-orders/{cond_id}", headers=headers)
    assert r.status_code == 204
    # 状态机:CANCELLED 保留行(非物理删除 · ADR 0041)· 列表可见
    listed = await client.get(
        "/api/v1/virtual/conditional-orders?status=cancelled", headers=headers,
    )
    assert [x["id"] for x in listed.json()] == [cond_id]
    # 再撤已 CANCELLED → 404(只能撤 ACTIVE · 不泄露状态)
    again = await client.delete(f"/api/v1/virtual/conditional-orders/{cond_id}", headers=headers)
    assert again.status_code == 404


@pytest.mark.asyncio
async def test_cancel_others_order_404(client: AsyncClient, db_session: AsyncSession) -> None:
    alice = await make_user(db_session)
    bob = await make_user(db_session)
    created = await client.post(
        "/api/v1/virtual/conditional-orders",
        json={"symbol": "NVDA", "market": "us", "order_kind": "limit",
              "side": "buy", "trigger_price": "90", "quantity": "5"},
        headers=await _auth(bob, db_session),
    )
    r = await client.delete(
        f"/api/v1/virtual/conditional-orders/{created.json()['id']}",
        headers=await _auth(alice, db_session),
    )
    assert r.status_code == 404


# ── 列表 ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_own_only_desc_and_filter(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    alice = await make_user(db_session)
    bob = await make_user(db_session)
    a_headers = await _auth(alice, db_session)
    ids = []
    for px in ("90", "91"):
        r = await client.post(
            "/api/v1/virtual/conditional-orders",
            json={"symbol": "NVDA", "market": "us", "order_kind": "limit",
                  "side": "buy", "trigger_price": px, "quantity": "1"},
            headers=a_headers,
        )
        ids.append(r.json()["id"])
    await client.post(  # bob 的 · 不该出现在 alice 列表
        "/api/v1/virtual/conditional-orders",
        json={"symbol": "NVDA", "market": "us", "order_kind": "limit",
              "side": "buy", "trigger_price": "1", "quantity": "1"},
        headers=await _auth(bob, db_session),
    )

    r = await client.get("/api/v1/virtual/conditional-orders", headers=a_headers)
    body = r.json()
    assert [x["id"] for x in body] == [ids[1], ids[0]]  # 仅本人 · 倒序
    # status 过滤:active 全中 · triggered 空
    active = await client.get(
        "/api/v1/virtual/conditional-orders?status=active", headers=a_headers,
    )
    assert len(active.json()) == 2
    triggered = await client.get(
        "/api/v1/virtual/conditional-orders?status=triggered", headers=a_headers,
    )
    assert triggered.json() == []


@pytest.mark.asyncio
async def test_unauthenticated_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/virtual/conditional-orders")).status_code == 401
    r = await client.post(
        "/api/v1/virtual/conditional-orders",
        json={"symbol": "NVDA", "market": "us", "order_kind": "limit",
              "side": "buy", "trigger_price": "90", "quantity": "5"},
    )
    assert r.status_code == 401
