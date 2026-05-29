"""飞书入站走 handle_inbound pytest · ADR 0032 阶段三。

证明:飞书 InboundMessage 复用阶段一中立核心 handle_inbound(逻辑一份),
+ ★ 身份只从 channel_uid 解析(文本里的伪 open_id 不被采信)+ session 键走 feishu 前缀。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationConfig
from app.models.virtual import PositionSide, VirtualPosition
from app.services.bot import router
from app.services.bot.replies import InboundMessage, ReplyModel
from tests.factories import make_user, make_virtual_account


class _FakeRedis:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self._d.get(key)

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self._d[key] = value

    async def delete(self, key: str) -> None:
        self._d.pop(key, None)

    async def incr(self, key: str) -> int:
        self._counters[key] = self._counters.get(key, 0) + 1
        return self._counters[key]

    async def expire(self, _key: str, _ttl: int) -> None:
        return None


class _FakeCH:
    def __init__(self) -> None:
        self._client = object()

    async def select_kline(self, **_kwargs: Any) -> list[Any]:
        return []


async def _bind_feishu(db: AsyncSession, user_id: Any, open_id: str) -> None:
    db.add(NotificationConfig(user_id=user_id, feishu_open_id=open_id))
    await db.commit()


@pytest.mark.asyncio
async def test_feishu_text_menu_reuses_handle_inbound(db_session: AsyncSession) -> None:
    """飞书发 /menu → 同一 handle_inbound → 主菜单 ReplyModel(逻辑复用,非另写)。"""
    user = await make_user(db_session)
    await _bind_feishu(db_session, user.id, "ou_alice")
    msg = InboundMessage(
        channel="feishu", channel_uid="ou_alice", kind="text", text="/menu",
    )
    reply = await router.handle_inbound(db_session, _FakeRedis(), _FakeCH(), msg)  # type: ignore[arg-type]
    assert isinstance(reply, ReplyModel)
    assert reply.title == "迷你终端"
    assert reply.buttons


@pytest.mark.asyncio
async def test_feishu_positions_query(db_session: AsyncSession) -> None:
    """飞书点「我的持仓」按钮 → handle_inbound → 持仓 ReplyModel(只读查询复用)。"""
    user = await make_user(db_session)
    acct = await make_virtual_account(db_session, user_id=user.id, market="us")
    db_session.add(VirtualPosition(
        account_id=acct.id, symbol="NVDA", market="us",
        position_side=PositionSide.LONG,
        quantity=Decimal("5"), avg_entry_price=Decimal("100"),
    ))
    await _bind_feishu(db_session, user.id, "ou_bob")
    msg = InboundMessage(
        channel="feishu", channel_uid="ou_bob", kind="button", action="act:positions",
    )
    reply = await router.handle_inbound(db_session, _FakeRedis(), _FakeCH(), msg)  # type: ignore[arg-type]
    assert reply.title == "持仓"
    assert "NVDA" in reply.text


@pytest.mark.asyncio
async def test_feishu_unbound_open_id_gets_not_bound(db_session: AsyncSession) -> None:
    """🔴 身份红线:未绑定的 open_id → not_bound,即便文本里塞了别人的 open_id 也不串号。"""
    user = await make_user(db_session)
    await _bind_feishu(db_session, user.id, "ou_real")
    # channel_uid 是未绑定的 ou_stranger;文本里伪造 "ou_real" 试图冒充 → 不被采信
    msg = InboundMessage(
        channel="feishu", channel_uid="ou_stranger", kind="text",
        text="/menu open_id=ou_real",
    )
    reply = await router.handle_inbound(db_session, _FakeRedis(), _FakeCH(), msg)  # type: ignore[arg-type]
    # resolve_user_id 只认 channel_uid=ou_stranger(未绑定)→ 引导绑定,绝不返回 ou_real 的数据
    assert reply.title is None  # build_not_bound 无标题(仅品牌头)
    assert "还没绑定" in reply.text


@pytest.mark.asyncio
async def test_feishu_session_uses_feishu_prefix(db_session: AsyncSession) -> None:
    """session 键按 (channel,uid) → 飞书用 feishu_session: 前缀(不与 TG 的 tg_session: 串)。"""
    user = await make_user(db_session)
    await _bind_feishu(db_session, user.id, "ou_carol")
    redis = _FakeRedis()
    msg = InboundMessage(
        channel="feishu", channel_uid="ou_carol", kind="button", action="ask:quote:cn",
    )
    await router.handle_inbound(db_session, redis, _FakeCH(), msg)  # type: ignore[arg-type]
    assert "feishu_session:ou_carol" in redis._d
    assert "tg_session:ou_carol" not in redis._d  # 绝不写 TG 前缀
