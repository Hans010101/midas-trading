"""bot 下单后台预设路由 pytest · 0026 G5。

GET 无行 → 默认值(= G4 常量);PUT upsert + 校验(杠杆 1-20 / 名义 >0)· 仅逐仓。
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth import issue_session
from tests.factories import make_user


async def _auth(user, db: AsyncSession) -> dict[str, str]:  # type: ignore[no-untyped-def]
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_returns_defaults_when_no_row(client: AsyncClient, db_session: AsyncSession):
    user = await make_user(db_session)
    await db_session.commit()
    r = await client.get("/api/v1/bot-preset", headers=await _auth(user, db_session))
    assert r.status_code == 200
    b = r.json()
    assert b["perp_leverage"] == 3
    assert float(b["perp_notional_usdt"]) == 100.0
    assert b["perp_margin_mode"] == "isolated"
    assert float(b["spot_notional_cny"]) == 10000.0
    assert float(b["spot_notional_usd"]) == 1000.0


@pytest.mark.asyncio
async def test_put_upserts_and_get_reflects(client: AsyncClient, db_session: AsyncSession):
    user = await make_user(db_session)
    await db_session.commit()
    headers = await _auth(user, db_session)
    r = await client.put(
        "/api/v1/bot-preset",
        json={
            "perp_leverage": 5, "perp_notional_usdt": 200,
            "spot_notional_cny": 20000, "spot_notional_usd": 2000,
        },
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["perp_leverage"] == 5
    assert r.json()["perp_margin_mode"] == "isolated"  # 固定逐仓
    # GET 反映保存值
    r2 = await client.get("/api/v1/bot-preset", headers=headers)
    assert r2.json()["perp_leverage"] == 5
    assert float(r2.json()["perp_notional_usdt"]) == 200.0


@pytest.mark.asyncio
async def test_put_rejects_bad_leverage(client: AsyncClient, db_session: AsyncSession):
    user = await make_user(db_session)
    await db_session.commit()
    r = await client.put(
        "/api/v1/bot-preset",
        json={
            "perp_leverage": 50, "perp_notional_usdt": 100,
            "spot_notional_cny": 10000, "spot_notional_usd": 1000,
        },
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 422  # 杠杆 > 20


@pytest.mark.asyncio
async def test_put_rejects_nonpositive_notional(client: AsyncClient, db_session: AsyncSession):
    user = await make_user(db_session)
    await db_session.commit()
    r = await client.put(
        "/api/v1/bot-preset",
        json={
            "perp_leverage": 3, "perp_notional_usdt": 0,
            "spot_notional_cny": 10000, "spot_notional_usd": 1000,
        },
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 422  # 名义额必须 > 0
