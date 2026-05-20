"""watchlist 路由 pytest · 8 个场景。

涵盖:
- list: 未验证 (no lazy-fill) / 验证后 (lazy-fill once) / demo_prefilled=true (empty)
- add: 成功 / 重复 409
- delete: 成功 / 越权 404(跨用户隔离)
- reorder: 失败回滚不应破坏数据
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.watchlist import WatchlistItem
from app.services.auth import issue_access_token
from tests.factories import (
    make_unverified_user,
    make_user,
    make_watchlist_item,
)


async def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user.id)}"}


@pytest.mark.asyncio
async def test_list_unverified_user_no_lazy_fill(
    client: AsyncClient, db_session: AsyncSession,
):
    """未验证邮箱的用户 GET /watchlist 返回 [],不触发 lazy-fill。"""
    user = await make_unverified_user(db_session)
    await db_session.commit()

    r = await client.get("/api/v1/watchlist", headers=await _auth_headers(user))
    assert r.status_code == 200
    assert r.json() == []

    # DB:user.demo_prefilled 仍为 false(没触发)
    await db_session.refresh(user)
    assert user.demo_prefilled is False


@pytest.mark.asyncio
async def test_list_verified_user_triggers_lazy_fill_3_demo(
    client: AsyncClient, db_session: AsyncSession,
):
    """验证邮箱后 + demo_prefilled=false + 空 watchlist → 自动预填 3 个 demo."""
    user = await make_user(db_session, demo_prefilled=False)
    await db_session.commit()

    r = await client.get("/api/v1/watchlist", headers=await _auth_headers(user))
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 3
    symbols = {(it["symbol"], it["market"]) for it in items}
    assert symbols == {
        ("BTC/USDT", "crypto"),
        ("NVDA", "us"),
        ("600519", "cn"),
    }
    # sort_order 各为 0/1/2
    assert {it["sort_order"] for it in items} == {0, 1, 2}

    # DB:user.demo_prefilled 已翻 true
    await db_session.refresh(user)
    assert user.demo_prefilled is True


@pytest.mark.asyncio
async def test_list_prefilled_flag_true_empty_returns_empty(
    client: AsyncClient, db_session: AsyncSession,
):
    """demo_prefilled=true + 空 watchlist → 返回 [],不再触发预填(防止「删光又被填回」)。"""
    user = await make_user(db_session, demo_prefilled=True)
    await db_session.commit()

    r = await client.get("/api/v1/watchlist", headers=await _auth_headers(user))
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_add_then_duplicate_returns_409(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_user(db_session, demo_prefilled=True)
    await db_session.commit()

    headers = await _auth_headers(user)

    # 第一次 add
    r1 = await client.post(
        "/api/v1/watchlist",
        json={"symbol": "AAPL", "market": "us"},
        headers=headers,
    )
    assert r1.status_code == 201
    body = r1.json()
    assert body["symbol"] == "AAPL"
    assert body["sort_order"] == 0

    # 第二次 add 相同 → 409
    r2 = await client.post(
        "/api/v1/watchlist",
        json={"symbol": "AAPL", "market": "us"},
        headers=headers,
    )
    assert r2.status_code == 409
    assert "已在自选" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_delete_own_item_returns_204(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_user(db_session, demo_prefilled=True)
    item = await make_watchlist_item(
        db_session, user_id=user.id, symbol="NVDA", market="us",
    )
    await db_session.commit()

    r = await client.delete(
        f"/api/v1/watchlist/{item.id}", headers=await _auth_headers(user),
    )
    assert r.status_code == 204

    # DB 确认确实删了
    remaining = await db_session.scalar(
        select(WatchlistItem).where(WatchlistItem.id == item.id),
    )
    assert remaining is None


@pytest.mark.asyncio
async def test_delete_other_users_item_returns_404(
    client: AsyncClient, db_session: AsyncSession,
):
    """跨用户隔离:用户 A 不能删用户 B 的 item。"""
    user_a = await make_user(db_session, demo_prefilled=True)
    user_b = await make_user(db_session, demo_prefilled=True)
    item_b = await make_watchlist_item(
        db_session, user_id=user_b.id, symbol="600519", market="cn",
    )
    await db_session.commit()

    # user_a 试图删 user_b 的 item
    r = await client.delete(
        f"/api/v1/watchlist/{item_b.id}", headers=await _auth_headers(user_a),
    )
    assert r.status_code == 404

    # DB 确认 user_b 的 item 还在
    still_there = await db_session.scalar(
        select(WatchlistItem).where(WatchlistItem.id == item_b.id),
    )
    assert still_there is not None


@pytest.mark.asyncio
async def test_reorder_success_rewrites_sort_order(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_user(db_session, demo_prefilled=True)
    it1 = await make_watchlist_item(
        db_session, user_id=user.id, symbol="A", market="us", sort_order=0,
    )
    it2 = await make_watchlist_item(
        db_session, user_id=user.id, symbol="B", market="us", sort_order=1,
    )
    it3 = await make_watchlist_item(
        db_session, user_id=user.id, symbol="C", market="us", sort_order=2,
    )
    await db_session.commit()

    # 反转顺序 C / B / A
    r = await client.put(
        "/api/v1/watchlist/reorder",
        json={"item_ids": [it3.id, it2.id, it1.id]},
        headers=await _auth_headers(user),
    )
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "reordered": 3}

    # DB 验证
    await db_session.refresh(it1)
    await db_session.refresh(it2)
    await db_session.refresh(it3)
    assert it3.sort_order == 0
    assert it2.sort_order == 1
    assert it1.sort_order == 2


@pytest.mark.asyncio
async def test_reorder_with_invalid_id_404_rollback(
    client: AsyncClient, db_session: AsyncSession,
):
    """reorder 中包含别人的 item id → 404 + 整批回滚不改任何 sort_order。"""
    user = await make_user(db_session, demo_prefilled=True)
    other = await make_user(db_session, demo_prefilled=True)
    own = await make_watchlist_item(
        db_session, user_id=user.id, symbol="X", market="us", sort_order=5,
    )
    foreign = await make_watchlist_item(
        db_session, user_id=other.id, symbol="Y", market="us", sort_order=7,
    )
    await db_session.commit()

    # 把别人的 id 混进来
    r = await client.put(
        "/api/v1/watchlist/reorder",
        json={"item_ids": [own.id, foreign.id]},
        headers=await _auth_headers(user),
    )
    assert r.status_code == 404

    # DB 验证回滚 · 两个 item 的 sort_order 都没变
    await db_session.refresh(own)
    await db_session.refresh(foreign)
    assert own.sort_order == 5
    assert foreign.sort_order == 7
