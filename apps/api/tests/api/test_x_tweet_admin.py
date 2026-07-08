"""X 营销生成端点(阶段4a · PR-2)· AdminDep 403 矩阵 + enqueue happy。

★安全边界:POST /admin/x-tweets/generate 必须 admin(401 未登录 / 403 普通用户)。
happy path mock 掉 enqueue(不真连 Celery broker)· 验证返回 enqueued。
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth import issue_session
from app.services.x_marketing.publish.store import update_dispatch_result, upsert_pending
from app.services.x_marketing.store import create_tweet
from tests.factories import make_user

_EP = "/api/v1/admin/x-tweets/generate"
_LIST = "/api/v1/admin/x-tweets"


async def _authed_headers(db: AsyncSession, *, role: str = "user") -> dict[str, str]:
    user = await make_user(db, role=role)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_generate_unauthenticated_401(client: AsyncClient) -> None:
    r = await client.post(_EP)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_generate_normal_user_403(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _authed_headers(db_session, role="user")
    r = await client.post(_EP, headers=headers)
    assert r.status_code == 403
    assert r.json()["detail"] == "Forbidden"


@pytest.mark.asyncio
async def test_generate_admin_enqueues(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    # mock enqueue(不真连 broker)· 验证 admin 触发返回 enqueued
    import app.api.v1.admin as admin_mod

    calls: list[object] = []
    monkeypatch.setattr(
        admin_mod, "enqueue_daily_generation", lambda uid, *_: calls.append(uid),
    )
    headers = await _authed_headers(db_session, role="admin")
    r = await client.post(_EP, headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "enqueued"
    assert len(calls) == 1  # ★确实 enqueue 了一次


# ── 列表 / 详情(403 矩阵 + happy)─────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_unauthenticated_401(client: AsyncClient) -> None:
    r = await client.get(_LIST)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_normal_user_403(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _authed_headers(db_session, role="user")
    r = await client.get(_LIST, headers=headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_list_admin_returns_items(client: AsyncClient, db_session: AsyncSession) -> None:
    # ★门禁过/不过都列出(不过的带 reason · passed=false)
    await create_tweet(
        db_session, symbol="BTCUSDT", bias="偏多", tweet_text="好推文",
        compliance_passed=True,
    )
    await create_tweet(
        db_session, symbol="ETHUSDT", bias="偏空", tweet_text="坏推文",
        compliance_passed=False, compliance_reason="预测词",
    )
    headers = await _authed_headers(db_session, role="admin")
    r = await client.get(_LIST, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    eth = next(i for i in body["items"] if i["symbol"] == "ETHUSDT")
    assert eth["compliance_passed"] is False
    assert eth["compliance_reason"] == "预测词"
    assert eth["status"] == "draft"
    assert eth["image_path"] is None  # ★截图 PR-4 才有


@pytest.mark.asyncio
async def test_detail_404_missing(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _authed_headers(db_session, role="admin")
    r = await client.get(f"{_LIST}/999999", headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_includes_dispatches(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    # 发布层 PR-3:列表带各平台发布状态(★批量查 · 一条推文配一条 success dispatch)
    row = await create_tweet(
        db_session, symbol="BTCUSDT", bias="偏多", tweet_text="好", compliance_passed=True,
    )
    d = await upsert_pending(
        db_session, tweet_id=row.id, platform="binance_square", dispatched_by=None,
    )
    await update_dispatch_result(
        db_session, d.id, status="success", platform_post_id="p1",
        url="https://www.binance.com/square/post/p1",
    )
    headers = await _authed_headers(db_session, role="admin")
    r = await client.get(_LIST, headers=headers)
    assert r.status_code == 200
    item = next(i for i in r.json()["items"] if i["symbol"] == "BTCUSDT")
    assert len(item["dispatches"]) == 1
    disp = item["dispatches"][0]
    assert disp["platform"] == "binance_square"
    assert disp["status"] == "success"
    assert disp["url"] == "https://www.binance.com/square/post/p1"


@pytest.mark.asyncio
async def test_list_no_dispatch_empty(client: AsyncClient, db_session: AsyncSession) -> None:
    # 没发过的推文 → dispatches 空列表(不报错)
    await create_tweet(
        db_session, symbol="ETHUSDT", bias="偏空", tweet_text="x", compliance_passed=True,
    )
    headers = await _authed_headers(db_session, role="admin")
    r = await client.get(_LIST, headers=headers)
    item = next(i for i in r.json()["items"] if i["symbol"] == "ETHUSDT")
    assert item["dispatches"] == []


# ── 截图端点(403 矩阵 + 无图 404 + 有图 200 · 阶段4a PR-4)────────────────────


@pytest.mark.asyncio
async def test_image_unauthenticated_401(client: AsyncClient) -> None:
    r = await client.get(f"{_LIST}/1/image")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_image_normal_user_403(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _authed_headers(db_session, role="user")
    r = await client.get(f"{_LIST}/1/image", headers=headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_image_404_when_no_screenshot(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    # 推文存在但 image_path 为 null(还没截好)→ 404
    row = await create_tweet(
        db_session, symbol="BTCUSDT", bias="偏多", tweet_text="x", compliance_passed=True,
    )
    headers = await _authed_headers(db_session, role="admin")
    r = await client.get(f"{_LIST}/{row.id}/image", headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_image_200_with_file(
    client: AsyncClient, db_session: AsyncSession, tmp_path,  # noqa: ANN001
) -> None:
    # image_path 指向真实 PNG → 200 + image/png(FileResponse 读共享卷)
    png = tmp_path / "1.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    row = await create_tweet(
        db_session, symbol="BTCUSDT", bias="偏多", tweet_text="x", compliance_passed=True,
        image_path=str(png),
    )
    headers = await _authed_headers(db_session, role="admin")
    r = await client.get(f"{_LIST}/{row.id}/image", headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
