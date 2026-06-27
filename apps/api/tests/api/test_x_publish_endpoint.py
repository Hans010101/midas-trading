"""X 营销发布端点(发布层 PR-1)· POST /admin/x-tweets/{id}/publish。

★安全边界:AdminDep 403 矩阵 + 只发门禁通过 + 幂等防重 + 频率守卫 + 未配置平台拦。
happy path mock 掉 enqueue(不真连 broker)+ check_rate(不依赖 redis 状态)。
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth import issue_session
from app.services.x_marketing.publish.store import update_dispatch_result, upsert_pending
from app.services.x_marketing.store import create_tweet
from tests.factories import make_user


async def _authed_headers(db: AsyncSession, *, role: str = "user") -> dict[str, str]:
    user = await make_user(db, role=role)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


async def _passed_tweet(db: AsyncSession) -> int:
    row = await create_tweet(
        db, symbol="BTCUSDT", bias="偏多", tweet_text="好推文 仅供参考", compliance_passed=True,
    )
    return row.id


def _ep(tid: int) -> str:
    return f"/api/v1/admin/x-tweets/{tid}/publish"


@pytest.mark.asyncio
async def test_publish_unauthenticated_401(client: AsyncClient) -> None:
    r = await client.post(_ep(1), json={"platform": "binance_square"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_publish_normal_user_403(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _authed_headers(db_session, role="user")
    r = await client.post(_ep(1), json={"platform": "binance_square"}, headers=headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_publish_unknown_platform_400(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await _authed_headers(db_session, role="admin")
    r = await client.post(_ep(1), json={"platform": "weibo"}, headers=headers)
    assert r.status_code == 400  # adapter 不存在


@pytest.mark.asyncio
async def test_publish_not_configured_400(client: AsyncClient, db_session: AsyncSession) -> None:
    # 默认无 binance key → adapter.enabled=False → 400(未配置)
    headers = await _authed_headers(db_session, role="admin")
    tid = await _passed_tweet(db_session)
    r = await client.post(_ep(tid), json={"platform": "binance_square"}, headers=headers)
    assert r.status_code == 400
    assert "未配置" in r.json()["detail"]


@pytest.mark.asyncio
async def test_publish_blocks_non_compliant(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    monkeypatch.setattr("app.core.config.settings.binance_square_openapi_key", "test-key")
    headers = await _authed_headers(db_session, role="admin")
    bad = await create_tweet(
        db_session, symbol="ETHUSDT", bias="偏空", tweet_text="坏", compliance_passed=False,
    )
    r = await client.post(_ep(bad.id), json={"platform": "binance_square"}, headers=headers)
    assert r.status_code == 400  # ★门禁未过不可发
    assert "门禁" in r.json()["detail"]


@pytest.mark.asyncio
async def test_publish_idempotent_409_already_published(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    monkeypatch.setattr("app.core.config.settings.binance_square_openapi_key", "test-key")
    headers = await _authed_headers(db_session, role="admin")
    tid = await _passed_tweet(db_session)
    # 预置一条 success dispatch → 再发拒 409(★防重复发)
    d = await upsert_pending(db_session, tweet_id=tid, platform="binance_square", dispatched_by=None)
    await update_dispatch_result(db_session, d.id, status="success", platform_post_id="p", url="u")
    r = await client.post(_ep(tid), json={"platform": "binance_square"}, headers=headers)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_publish_rate_limited_429(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    monkeypatch.setattr("app.core.config.settings.binance_square_openapi_key", "test-key")

    async def _over(_redis: object, _platform: str) -> tuple[bool, str]:
        return False, "今日已达 100 条上限,明日再发"

    monkeypatch.setattr("app.api.v1.admin.check_rate", _over)
    headers = await _authed_headers(db_session, role="admin")
    tid = await _passed_tweet(db_session)
    r = await client.post(_ep(tid), json={"platform": "binance_square"}, headers=headers)
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_publish_auto_drafted_quota_full_429(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    # ★人工补发 auto_drafted 素材时,自动托管日配额(30)已满 → 429(配额"算":自动发+补发总量≤30)
    monkeypatch.setattr("app.core.config.settings.binance_square_openapi_key", "test-key")

    async def _ok(_redis: object, _platform: str) -> tuple[bool, str]:
        return True, ""

    monkeypatch.setattr("app.api.v1.admin.check_rate", _ok)

    async def _full(*_args: object, **_kwargs: object) -> int:
        return 0  # 配额满

    monkeypatch.setattr("app.api.v1.admin.auto_guard.daily_remaining", _full)
    headers = await _authed_headers(db_session, role="admin")
    row = await create_tweet(
        db_session, symbol="BTCUSDT", bias="偏多", tweet_text="好推文 仅供参考",
        compliance_passed=True, auto_drafted=True,  # ★自动素材
    )
    r = await client.post(_ep(row.id), json={"platform": "binance_square"}, headers=headers)
    assert r.status_code == 429
    assert "配额" in r.json()["detail"]


@pytest.mark.asyncio
async def test_publish_happy_enqueues(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    monkeypatch.setattr("app.core.config.settings.binance_square_openapi_key", "test-key")

    async def _ok(_redis: object, _platform: str) -> tuple[bool, str]:
        return True, ""

    monkeypatch.setattr("app.api.v1.admin.check_rate", _ok)
    calls: list[int] = []
    monkeypatch.setattr("app.api.v1.admin.enqueue_publish", lambda did: calls.append(did))
    headers = await _authed_headers(db_session, role="admin")
    tid = await _passed_tweet(db_session)
    r = await client.post(_ep(tid), json={"platform": "binance_square"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending"
    assert body["platform"] == "binance_square"
    assert len(calls) == 1  # ★enqueue 了一次(异步发布)
