"""通知配置路由 pytest · 0025 G2a 统一 bot(飞书 / per-user token 已移除)。

涵盖:
- GET /config 未配置返默认对象(未绑定 + 开关 true)
- GET /config 已绑定(tg_chat_id)→ has_telegram true
- PUT /config 只更新总开关(lazy create)
- PUT /config 拒绝已移除字段(extra=forbid → 422)
- POST /test 无配置 400 · 已配置但未绑定 → 200 ok=false
"""

from __future__ import annotations

from unittest.mock import AsyncMock

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


# ============================================================
# 0028 N2 · quiet_hours 4 字段对前端暴露(GET 返 + PUT 接受 + 校验)
# ============================================================


@pytest.mark.asyncio
async def test_get_config_unconfigured_includes_quiet_hours_defaults(
    client: AsyncClient, db_session: AsyncSession,
):
    """未配置用户 GET → 默认 quiet_hours(对齐 DB server_default · DP4+DP5)。"""
    user = await make_user(db_session)
    await db_session.commit()

    r = await client.get(
        "/api/v1/notifications/config", headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["quiet_hours_enabled"] is True
    assert body["quiet_hours_start"] == 23
    assert body["quiet_hours_end"] == 7
    assert body["quiet_hours_tz"] == "Asia/Shanghai"


@pytest.mark.asyncio
async def test_get_config_returns_persisted_quiet_hours(
    client: AsyncClient, db_session: AsyncSession,
):
    """已落 DB 的 quiet_hours 字段被原样返回。"""
    user = await make_user(db_session)
    db_session.add(NotificationConfig(
        user_id=user.id,
        quiet_hours_enabled=False,
        quiet_hours_start=22,
        quiet_hours_end=8,
        quiet_hours_tz="UTC",
    ))
    await db_session.commit()

    r = await client.get(
        "/api/v1/notifications/config", headers=await _auth(user, db_session),
    )
    body = r.json()
    assert body["quiet_hours_enabled"] is False
    assert body["quiet_hours_start"] == 22
    assert body["quiet_hours_end"] == 8
    assert body["quiet_hours_tz"] == "UTC"


@pytest.mark.asyncio
async def test_put_config_updates_quiet_hours(
    client: AsyncClient, db_session: AsyncSession,
):
    """PUT 局部更新 quiet_hours · 跨夜 + 非默认时区都能落库。"""
    user = await make_user(db_session)
    await db_session.commit()

    r = await client.put(
        "/api/v1/notifications/config",
        json={
            "quiet_hours_enabled": True,
            "quiet_hours_start": 23,
            "quiet_hours_end": 6,
            "quiet_hours_tz": "America/New_York",
        },
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["quiet_hours_start"] == 23
    assert body["quiet_hours_end"] == 6
    assert body["quiet_hours_tz"] == "America/New_York"

    # DB lazy create + 原值未传字段保持默认(总开关默认 True)
    config = await db_session.scalar(
        select(NotificationConfig).where(NotificationConfig.user_id == user.id),
    )
    assert config is not None
    assert config.quiet_hours_start == 23
    assert config.quiet_hours_end == 6
    assert config.quiet_hours_tz == "America/New_York"
    assert config.trade_alert_enabled is True  # 没传 · 保持 server_default


@pytest.mark.asyncio
async def test_put_config_partial_quiet_hours_keeps_unchanged_fields(
    client: AsyncClient, db_session: AsyncSession,
):
    """只传 quiet_hours_enabled · start/end/tz 保持原值。"""
    user = await make_user(db_session)
    db_session.add(NotificationConfig(
        user_id=user.id,
        quiet_hours_start=22, quiet_hours_end=8, quiet_hours_tz="Asia/Tokyo",
    ))
    await db_session.commit()

    r = await client.put(
        "/api/v1/notifications/config",
        json={"quiet_hours_enabled": False},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["quiet_hours_enabled"] is False
    # 其余 quiet_hours 字段未变
    assert body["quiet_hours_start"] == 22
    assert body["quiet_hours_end"] == 8
    assert body["quiet_hours_tz"] == "Asia/Tokyo"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"quiet_hours_start": 24}, "quiet_hours_start"),    # > 23
        ({"quiet_hours_start": -1}, "quiet_hours_start"),    # < 0
        ({"quiet_hours_end": 99}, "quiet_hours_end"),
        ({"quiet_hours_end": -5}, "quiet_hours_end"),
        ({"quiet_hours_tz": "Mars/Olympus"}, "quiet_hours_tz"),  # 非法 IANA
        ({"quiet_hours_tz": ""}, "quiet_hours_tz"),               # 空串
    ],
)
async def test_put_config_rejects_invalid_quiet_hours(
    client: AsyncClient, db_session: AsyncSession,
    payload: dict, field: str,
):
    """边界 + 非法时区一律 422 · 不污染 DB。"""
    user = await make_user(db_session)
    await db_session.commit()

    r = await client.put(
        "/api/v1/notifications/config",
        json=payload,
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 422, f"应拒绝 {field}={payload}"

    # 失败的 PUT 不应 lazy create config(只在合法 PUT 才写)
    config = await db_session.scalar(
        select(NotificationConfig).where(NotificationConfig.user_id == user.id),
    )
    assert config is None


# ── 做T M2-4 · 做T信号拆两体系开关(★两字段都 Pro 双层 gate · 默认 false · 后端二道 gate)──────────

@pytest.mark.asyncio
async def test_dott_split_default_false(
    client: AsyncClient, db_session: AsyncSession,
):
    # ★两体系开关都默认 false(opt-in · 不给存量用户群发)· 旧 dott_alert_enabled 不再暴露
    user = await make_user(db_session)
    await db_session.commit()
    r = await client.get(
        "/api/v1/notifications/config", headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dott_digest_enabled"] is False
    assert body["dott_transition_enabled"] is False
    assert "dott_alert_enabled" not in body  # 旧字段废弃 · API 不再暴露


@pytest.mark.asyncio
async def test_dott_split_pro_can_enable_each(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    # Pro 用户分别开两体系 → 200 · 落库 true(各自独立)
    monkeypatch.setattr(
        "app.api.v1.notifications.resolve_plan", AsyncMock(return_value="pro"),
    )
    user = await make_user(db_session)
    await db_session.commit()
    r = await client.put(
        "/api/v1/notifications/config",
        json={"dott_digest_enabled": True, "dott_transition_enabled": True},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dott_digest_enabled"] is True
    assert body["dott_transition_enabled"] is True
    config = await db_session.scalar(
        select(NotificationConfig).where(NotificationConfig.user_id == user.id),
    )
    assert config is not None
    assert config.dott_digest_enabled is True
    assert config.dott_transition_enabled is True


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["dott_digest_enabled", "dott_transition_enabled"])
async def test_dott_split_non_pro_enable_rejected(
    field: str,
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    # ★两字段【都】保留 M2-2 的 Pro 二道 gate:非 Pro 设任一为 true → 403 · DB 不写入(防 F12)
    monkeypatch.setattr(
        "app.api.v1.notifications.resolve_plan", AsyncMock(return_value="free"),
    )
    user = await make_user(db_session)
    await db_session.commit()
    r = await client.put(
        "/api/v1/notifications/config",
        json={field: True},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 403
    assert "Pro" in r.json()["detail"]
    config = await db_session.scalar(
        select(NotificationConfig).where(NotificationConfig.user_id == user.id),
    )
    if config is not None:
        assert getattr(config, field) is False


@pytest.mark.asyncio
async def test_dott_split_non_pro_can_disable(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    # 非 Pro 设 false(退订)允许 · gate 只拦「开启」(两字段同)
    monkeypatch.setattr(
        "app.api.v1.notifications.resolve_plan", AsyncMock(return_value="free"),
    )
    user = await make_user(db_session)
    await db_session.commit()
    r = await client.put(
        "/api/v1/notifications/config",
        json={"dott_digest_enabled": False, "dott_transition_enabled": False},
        headers=await _auth(user, db_session),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["dott_digest_enabled"] is False
    assert body["dott_transition_enabled"] is False
