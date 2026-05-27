"""通知配置路由 pytest · 0025 G2a 统一 bot(飞书 / per-user token 已移除)。

涵盖:
- GET /config 未配置返默认对象(未绑定 + 开关 true)
- GET /config 已绑定(tg_chat_id)→ has_telegram true
- PUT /config 只更新总开关(lazy create)
- PUT /config 拒绝已移除字段(extra=forbid → 422)
- POST /test 无配置 400 · 已配置但未绑定 → 200 ok=false
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationConfig
from app.services.auth import issue_session
from tests.factories import make_user


async def _auth(user, db: AsyncSession) -> dict[str, str]:  # type: ignore[no-untyped-def]
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_get_config_unconfigured_returns_default(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_user(db_session)
    await db_session.commit()

    r = await client.get(
        "/api/v1/notifications/config", headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tg_chat_id"] is None
    assert body["trade_alert_enabled"] is True
    assert body["price_alert_enabled"] is True
    assert body["has_telegram"] is False
    # 飞书 / token 字段已彻底移除
    assert "feishu_webhook_url" not in body
    assert "tg_bot_token" not in body


@pytest.mark.asyncio
async def test_get_config_bound_has_telegram(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_user(db_session)
    db_session.add(NotificationConfig(user_id=user.id, tg_chat_id="42"))
    await db_session.commit()

    r = await client.get(
        "/api/v1/notifications/config", headers=await _auth(user, db_session),
    )
    body = r.json()
    assert body["tg_chat_id"] == "42"
    assert body["has_telegram"] is True


@pytest.mark.asyncio
async def test_put_config_toggles_lazy_create(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_user(db_session)
    await db_session.commit()

    r = await client.put(
        "/api/v1/notifications/config",
        json={"trade_alert_enabled": False},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["trade_alert_enabled"] is False
    assert body["price_alert_enabled"] is True  # 未传 → 默认保持

    # DB lazy create
    config = await db_session.scalar(
        select(NotificationConfig).where(NotificationConfig.user_id == user.id),
    )
    assert config is not None
    assert config.trade_alert_enabled is False


@pytest.mark.asyncio
async def test_put_config_rejects_removed_fields(
    client: AsyncClient, db_session: AsyncSession,
):
    """飞书 / token 字段已移除 · extra=forbid → 422(防回归再写这些字段)。"""
    user = await make_user(db_session)
    await db_session.commit()

    r = await client.put(
        "/api/v1/notifications/config",
        json={"feishu_webhook_url": "https://x", "tg_bot_token": "y"},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_test_no_config_400(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_user(db_session)
    await db_session.commit()

    r = await client.post(
        "/api/v1/notifications/test?channel=telegram",
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_post_test_unbound_returns_error_payload(
    client: AsyncClient, db_session: AsyncSession,
):
    """有 config 但未绑定 Telegram → 200 + ok=false(无网络)。"""
    user = await make_user(db_session)
    db_session.add(NotificationConfig(user_id=user.id, tg_chat_id=None))
    await db_session.commit()

    r = await client.post(
        "/api/v1/notifications/test?channel=telegram",
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "未绑定" in (body["error"] or "")
