"""通知配置路由 pytest · 7 个场景。

涵盖:
- GET /config · 未配置返默认对象(不是 404)
- GET /config · 已配置返 token 截断
- PUT /config · 首次激活(lazy create)
- PUT /config · 部分更新保持原值
- PUT /config · 空字符串清空字段
- POST /test · 未配置 400
- POST /test · 用 mock httpx 验证 payload
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
    assert body["feishu_webhook_url"] is None
    assert body["tg_bot_token"] is None
    assert body["trade_alert_enabled"] is True  # 默认开
    assert body["price_alert_enabled"] is True
    assert body["has_feishu"] is False
    assert body["has_telegram"] is False


@pytest.mark.asyncio
async def test_get_config_truncates_tg_token(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_user(db_session)
    config = NotificationConfig(
        user_id=user.id,
        tg_bot_token="1234567890123456:VeryLongTokenABCDEF",
        tg_chat_id="42",
    )
    db_session.add(config)
    await db_session.commit()

    r = await client.get(
        "/api/v1/notifications/config", headers=await _auth(user, db_session),
    )
    body = r.json()
    # 前 10 + ... + 后 4
    assert body["tg_bot_token"] == "1234567890...CDEF"
    assert body["tg_chat_id"] == "42"
    assert body["has_telegram"] is True


@pytest.mark.asyncio
async def test_put_config_first_time_lazy_create(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_user(db_session)
    await db_session.commit()

    r = await client.put(
        "/api/v1/notifications/config",
        json={"feishu_webhook_url": "https://feishu.example/webhook/abc"},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["feishu_webhook_url"] == "https://feishu.example/webhook/abc"
    assert body["has_feishu"] is True
    assert body["has_telegram"] is False

    # DB 实际写入(lazy create)
    config = await db_session.scalar(
        select(NotificationConfig).where(NotificationConfig.user_id == user.id),
    )
    assert config is not None
    assert config.feishu_webhook_url == "https://feishu.example/webhook/abc"


@pytest.mark.asyncio
async def test_put_config_partial_update_keeps_other_fields(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_user(db_session)
    config = NotificationConfig(
        user_id=user.id,
        feishu_webhook_url="https://feishu.example/webhook/keep",
        tg_bot_token="old",
        tg_chat_id="old_chat",
    )
    db_session.add(config)
    await db_session.commit()

    # 只更新 tg_chat_id · 其他保持
    r = await client.put(
        "/api/v1/notifications/config",
        json={"tg_chat_id": "new_chat"},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["feishu_webhook_url"] == "https://feishu.example/webhook/keep"
    assert body["tg_chat_id"] == "new_chat"


@pytest.mark.asyncio
async def test_put_config_empty_string_clears_field(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_user(db_session)
    config = NotificationConfig(
        user_id=user.id,
        feishu_webhook_url="https://feishu.example/webhook/x",
    )
    db_session.add(config)
    await db_session.commit()

    r = await client.put(
        "/api/v1/notifications/config",
        json={"feishu_webhook_url": ""},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["feishu_webhook_url"] is None
    assert body["has_feishu"] is False


@pytest.mark.asyncio
async def test_post_test_unconfigured_400(
    client: AsyncClient, db_session: AsyncSession,
):
    user = await make_user(db_session)
    await db_session.commit()

    r = await client.post(
        "/api/v1/notifications/test?channel=feishu",
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 400
    assert "未配置" in r.json()["detail"]


@pytest.mark.asyncio
async def test_post_test_channel_unconfigured_returns_error_payload(
    client: AsyncClient, db_session: AsyncSession,
):
    """已配置另一通道 · 但请求测的通道未配 · 返回 200 + ok=false。"""
    user = await make_user(db_session)
    config = NotificationConfig(
        user_id=user.id,
        feishu_webhook_url="https://feishu.example/webhook/x",
    )
    db_session.add(config)
    await db_session.commit()

    # tg 未配置
    r = await client.post(
        "/api/v1/notifications/test?channel=telegram",
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "未配置" in (body["error"] or "")
