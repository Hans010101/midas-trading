"""飞书告警规则 / 安静时段卡 pytest · ADR 0032 阶段四-C。

★ 本阶段【无新增渲染代码】:告警/安静时段卡复用 build_alert_rules / build_quiet_hours
(阶段三已有)+ 同一 render_for_feishu(阶段三)+ card.action.trigger 原地刷新(四-B)。
本测试证明这条共享链路对"告警类卡"也走通,且按钮回调走 handle_inbound(逻辑一份)。

覆盖:menu:rules 卡渲染 · rules:toggle 启停翻转 · rules:apply 一键推荐 · 跨用户隔离 ·
menu:quiet 卡渲染 · quiet:s+ 步进生效。全部经 _handle_card_action(四-B 原地刷新入口)。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.feishu import _handle_card_action
from app.models.alert_rule import AlertRule
from app.models.notification import NotificationConfig
from tests.factories import make_user


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
    def __init__(self) -> None:
        self._client = object()

    async def select_kline(self, **_kw: Any) -> list[Any]:
        return []


def _ev(open_id: str, action: str) -> dict[str, Any]:
    return {"operator": {"open_id": open_id}, "action": {"value": {"action": action}}}


def _actions(resp: dict[str, Any]) -> list[str | None]:
    """从 card-update 响应抽所有按钮的 action(url 按钮无 action → None)。"""
    card = resp["card"]["data"]
    return [
        a.get("value", {}).get("action")
        for e in card["elements"] if e["tag"] == "action"
        for a in e["actions"]
    ]


async def _bind(db: AsyncSession, user_id: Any, open_id: str, **cfg: Any) -> None:
    db.add(NotificationConfig(user_id=user_id, feishu_open_id=open_id, **cfg))
    await db.commit()


# ── 告警规则卡 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_feishu_alert_rules_card(db_session: AsyncSession) -> None:
    """menu:rules → 告警规则卡(原地刷新)· 含 toggle / apply / 返回按钮。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, "ou_a")
    db_session.add(AlertRule(
        user_id=user.id, market="crypto", symbol="BTC/USDT",
        indicator="price", operator="gt", threshold=Decimal("70000"), enabled=True,
    ))
    await db_session.commit()
    resp = await _handle_card_action(
        db_session, _FakeRedis(), _FakeCH(), _ev("ou_a", "menu:rules"),  # type: ignore[arg-type]
    )
    assert resp is not None
    acts = _actions(resp)
    assert any(a and a.startswith("rules:toggle:") for a in acts)
    assert "rules:apply" in acts
    assert "menu:main" in acts


@pytest.mark.asyncio
async def test_feishu_rule_toggle_flips(db_session: AsyncSession) -> None:
    """rules:toggle:{id} → 启停翻转(走 handle_inbound 业务)+ 原地返回新卡。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, "ou_b")
    rule = AlertRule(
        user_id=user.id, market="us", symbol="NVDA",
        indicator="pct", operator="lte", threshold=Decimal("-5"), enabled=True,
    )
    db_session.add(rule)
    await db_session.commit()
    before = rule.enabled
    resp = await _handle_card_action(
        db_session, _FakeRedis(), _FakeCH(), _ev("ou_b", f"rules:toggle:{rule.id}"),  # type: ignore[arg-type]
    )
    assert resp is not None  # 原地刷新
    await db_session.refresh(rule)
    assert rule.enabled is not before  # 翻转生效


@pytest.mark.asyncio
async def test_feishu_rule_apply_recommended(db_session: AsyncSession) -> None:
    """rules:apply → 一键应用推荐规则(创建规则)+ 原地返回新卡。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, "ou_d")
    resp = await _handle_card_action(
        db_session, _FakeRedis(), _FakeCH(), _ev("ou_d", "rules:apply"),  # type: ignore[arg-type]
    )
    assert resp is not None
    rules = list(await db_session.scalars(
        select(AlertRule).where(AlertRule.user_id == user.id),
    ))
    assert len(rules) > 0  # 推荐规则已创建


@pytest.mark.asyncio
async def test_feishu_rule_toggle_cross_user_isolation(db_session: AsyncSession) -> None:
    """🔴 隔离:A 的飞书点 B 的规则 id → B 规则不变(ownership-scoped · 与通道无关)。"""
    user_a = await make_user(db_session)
    user_b = await make_user(db_session)
    await _bind(db_session, user_a.id, "ou_attacker")
    b_rule = AlertRule(
        user_id=user_b.id, market="crypto", symbol=None,
        indicator="fg", operator="lt", threshold=Decimal("20"), enabled=True,
    )
    db_session.add(b_rule)
    await db_session.commit()
    before = b_rule.enabled
    await _handle_card_action(
        db_session, _FakeRedis(), _FakeCH(),  # type: ignore[arg-type]
        _ev("ou_attacker", f"rules:toggle:{b_rule.id}"),
    )
    await db_session.refresh(b_rule)
    assert b_rule.enabled == before  # B 的规则没被 A 改


# ── 安静时段卡 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_feishu_quiet_card(db_session: AsyncSession) -> None:
    """menu:quiet → 安静时段卡 · 含启停 / 起止步进按钮。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, "ou_c")
    resp = await _handle_card_action(
        db_session, _FakeRedis(), _FakeCH(), _ev("ou_c", "menu:quiet"),  # type: ignore[arg-type]
    )
    assert resp is not None
    acts = _actions(resp)
    assert "quiet:toggle" in acts
    assert "quiet:s+" in acts
    assert "quiet:e-" in acts


@pytest.mark.asyncio
async def test_feishu_quiet_step_persists(db_session: AsyncSession) -> None:
    """quiet:s+ → 起始小时 +1 持久化(走 handle_inbound → quiet_mod)+ 原地返回新卡。"""
    user = await make_user(db_session)
    await _bind(db_session, user.id, "ou_e", quiet_hours_start=10)
    resp = await _handle_card_action(
        db_session, _FakeRedis(), _FakeCH(), _ev("ou_e", "quiet:s+"),  # type: ignore[arg-type]
    )
    assert resp is not None
    cfg = await db_session.scalar(
        select(NotificationConfig).where(NotificationConfig.user_id == user.id),
    )
    assert cfg is not None
    assert cfg.quiet_hours_start == 11  # 10 + 1
