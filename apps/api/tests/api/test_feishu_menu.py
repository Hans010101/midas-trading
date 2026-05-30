"""飞书常驻菜单(application.bot.menu_v6)pytest · ADR 0032 阶段四后续(体验打磨二批)。

★ 菜单点击复用现成架构:event_key 当 action → handle_inbound → render_for_feishu → 后台发新卡。
覆盖:身份红线(open_id 只从 operator.operator_id.open_id 取)· 路由正确(menu:quote→选市场卡)·
🔴 下单二次确认 gate 不因菜单弱化(伪造 event_key=ordok 无确认态 → 不成交)· 缺身份忽略。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.feishu import _handle_menu_action, _parse_menu_event
from app.models.notification import NotificationConfig
from app.models.virtual import VirtualPosition
from tests.factories import make_user, make_virtual_account


class _FakeRedis:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}
        self._c: dict[str, int] = {}

    async def get(self, k: str) -> str | None:
        return self._d.get(k)

    async def setex(self, k: str, _t: int, v: str) -> None:
        self._d[k] = v

    async def delete(self, k: str) -> None:
        self._d.pop(k, None)

    async def incr(self, k: str) -> int:
        self._c[k] = self._c.get(k, 0) + 1
        return self._c[k]

    async def expire(self, _k: str, _t: int) -> None:
        return None


class _FakeCH:
    def __init__(self, klines: list[Any] | None = None) -> None:
        self._klines = klines or []
        self._client = object()

    async def select_kline(self, **_kw: Any) -> list[Any]:
        return list(self._klines)


class _CaptureBg:
    """假 BackgroundTasks · 捕获 add_task(_send_card_safe, open_id, card) 而不真发。"""

    def __init__(self) -> None:
        self.tasks: list[tuple[Any, tuple[Any, ...]]] = []

    def add_task(self, fn: Any, *args: Any, **_kw: Any) -> None:
        self.tasks.append((fn, args))


def _bar(close: float) -> SimpleNamespace:
    return SimpleNamespace(close=Decimal(str(close)), volume=Decimal("1"))


def _menu_event(open_id: str, event_key: str) -> dict[str, Any]:
    """application.bot.menu_v6 事件体 · open_id 在 operator.operator_id(嵌套)。"""
    return {"operator": {"operator_id": {"open_id": open_id}}, "event_key": event_key}


def _sent_card(bg: _CaptureBg) -> dict[str, Any]:
    assert bg.tasks, "应有一条后台发卡任务"
    return bg.tasks[0][1][1]  # (fn, (open_id, card)) → card


def _body(card: dict[str, Any]) -> str:
    return "\n".join(
        e["text"]["content"] for e in card["elements"]
        if e["tag"] == "div" and "text" in e
    )


def _actions(card: dict[str, Any]) -> list[str | None]:
    return [
        a.get("value", {}).get("action")
        for e in card["elements"] if e["tag"] == "action"
        for a in e["actions"]
    ]


async def _bind(db: AsyncSession, user_id: Any, open_id: str) -> None:
    db.add(NotificationConfig(user_id=user_id, feishu_open_id=open_id))
    await db.commit()


async def _positions(db: AsyncSession, account_id: int) -> list[VirtualPosition]:
    rows = await db.scalars(
        select(VirtualPosition).where(VirtualPosition.account_id == account_id),
    )
    return list(rows)


# ── 身份红线(纯解析)─────────────────────────────────────────────────


def test_parse_menu_event_open_id_from_operator_id_only() -> None:
    """🔴 open_id 只取自 operator.operator_id.open_id(嵌套)· 顶层伪 open_id 不被采信。"""
    event = {
        "open_id": "ou_FORGED",  # 顶层伪造 · 不应被读
        "operator": {"operator_id": {"open_id": "ou_real", "user_id": "u1"}},
        "event_key": "menu:order",
    }
    open_id, event_key = _parse_menu_event(event)
    assert open_id == "ou_real"  # 来自 operator.operator_id,不是顶层 ou_FORGED
    assert event_key == "menu:order"


def test_parse_menu_event_missing_operator_returns_none() -> None:
    open_id, event_key = _parse_menu_event({"event_key": "menu:quote"})
    assert open_id is None
    assert event_key == "menu:quote"


# ── 路由:菜单点击 → handle_inbound → 发新卡 ──────────────────────────


@pytest.mark.asyncio
async def test_menu_routes_to_handle_inbound(db_session: AsyncSession) -> None:
    """点「行情」菜单(event_key=menu:quote)→ 后台发【选市场卡】(走 handle_inbound)。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, "ou_menu")
    redis, ch, bg = _FakeRedis(), _FakeCH([_bar(100.0)]), _CaptureBg()

    await _handle_menu_action(
        db_session, redis, ch, bg, _menu_event("ou_menu", "menu:quote"),  # type: ignore[arg-type]
    )
    card = _sent_card(bg)
    assert "先选市场" in _body(card)  # menu:quote → build_market_picker("quote")
    assert any(a and a.startswith("ask:quote:") for a in _actions(card))


@pytest.mark.asyncio
async def test_menu_no_open_id_ignored(db_session: AsyncSession) -> None:
    """🔴 缺 operator.operator_id.open_id → 不处理、不发卡(身份缺失不臆测)。"""
    redis, ch, bg = _FakeRedis(), _FakeCH([_bar(100.0)]), _CaptureBg()
    await _handle_menu_action(
        db_session, redis, ch, bg, {"event_key": "menu:quote"},  # type: ignore[arg-type]
    )
    assert bg.tasks == []  # 没有任何发卡


# ── 🔴 下单二次确认 gate 不因菜单弱化 ─────────────────────────────────


@pytest.mark.asyncio
async def test_menu_forged_ordok_does_not_execute(db_session: AsyncSession) -> None:
    """🔴 命门:把菜单 event_key 伪造成 ordok,但无 order_confirm 会话 → 绝不成交。

    菜单点击 ≡ 点按钮,execute 仍只由 router._handle_confirm 的 order_confirm gate 触发;
    菜单只是入口,绕不过二次确认(与 card/TG 同一闸)。
    """
    user = await make_user(db_session)
    acct = await make_virtual_account(db_session, user_id=user.id, market="us")
    await _bind(db_session, user.id, "ou_forge")
    redis, ch, bg = _FakeRedis(), _FakeCH([_bar(100.0)]), _CaptureBg()

    await _handle_menu_action(
        db_session, redis, ch, bg, _menu_event("ou_forge", "ordok"),  # type: ignore[arg-type]
    )
    assert not await _positions(db_session, acct.id), "菜单伪造 ordok 绝不能成交"
    card = _sent_card(bg)
    assert "成交" not in _body(card)  # 兜底回主菜单 · 不报成交
    assert "menu:order" in _actions(card)  # 主菜单(含下单入口)
