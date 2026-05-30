"""Telegram 统一 bot 路由 pytest · 0024 v2 · M1-G G1。

覆盖:
- bind-token:未配 bot → 503 · 配了 → 返回 token 并存入 Redis
- webhook:secret_token 头校验(坏 secret → 403)
- /start <token>:有效 token → 写 tg_chat_id + 消费 token · 无效 token → 不绑定
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_clickhouse_optional
from app.core.config import settings
from app.core.redis_client import get_redis
from app.main import app
from app.models.notification import NotificationConfig
from app.models.user import User
from app.services.auth import issue_session
from app.services.notifications.telegram_bind import (
    _bind_key,
    create_bind_token,
    webhook_secret,
)
from tests.factories import make_user

_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


async def _auth_headers(user: User, db: AsyncSession) -> dict[str, str]:
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


class _FakeRedis:
    """最小内存 Redis 替身 · 只实现绑定 token 用到的 get/setex/delete。"""

    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self._d[key] = value

    async def get(self, key: str) -> str | None:
        return self._d.get(key)

    async def delete(self, key: str) -> None:
        self._d.pop(key, None)


@pytest.fixture
def fake_redis() -> Iterator[_FakeRedis]:
    fake = _FakeRedis()
    app.dependency_overrides[get_redis] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_redis, None)


@pytest.fixture
def bot_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """临时配上 bot token(测 bind-token 成功路径)· monkeypatch 自动还原。"""
    monkeypatch.setattr(settings, "tg_bot_token", "123456:FAKE_TEST_TOKEN")


# ── bind-token ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bind_token_requires_bot_configured(
    client: AsyncClient, db_session: AsyncSession, fake_redis: _FakeRedis,
):
    """未配 TG_BOT_TOKEN(默认空)→ 503。"""
    user = await make_user(db_session, demo_prefilled=True)
    await db_session.commit()

    r = await client.post(
        "/api/v1/telegram/bind-token", headers=await _auth_headers(user, db_session),
    )
    assert r.status_code == 503
    assert fake_redis._d == {}  # 没生成 token


@pytest.mark.asyncio
@pytest.mark.usefixtures("bot_configured")
async def test_bind_token_success_stores_in_redis(
    client: AsyncClient,
    db_session: AsyncSession,
    fake_redis: _FakeRedis,
):
    """配了 bot → 返回 token + expires_in · token 已存 Redis。"""
    user = await make_user(db_session, demo_prefilled=True)
    await db_session.commit()

    r = await client.post(
        "/api/v1/telegram/bind-token", headers=await _auth_headers(user, db_session),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["token"]
    assert body["expires_in"] == settings.tg_bind_token_ttl_seconds
    # token 已存 Redis,且映射到该用户
    assert fake_redis._d.get(_bind_key(body["token"])) == str(user.id)


# ── webhook ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_redis")
async def test_webhook_rejects_bad_secret(client: AsyncClient):
    """secret_token 头不对 → 403。"""
    r = await client.post(
        "/api/v1/telegram/webhook",
        json={"message": {"chat": {"id": 1}, "text": "/start x"}},
        headers={_SECRET_HEADER: "wrong-secret"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_webhook_start_binds_chat_id(
    client: AsyncClient, db_session: AsyncSession, fake_redis: _FakeRedis,
):
    """有效 secret + 有效 /start token → 写 tg_chat_id + 消费 token。

    token 留空(settings.tg_bot_token 默认空)→ 不发回执(无网络),仅测绑定写库。
    """
    user = await make_user(db_session, demo_prefilled=True)
    await db_session.commit()
    token = await create_bind_token(fake_redis, user.id)  # type: ignore[arg-type]

    r = await client.post(
        "/api/v1/telegram/webhook",
        json={"message": {"chat": {"id": 998877}, "text": f"/start {token}"}},
        headers={_SECRET_HEADER: webhook_secret()},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    # tg_chat_id 已写入该用户配置
    config = await db_session.scalar(
        select(NotificationConfig).where(NotificationConfig.user_id == user.id),
    )
    assert config is not None
    assert config.tg_chat_id == "998877"
    # token 已被消费(一次性)
    assert fake_redis._d.get(_bind_key(token)) is None


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_redis")
async def test_webhook_invalid_token_no_bind(
    client: AsyncClient, db_session: AsyncSession,
):
    """有效 secret 但 token 不存在 → 200 但不绑定。"""
    user = await make_user(db_session, demo_prefilled=True)
    await db_session.commit()

    r = await client.post(
        "/api/v1/telegram/webhook",
        json={"message": {"chat": {"id": 555}, "text": "/start bogustoken"}},
        headers={_SECRET_HEADER: webhook_secret()},
    )
    assert r.status_code == 200

    config = await db_session.scalar(
        select(NotificationConfig).where(NotificationConfig.user_id == user.id),
    )
    # 没有为该用户写入任何绑定
    assert config is None or config.tg_chat_id is None


# ── G3 · 交互(命令 / 按钮回调)+ 解绑 ───────────────────────────────


class _FakeCH:
    """webhook G3 分支用的 CH 替身(select_kline 返回空 · 不影响 200/路由验证)。"""

    def __init__(self) -> None:
        self._client = object()

    async def select_kline(self, **_kwargs: object) -> list[object]:
        return []


@pytest.fixture
def ch_override() -> Iterator[_FakeCH]:
    fake = _FakeCH()
    app.dependency_overrides[get_clickhouse_optional] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_clickhouse_optional, None)


@pytest.fixture
def captured_tg(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """捕获 webhook 后台发出的 telegram 调用(配合 bot_configured 触发发送)。"""
    calls: dict[str, list] = {"send": [], "edit": [], "answer": []}

    async def _send(_t: str, chat_id: str, text: str, **kw: object) -> dict[str, bool]:
        calls["send"].append((chat_id, text, kw.get("reply_markup")))
        return {"ok": True}

    async def _edit(
        _t: str, chat_id: str, message_id: int, text: str, **kw: object,
    ) -> dict[str, bool]:
        calls["edit"].append((chat_id, message_id, text, kw.get("reply_markup")))
        return {"ok": True}

    async def _answer(_t: str, cq_id: str, **_kw: object) -> dict[str, bool]:
        calls["answer"].append(cq_id)
        return {"ok": True}

    monkeypatch.setattr("app.services.notifications.telegram.send", _send)
    monkeypatch.setattr("app.services.notifications.telegram.edit_message_text", _edit)
    monkeypatch.setattr(
        "app.services.notifications.telegram.answer_callback_query", _answer,
    )
    return calls


async def _bind_chat(db: AsyncSession, user: User, chat_id: str) -> None:
    db.add(NotificationConfig(user_id=user.id, tg_chat_id=chat_id))
    await db.commit()


@pytest.mark.asyncio
@pytest.mark.usefixtures("bot_configured", "fake_redis", "ch_override")
async def test_webhook_command_menu_bound(
    client: AsyncClient,
    db_session: AsyncSession,
    captured_tg: dict[str, list],
):
    """已绑定 chat 发 /menu → 200 · 后台发出带 inline 键盘的菜单。"""
    user = await make_user(db_session, demo_prefilled=True)
    await _bind_chat(db_session, user, "987")

    r = await client.post(
        "/api/v1/telegram/webhook",
        json={"message": {"chat": {"id": 987}, "text": "/menu"}},
        headers={_SECRET_HEADER: webhook_secret()},
    )
    assert r.status_code == 200
    assert captured_tg["send"], "应有一条菜单回执"
    chat_id, text, markup = captured_tg["send"][0]
    assert chat_id == "987"
    assert markup is not None
    assert "inline_keyboard" in markup
    # ADR 0032 阶段四-A 免责分级:主菜单是【展示类】→ 不带免责(交易类才带)·
    # 交易类必带免责由 test_bot_golden 守卫钉死。
    assert "不构成投资建议" not in text
    assert "迷你终端" in text  # 仍是主菜单


@pytest.mark.asyncio
@pytest.mark.usefixtures("bot_configured", "fake_redis", "ch_override")
async def test_webhook_callback_edits_message(
    client: AsyncClient,
    db_session: AsyncSession,
    captured_tg: dict[str, list],
):
    """已绑定 chat 点按钮 → 200 · 消除 loading + 原地编辑消息。"""
    user = await make_user(db_session, demo_prefilled=True)
    await _bind_chat(db_session, user, "987")

    r = await client.post(
        "/api/v1/telegram/webhook",
        json={
            "callback_query": {
                "id": "cb-1", "data": "menu:main",
                "message": {"message_id": 55, "chat": {"id": 987}},
            },
        },
        headers={_SECRET_HEADER: webhook_secret()},
    )
    assert r.status_code == 200
    assert captured_tg["answer"] == ["cb-1"]
    assert captured_tg["edit"], "应原地编辑消息"
    chat_id, message_id, _text, markup = captured_tg["edit"][0]
    assert chat_id == "987"
    assert message_id == 55  # noqa: PLR2004
    assert markup is not None


@pytest.mark.asyncio
@pytest.mark.usefixtures("bot_configured", "fake_redis", "ch_override")
async def test_webhook_command_unbound_prompts_bind(
    client: AsyncClient,
    captured_tg: dict[str, list],
):
    """未绑定 chat 发命令 → 引导绑定,绝不返回任何账号数据。"""
    r = await client.post(
        "/api/v1/telegram/webhook",
        json={"message": {"chat": {"id": 40404}, "text": "/menu"}},
        headers={_SECRET_HEADER: webhook_secret()},
    )
    assert r.status_code == 200
    assert captured_tg["send"]
    _chat, text, _markup = captured_tg["send"][0]
    assert "绑定" in text


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_redis")
async def test_unbind_clears_chat_id(
    client: AsyncClient, db_session: AsyncSession,
):
    """解绑端点:清空当前用户 tg_chat_id(D7)· 幂等。"""
    user = await make_user(db_session, demo_prefilled=True)
    await _bind_chat(db_session, user, "777")

    r = await client.post(
        "/api/v1/telegram/unbind", headers=await _auth_headers(user, db_session),
    )
    assert r.status_code == 200
    assert r.json() == {"unbound": True}

    config = await db_session.scalar(
        select(NotificationConfig).where(NotificationConfig.user_id == user.id),
    )
    assert config is not None
    assert config.tg_chat_id is None
