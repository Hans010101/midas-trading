"""bot 入站编排 pytest · 0025 M1-G G3。

重点:① 未绑定 → 引导绑定;② 命令 / 回调路由正确;③ 🔴 安全边界 —— user_id 只从
chat 绑定取(自选/持仓永远只返回该 chat 绑定账号的数据,跨用户隔离)。
"""

from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationConfig
from app.models.virtual import PositionSide, VirtualPosition
from app.services.bot import router
from tests.factories import make_user, make_virtual_account


class _FakeRedis:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._d.get(key)

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self._d[key] = value

    async def delete(self, key: str) -> None:
        self._d.pop(key, None)


class _FakeCH:
    def __init__(self, klines: list[Any] | None = None) -> None:
        self._klines = klines or []
        self._client = object()

    async def select_kline(self, **_kwargs: Any) -> list[Any]:
        return list(self._klines)


def _bar(close: float) -> SimpleNamespace:
    return SimpleNamespace(close=Decimal(str(close)), volume=Decimal("1"))


async def _bind(db: AsyncSession, user_id: Any, chat_id: int) -> None:
    db.add(NotificationConfig(user_id=user_id, tg_chat_id=str(chat_id)))
    await db.commit()


@pytest.mark.asyncio
async def test_command_unbound_prompts_binding(db_session: AsyncSession):
    """没绑定的 chat → 不泄露任何数据,引导去网页端绑定。"""
    reply = await router.handle_command(
        db_session, _FakeRedis(), _FakeCH(), 999, "/menu",  # type: ignore[arg-type]
    )
    assert "绑定" in reply.text
    assert reply.keyboard is None


@pytest.mark.asyncio
async def test_command_menu_when_bound(db_session: AsyncSession):
    user = await make_user(db_session)
    await _bind(db_session, user.id, 12345)
    reply = await router.handle_command(
        db_session, _FakeRedis(), _FakeCH(), 12345, "/menu",  # type: ignore[arg-type]
    )
    assert reply.keyboard is not None
    assert "inline_keyboard" in reply.keyboard


@pytest.mark.asyncio
async def test_callback_positions_bound(db_session: AsyncSession):
    user = await make_user(db_session)
    acct = await make_virtual_account(db_session, user_id=user.id, market="us")
    db_session.add(
        VirtualPosition(
            account_id=acct.id, symbol="NVDA", market="us",
            position_side=PositionSide.LONG,
            quantity=Decimal("5"), avg_entry_price=Decimal("100"),
        ),
    )
    await _bind(db_session, user.id, 222)

    reply = await router.handle_callback(
        db_session, _FakeRedis(), _FakeCH(), 222, "act:positions",  # type: ignore[arg-type]
    )
    assert "NVDA" in reply.text
    assert "模拟" in reply.text  # VIRTUAL 徽章 / 免责语境


@pytest.mark.asyncio
async def test_ask_quote_session_then_symbol(db_session: AsyncSession):
    user = await make_user(db_session)
    await _bind(db_session, user.id, 333)
    redis = _FakeRedis()
    ch = _FakeCH([_bar(100.0), _bar(120.0)])

    # 点「行情→美股」→ 写会话态 + 提示输代码
    ask = await router.handle_callback(
        db_session, redis, ch, 333, "ask:quote:us",  # type: ignore[arg-type]
    )
    assert "代码" in ask.text
    assert json.loads(redis._d["tg_session:333"]) == {"awaiting": "quote", "market": "us"}

    # 续输代码 → 行情卡
    quote = await router.handle_command(
        db_session, redis, ch, 333, "NVDA",  # type: ignore[arg-type]
    )
    assert "NVDA" in quote.text
    assert "tg_session:333" not in redis._d  # 会话已清


@pytest.mark.asyncio
async def test_user_isolation_positions(db_session: AsyncSession):
    """🔴 安全:chat 绑定 A,A 无持仓;B 有持仓 → 该 chat 查持仓返回空(绝不串到 B)。"""
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    acct_b = await make_virtual_account(db_session, user_id=user_b.id, market="us")
    db_session.add(
        VirtualPosition(
            account_id=acct_b.id, symbol="TSLA", market="us",
            position_side=PositionSide.LONG,
            quantity=Decimal("3"), avg_entry_price=Decimal("200"),
        ),
    )
    await _bind(db_session, user_a.id, 444)  # chat 444 绑定 A

    reply = await router.handle_callback(
        db_session, _FakeRedis(), _FakeCH(), 444, "act:positions",  # type: ignore[arg-type]
    )
    assert "TSLA" not in reply.text  # B 的持仓绝不出现
    assert "没有活仓" in reply.text


@pytest.mark.asyncio
async def test_unknown_callback_falls_back_to_menu(db_session: AsyncSession):
    user = await make_user(db_session)
    await _bind(db_session, user.id, 555)
    reply = await router.handle_callback(
        db_session, _FakeRedis(), _FakeCH(), 555, "bogus:xyz",  # type: ignore[arg-type]
    )
    assert reply.keyboard is not None
    assert "inline_keyboard" in reply.keyboard
