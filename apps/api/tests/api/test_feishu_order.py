"""飞书下单 + 二次确认卡 pytest · ADR 0032 阶段四-D(多通道收官 · 唯一碰下单红线)。

★ 本阶段【零下单逻辑新增】:飞书下单全程复用 handle_inbound 共享核心 ——
- 按钮步(omkt / odir / ordok / ordno)走【真实飞书 webhook 入口】_handle_card_action
  (card.action.trigger → 解析已验签 open_id → InboundMessage → handle_inbound → 原地刷新卡);
- 输标的那步(text)走 handle_inbound,与 webhook 的 _handle_message 构造的 InboundMessage
  完全一致(channel="feishu" · kind="text")· 此处直调核心使断言确定(_handle_message 走后台发卡)。

★★ 下单二次确认红线(本文件的命门):
- execute 全局唯一调用点 = router._handle_confirm · gate = session.step == "order_confirm";
- order_confirm 态【只能】由 _handle_direction(odir 点击 → build_preview 成功)写入;
- 飞书「确认下单」按钮 = card.action.trigger(action=ordok)→ 同一 _handle_button 的 ordok 分支
  → 同一 _handle_confirm → 同一 gate · 飞书【绝不另写下单逻辑】。
飞书侧红线测试:伪造 ordok(无确认态)不成交 + 选市场就跳 ordok 不成交 + 完整流程才成交。
通道无关的三条红线(test_ordok_without_confirm / _skipping_symbol / _at_direction)在
tests/services/test_bot_router.py 继续守门(本文件不重复,只补飞书入口的等价证明)。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.feishu import _handle_card_action
from app.models.notification import NotificationConfig
from app.models.virtual import VirtualPosition
from app.services.bot.replies import InboundMessage
from app.services.bot.router import handle_inbound
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


def _bar(close: float) -> SimpleNamespace:
    return SimpleNamespace(close=Decimal(str(close)), volume=Decimal("1"))


def _ev(open_id: str, action: str) -> dict[str, Any]:
    """card.action.trigger 事件 · open_id 只取自 operator(已验签)· action 在 value 里。"""
    return {"operator": {"open_id": open_id}, "action": {"value": {"action": action}}}


def _card(resp: dict[str, Any]) -> dict[str, Any]:
    return resp["card"]["data"]


def _actions(resp: dict[str, Any]) -> list[str | None]:
    card = _card(resp)
    return [
        a.get("value", {}).get("action")
        for e in card["elements"] if e["tag"] == "action"
        for a in e["actions"]
    ]


def _body(resp: dict[str, Any]) -> str:
    card = _card(resp)
    return "\n".join(
        e["text"]["content"] for e in card["elements"]
        if e["tag"] == "div" and "text" in e
    )


async def _bind(db: AsyncSession, user_id: Any, open_id: str) -> None:
    db.add(NotificationConfig(user_id=user_id, feishu_open_id=open_id))
    await db.commit()


async def _positions(db: AsyncSession, account_id: int) -> list[VirtualPosition]:
    rows = await db.scalars(
        select(VirtualPosition).where(VirtualPosition.account_id == account_id),
    )
    return list(rows)


async def _feishu_text(
    db: AsyncSession, redis: _FakeRedis, ch: _FakeCH, open_id: str, text: str,
) -> Any:
    """输标的那步 · 与 webhook _handle_message 构造的 InboundMessage 完全一致(feishu·text)。"""
    msg = InboundMessage(
        channel="feishu", channel_uid=open_id, kind="text", text=text,
    )
    return await handle_inbound(db, redis, ch, msg)  # type: ignore[arg-type]


# ── 完整流程:选市场 → 标的 → 方向 → 二次确认卡 → 成交 ──────────────────


@pytest.mark.asyncio
async def test_feishu_full_order_flow_fills(db_session: AsyncSession) -> None:
    """飞书走完整下单流程 → 二次确认卡 → 确认 → 正常成交一笔虚拟单。"""
    user = await make_user(db_session)
    acct = await make_virtual_account(db_session, user_id=user.id, market="us")
    await _bind(db_session, user.id, "ou_buyer")
    redis, ch = _FakeRedis(), _FakeCH([_bar(100.0)])

    # ① 点🛒下单 → 选市场卡(card.action.trigger · 原地刷新)
    r0 = await _handle_card_action(db_session, redis, ch, _ev("ou_buyer", "menu:order"))  # type: ignore[arg-type]
    assert r0 is not None
    assert any(a and a.startswith("omkt:") for a in _actions(r0))

    # ② 选美股 → 提示输代码(原地刷新 · session→order_symbol)
    r1 = await _handle_card_action(db_session, redis, ch, _ev("ou_buyer", "omkt:us"))  # type: ignore[arg-type]
    assert r1 is not None
    assert "feishu_session:ou_buyer" in redis._d

    # ③ 发文本输代码 NVDA(走 handle_inbound · 同 _handle_message 构造)→ 方向卡
    dirs = await _feishu_text(db_session, redis, ch, "ou_buyer", "NVDA")
    assert any(a and a.startswith("odir:") for a in [
        b.action for row in dirs.buttons for b in row
    ])

    # ④ 选「买入」→ 二次确认卡(含 ordok/ordno · 交易免责)· 此刻【还没下单】
    rp = await _handle_card_action(db_session, redis, ch, _ev("ou_buyer", "odir:buy"))  # type: ignore[arg-type]
    assert rp is not None
    acts = _actions(rp)
    assert "ordok" in acts
    assert "ordno" in acts
    assert not await _positions(db_session, acct.id), "选方向只出确认卡,绝不能已成交"

    # ⑤ 点「✅确认下单」→ 真正成交(同一 _handle_confirm · 同一 gate)
    rr = await _handle_card_action(db_session, redis, ch, _ev("ou_buyer", "ordok"))  # type: ignore[arg-type]
    assert rr is not None
    assert "成交" in _body(rr)
    assert "header" not in _card(rr)  # 成交回执 prerendered · body 自带品牌 → 无 card header
    assert len(await _positions(db_session, acct.id)) == 1  # 成交一笔


@pytest.mark.asyncio
async def test_feishu_order_preview_is_confirm_card(db_session: AsyncSession) -> None:
    """二次确认卡本身保留(决策④:不加飞书原生弹窗,但确认卡必经)· 带交易口径免责。"""
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="us")
    await _bind(db_session, user.id, "ou_pv")
    redis, ch = _FakeRedis(), _FakeCH([_bar(100.0)])

    await _handle_card_action(db_session, redis, ch, _ev("ou_pv", "omkt:us"))  # type: ignore[arg-type]
    await _feishu_text(db_session, redis, ch, "ou_pv", "NVDA")
    rp = await _handle_card_action(db_session, redis, ch, _ev("ou_pv", "odir:buy"))  # type: ignore[arg-type]

    assert rp is not None
    card = _card(rp)
    # 确认卡有 header(非 prerendered)+ ordok/ordno 按钮 + 交易口径免责 note
    assert "header" in card
    assert {"ordok", "ordno"} <= set(_actions(rp))
    notes = [
        e["elements"][0]["content"] for e in card["elements"] if e["tag"] == "note"
    ]
    assert any("模拟交易" in n for n in notes)  # 交易口径免责(四-A 分级)


# ── 🔴 下单二次确认红线(飞书入口)─────────────────────────────────────


@pytest.mark.asyncio
async def test_feishu_forged_ordok_without_confirm_no_execute(
    db_session: AsyncSession,
) -> None:
    """🔴 命门:伪造 card.action.trigger(action=ordok)但 session 不在 order_confirm 态
    → 绝不成交(gate 拦下 · 回主菜单)· 与通道无关,飞书也绕不过。"""
    user = await make_user(db_session)
    acct = await make_virtual_account(db_session, user_id=user.id, market="us")
    await _bind(db_session, user.id, "ou_forge")
    redis, ch = _FakeRedis(), _FakeCH([_bar(100.0)])

    # 全新会话(无 order_confirm)· 直接伪造点 ordok
    resp = await _handle_card_action(db_session, redis, ch, _ev("ou_forge", "ordok"))  # type: ignore[arg-type]

    assert resp is not None  # 有响应(原地刷新成主菜单卡)
    assert not await _positions(db_session, acct.id), "无确认态点 ordok 绝不能成交"
    assert "成交" not in _body(resp)  # 不是成交回执
    assert "menu:order" in _actions(resp)  # 兜底回主菜单(含下单入口按钮)


@pytest.mark.asyncio
async def test_feishu_ordok_at_order_symbol_step_no_execute(
    db_session: AsyncSession,
) -> None:
    """🔴 刚选完市场(step=order_symbol)就跳点 ordok(跳过标的/方向/预览)→ 不成交。"""
    user = await make_user(db_session)
    acct = await make_virtual_account(db_session, user_id=user.id, market="us")
    await _bind(db_session, user.id, "ou_skip")
    redis, ch = _FakeRedis(), _FakeCH([_bar(100.0)])

    await _handle_card_action(db_session, redis, ch, _ev("ou_skip", "menu:order"))  # type: ignore[arg-type]
    await _handle_card_action(db_session, redis, ch, _ev("ou_skip", "omkt:us"))  # type: ignore[arg-type]
    # 跳过输代码/选方向/预览,直接确认
    resp = await _handle_card_action(db_session, redis, ch, _ev("ou_skip", "ordok"))  # type: ignore[arg-type]

    assert resp is not None
    assert not await _positions(db_session, acct.id), "未到确认态点 ordok 绝不能成交"
    assert "成交" not in _body(resp)


@pytest.mark.asyncio
async def test_feishu_order_cross_user_isolation(db_session: AsyncSession) -> None:
    """🔴 隔离:A 的飞书全程确认下单 → 单子只进 A 账户,B 账户绝不被动
    (user_id 由 resolve_user_id(feishu, open_id) 解析 · 会话不存身份)。"""
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    acct_a = await make_virtual_account(db_session, user_id=user_a.id, market="us")
    acct_b = await make_virtual_account(db_session, user_id=user_b.id, market="us")
    await _bind(db_session, user_a.id, "ou_a_only")
    redis, ch = _FakeRedis(), _FakeCH([_bar(100.0)])

    await _handle_card_action(db_session, redis, ch, _ev("ou_a_only", "omkt:us"))  # type: ignore[arg-type]
    await _feishu_text(db_session, redis, ch, "ou_a_only", "NVDA")
    await _handle_card_action(db_session, redis, ch, _ev("ou_a_only", "odir:buy"))  # type: ignore[arg-type]
    await _handle_card_action(db_session, redis, ch, _ev("ou_a_only", "ordok"))  # type: ignore[arg-type]

    assert len(await _positions(db_session, acct_a.id)) == 1  # A 有单
    assert len(await _positions(db_session, acct_b.id)) == 0  # B 一张没有


@pytest.mark.asyncio
async def test_feishu_order_cancel_no_execution(db_session: AsyncSession) -> None:
    """点「✖️取消」(ordno)→ 不成交 · 清会话 · 回取消提示。"""
    user = await make_user(db_session)
    acct = await make_virtual_account(db_session, user_id=user.id, market="us")
    await _bind(db_session, user.id, "ou_cancel")
    redis, ch = _FakeRedis(), _FakeCH([_bar(100.0)])

    await _handle_card_action(db_session, redis, ch, _ev("ou_cancel", "omkt:us"))  # type: ignore[arg-type]
    await _feishu_text(db_session, redis, ch, "ou_cancel", "NVDA")
    await _handle_card_action(db_session, redis, ch, _ev("ou_cancel", "odir:buy"))  # type: ignore[arg-type]
    resp = await _handle_card_action(db_session, redis, ch, _ev("ou_cancel", "ordno"))  # type: ignore[arg-type]

    assert resp is not None
    assert not await _positions(db_session, acct.id), "取消绝不能成交"
    assert "feishu_session:ou_cancel" not in redis._d  # 会话已清
