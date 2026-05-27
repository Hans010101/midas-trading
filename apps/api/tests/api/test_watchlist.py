"""watchlist 路由 pytest · 8 个场景。

涵盖:
- list: 未验证 (no lazy-fill) / 验证后 (lazy-fill once) / demo_prefilled=true (empty)
- add: 成功 / 重复 409
- delete: 成功 / 越权 404(跨用户隔离)
- reorder: 失败回滚不应破坏数据
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.user import User
from app.models.watchlist import WatchlistItem
from app.services.auth import issue_session
from tests.factories import (
    make_unverified_user,
    make_user,
    make_watchlist_item,
)


async def _auth_headers(user: User, db: AsyncSession) -> dict[str, str]:
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


class _FakeCryptoSource:
    """测试用 crypto 源 · 只实现加自选校验需要的 symbol_exists。

    valid=None → 全部存在;否则只认集合内符号。记录被校验过的 symbol,
    用于断言「A股/美股加自选根本不触发 crypto 校验」。
    """

    def __init__(self, valid: set[str] | None = None) -> None:
        self._valid = valid
        self.checked: list[str] = []

    def symbol_exists(self, symbol: str) -> bool:
        self.checked.append(symbol)
        return self._valid is None or symbol in self._valid


@pytest.fixture
def crypto_source_only_btc() -> Iterator[_FakeCryptoSource]:
    """注入「只认 BTC/USDT」的 crypto 源到 app.state · 测试后清理。"""
    fake = _FakeCryptoSource(valid={"BTC/USDT"})
    app.state.crypto_source = fake
    yield fake
    if hasattr(app.state, "crypto_source"):
        delattr(app.state, "crypto_source")


@pytest.fixture
def crypto_source_reject_all() -> Iterator[_FakeCryptoSource]:
    """注入「全部拒绝」的 crypto 源 · 用于验证 A股/美股加自选不被它误伤。"""
    fake = _FakeCryptoSource(valid=set())
    app.state.crypto_source = fake
    yield fake
    if hasattr(app.state, "crypto_source"):
        delattr(app.state, "crypto_source")


@pytest.mark.asyncio
async def test_list_unverified_user_no_lazy_fill(
    client: AsyncClient, db_session: AsyncSession,
):
    """未验证邮箱的用户 GET /watchlist 返回 [],不触发 lazy-fill。"""
    user = await make_unverified_user(db_session)
    await db_session.commit()

    r = await client.get("/api/v1/watchlist", headers=await _auth_headers(user, db_session))
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

    r = await client.get("/api/v1/watchlist", headers=await _auth_headers(user, db_session))
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

    r = await client.get("/api/v1/watchlist", headers=await _auth_headers(user, db_session))
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_add_then_duplicate_returns_409(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_user(db_session, demo_prefilled=True)
    await db_session.commit()

    headers = await _auth_headers(user, db_session)

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
        f"/api/v1/watchlist/{item.id}", headers=await _auth_headers(user, db_session),
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
        f"/api/v1/watchlist/{item_b.id}", headers=await _auth_headers(user_a, db_session),
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
        headers=await _auth_headers(user, db_session),
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
        headers=await _auth_headers(user, db_session),
    )
    assert r.status_code == 404

    # DB 验证回滚 · 两个 item 的 sort_order 都没变
    await db_session.refresh(own)
    await db_session.refresh(foreign)
    assert own.sort_order == 5
    assert foreign.sort_order == 7


# =====================
# 加密标的存在性校验(MU/USDT 根因修复)
# =====================


@pytest.mark.asyncio
async def test_add_crypto_nonexistent_symbol_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    crypto_source_only_btc: _FakeCryptoSource,
):
    """加密非法交易对(如 MU/USDT)→ 400 + 友好提示 · 不入库。"""
    user = await make_user(db_session, demo_prefilled=True)
    await db_session.commit()
    headers = await _auth_headers(user, db_session)

    r = await client.post(
        "/api/v1/watchlist",
        json={"symbol": "MU/USDT", "market": "crypto"},
        headers=headers,
    )
    assert r.status_code == 400
    assert "不存在" in r.json()["detail"]
    # 校验确实针对该 symbol 跑过
    assert "MU/USDT" in crypto_source_only_btc.checked

    # 不入库
    row = await db_session.scalar(
        select(WatchlistItem).where(
            WatchlistItem.user_id == user.id,
            WatchlistItem.symbol == "MU/USDT",
        ),
    )
    assert row is None


@pytest.mark.asyncio
async def test_add_crypto_valid_symbol_succeeds(
    client: AsyncClient,
    db_session: AsyncSession,
    crypto_source_only_btc: _FakeCryptoSource,
):
    """加密真实交易对(BTC/USDT)→ 201 正常入库。"""
    user = await make_user(db_session, demo_prefilled=True)
    await db_session.commit()
    headers = await _auth_headers(user, db_session)

    r = await client.post(
        "/api/v1/watchlist",
        json={"symbol": "BTC/USDT", "market": "crypto"},
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["symbol"] == "BTC/USDT"
    # 校验确实跑过且放行
    assert "BTC/USDT" in crypto_source_only_btc.checked


@pytest.mark.asyncio
async def test_add_cn_us_symbol_skips_crypto_validation(
    client: AsyncClient,
    db_session: AsyncSession,
    crypto_source_reject_all: _FakeCryptoSource,
):
    """A股/美股加自选不走 crypto 校验 —— 即便 crypto 源拒绝一切,仍正常入库;
    且 crypto 源的 symbol_exists 根本不被调用(市场门控 · 零回归保证)。"""
    user = await make_user(db_session, demo_prefilled=True)
    await db_session.commit()
    headers = await _auth_headers(user, db_session)

    for symbol, market in (("600519", "cn"), ("AAPL", "us")):
        r = await client.post(
            "/api/v1/watchlist",
            json={"symbol": symbol, "market": market},
            headers=headers,
        )
        assert r.status_code == 201, f"{symbol}/{market} 应正常入库(不受 crypto 校验影响)"

    # crypto 校验对 A股/美股完全没被触发
    assert crypto_source_reject_all.checked == []
