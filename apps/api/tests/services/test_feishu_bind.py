"""飞书绑定 pytest · ADR 0032 阶段三:bind-token 机制对称 TG + 身份红线。

覆盖:create_bind_token、显式/隐式有效绑定、无效码、非绑定消息(ignored)、
一 open_id 一账号、★ open_id 只从入参取(不从文本)。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationConfig
from app.services.notifications.feishu_bind import (
    create_bind_token,
    handle_feishu_bind,
    peek_bind_token,
)
from tests.factories import make_user


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


async def _config(db: AsyncSession, user_id: object) -> NotificationConfig | None:
    return await db.scalar(
        select(NotificationConfig).where(NotificationConfig.user_id == user_id),
    )


@pytest.mark.asyncio
async def test_bind_token_roundtrip() -> None:
    redis = _FakeRedis()
    import uuid
    uid = uuid.uuid4()
    token = await create_bind_token(redis, uid)
    assert await peek_bind_token(redis, token) == str(uid)
    assert redis.store[f"feishu_bind:{token}"] == str(uid)  # 通道专属前缀


@pytest.mark.asyncio
async def test_explicit_bind_writes_open_id(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    redis = _FakeRedis()
    token = await create_bind_token(redis, user.id)
    res = await handle_feishu_bind(
        db_session, redis, open_id="ou_alice", text=f"/bind {token}",
    )
    assert res.kind == "bound"
    cfg = await _config(db_session, user.id)
    assert cfg is not None
    assert cfg.feishu_open_id == "ou_alice"
    # 一次性 token 已 consume
    assert await peek_bind_token(redis, token) is None


@pytest.mark.asyncio
async def test_implicit_paste_code_binds(db_session: AsyncSession) -> None:
    """直接粘贴绑定码(无 /bind 前缀)也能绑(单词 · 高熵 token)。"""
    user = await make_user(db_session)
    redis = _FakeRedis()
    token = await create_bind_token(redis, user.id)
    res = await handle_feishu_bind(db_session, redis, open_id="ou_bob", text=token)
    assert res.kind == "bound"


@pytest.mark.asyncio
async def test_explicit_bad_code_rejected(db_session: AsyncSession) -> None:
    redis = _FakeRedis()
    res = await handle_feishu_bind(
        db_session, redis, open_id="ou_x", text="/bind not-a-real-token",
    )
    assert res.kind == "invalid_token"


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["/menu", "BTC", "你好 世界", "/price NVDA"])
async def test_non_bind_message_ignored(db_session: AsyncSession, text: str) -> None:
    """普通消息(命令/标的/多词)不被当成绑定 → ignored(交 handle_inbound 处理)。"""
    redis = _FakeRedis()
    res = await handle_feishu_bind(db_session, redis, open_id="ou_x", text=text)
    assert res.kind == "ignored"


@pytest.mark.asyncio
async def test_one_open_id_one_account(db_session: AsyncSession) -> None:
    """open_id 已绑账号 B → 账号 A 想绑同一 open_id 被拒(对称 TG 一 chat 一账号)。"""
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    db_session.add(NotificationConfig(user_id=user_b.id, feishu_open_id="ou_taken"))
    await db_session.commit()
    redis = _FakeRedis()
    token = await create_bind_token(redis, user_a.id)
    res = await handle_feishu_bind(
        db_session, redis, open_id="ou_taken", text=f"/bind {token}",
    )
    assert res.kind == "open_id_taken"
    # A 没有被写入(绑定失败)
    cfg_a = await _config(db_session, user_a.id)
    assert cfg_a is None or cfg_a.feishu_open_id != "ou_taken"


@pytest.mark.asyncio
async def test_open_id_only_from_param_not_text(db_session: AsyncSession) -> None:
    """🔴 身份红线:写入的 open_id 来自【入参】(已验签事件),文本里的伪 open_id 不被采信。"""
    user = await make_user(db_session)
    redis = _FakeRedis()
    token = await create_bind_token(redis, user.id)
    # 文本里塞一个伪 open_id,但入参 open_id=ou_real
    res = await handle_feishu_bind(
        db_session, redis, open_id="ou_real", text=f"/bind {token} open_id=ou_FORGED",
    )
    # text 含空格 → token 候选只取前缀后第一个词?显式前缀取剩余整串 → token 含空格 → 无效
    # 这里验证:即便绑定成功路径,写的也只能是入参 ou_real,绝不会是 ou_FORGED
    cfg = await _config(db_session, user.id)
    if res.kind == "bound":
        assert cfg is not None
        assert cfg.feishu_open_id == "ou_real"
    # 不论 bound 与否,数据库里都不可能出现 ou_FORGED
    forged = await db_session.scalar(
        select(NotificationConfig).where(
            NotificationConfig.feishu_open_id == "ou_FORGED",
        ),
    )
    assert forged is None
