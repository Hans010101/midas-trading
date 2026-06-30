"""托管交易 PR-2 · 开仓编排单测:守卫 skip + 选偏多transition + 去重/≤5 + ★标 managed。

DB(midas_test · CI)+ FakeRedis(开关/快照)+ ★mock route_open_perp(不碰真引擎 · 建仓+返单)。
验:只选偏多∩transition · 同币不重复 · 并行≤5 · route_open_perp 调参 LONG/100U/5x/CROSS · 仓标 managed。
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.models.virtual import OrderStatus, VirtualAccount
from app.services.virtual_trading.managed import account as macc
from app.services.virtual_trading.managed import guard as mguard
from app.services.virtual_trading.managed import open as mopen
from app.services.virtual_trading.perp_fees import q_money
from tests.factories import make_user


class _FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, Any] = {}

    async def get(self, k: str) -> Any:
        return self.kv.get(k)

    async def set(self, k: str, v: Any) -> None:
        self.kv[k] = v


def _item(symbol: str, bias: str, change: float, *, transition: bool) -> dict[str, Any]:
    return {"symbol": symbol, "bias": bias, "change_pct_24h": change, "transition": transition}


def _seed_snapshot(r: _FakeRedis, items: list[dict[str, Any]]) -> None:
    r.kv["boll:snapshot:latest"] = json.dumps({"items": items})


async def _mark_price(_symbol: str) -> Decimal:
    return Decimal("100")


def _spy_open(captured: list[dict[str, Any]], account_id: int):  # noqa: ANN202
    """★mock route_open_perp:建一条 managed=False 仓(仿引擎)+ 返 FILLED 单 · 捕获入参。"""
    async def fake(
        session: AsyncSession, *, symbol: str, side: Any, leverage: int,
        margin: Any, preferred_mode: Any, **_kw: Any,  # _kw 吸收 user_id/quantity/get_mark_price
    ) -> Any:
        captured.append({
            "symbol": symbol, "side": side, "leverage": leverage,
            "margin": margin, "mode": preferred_mode,
        })
        q, e = Decimal("1"), Decimal("100")
        pos = VirtualPerpPosition(
            account_id=account_id, symbol=symbol, side=side,
            margin_mode=preferred_mode, leverage=leverage, quantity=q, entry_price=e,
            initial_margin=q_money(q * e / Decimal(leverage)),
            maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
            managed=False,  # ★引擎默认非托管 · 编排应 post-open 标 True
        )
        session.add(pos)
        await session.flush()
        return SimpleNamespace(
            status=OrderStatus.FILLED, position_id=pos.id, reject_reason=None,
        )
    return fake


# ── 守卫 skip ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_skip_disabled(db_session: AsyncSession) -> None:
    r = _FakeRedis()  # 开关默认 OFF
    out = await mopen.run_managed_open(db_session, r, _mark_price)
    assert out == {"status": "skip", "reason": "disabled"}


@pytest.mark.asyncio
async def test_per_round_cap_not_total(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★每轮最多开 5 个新单 · ★总活仓数不限:已持 6 仓仍继续开,本轮再开满 5(不再是「持满5就停」)
    r = _FakeRedis()
    await mguard.set_enabled(r, enabled=True)
    acc = await macc.ensure_managed_account(db_session)
    for i in range(6):  # 已持 6 仓(> 5)· 旧逻辑会 skip max_positions,新逻辑不该
        db_session.add(VirtualPerpPosition(
            account_id=acc.id, symbol=f"HELD{i}USDT", side=PerpSide.LONG,
            margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
            entry_price=Decimal("100"), initial_margin=Decimal("20"),
            maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
            managed=True,
        ))
    await db_session.flush()
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mopen, "route_open_perp", _spy_open(captured, acc.id))
    # 快照 8 个【新】偏多∩transition 候选 → 本轮应开满 5(不被「总活仓≥5」挡)
    _seed_snapshot(r, [_item(f"N{i}USDT", "偏多", 9.0 - i, transition=True) for i in range(8)])
    out = await mopen.run_managed_open(db_session, r, _mark_price)
    assert out["status"] == "ok"
    assert len(out["opened"]) == mguard.MAX_PER_ROUND  # ★本轮恰开 5 个新单
    # ★总活仓累积(6 旧 + 5 新 = 11)· 没有总上限
    from sqlalchemy import func, select  # noqa: PLC0415
    total = await db_session.scalar(
        select(func.count()).select_from(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == acc.id,
            VirtualPerpPosition.closed_at.is_(None),
        ),
    )
    assert total == 11


# ── happy:选偏多∩transition + 调 route_open_perp + 标 managed ──────────
@pytest.mark.asyncio
async def test_opens_bullish_transition_and_marks_managed(
    db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    r = _FakeRedis()
    await mguard.set_enabled(r, enabled=True)
    acc = await macc.ensure_managed_account(db_session)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mopen, "route_open_perp", _spy_open(captured, acc.id))
    _seed_snapshot(r, [
        _item("AAAUSDT", "偏空", 9.0, transition=True),   # 偏空 → 不开
        _item("BBBUSDT", "偏多", -2.0, transition=False),  # 非 transition → 不开
        _item("CCCUSDT", "偏多", 8.0, transition=True),    # ★偏多∩transition → 开
        _item("DDDUSDT", "偏多", 3.0, transition=True),    # ★偏多∩transition → 开
    ])
    out = await mopen.run_managed_open(db_session, r, _mark_price)
    assert out["status"] == "ok"
    assert set(out["opened"]) == {"CCCUSDT", "DDDUSDT"}  # 只偏多∩transition
    # ★route_open_perp 调参:LONG / 100U / 5x / CROSS
    assert all(c["side"] == PerpSide.LONG for c in captured)
    assert all(c["margin"] == Decimal("100") for c in captured)
    assert all(c["leverage"] == 5 for c in captured)
    assert all(c["mode"] == MarginMode.CROSS for c in captured)
    # ★开的仓都标了 managed=True(post-open · 零碰引擎)
    from sqlalchemy import select  # noqa: PLC0415
    positions = list(await db_session.scalars(
        select(VirtualPerpPosition).where(VirtualPerpPosition.account_id == acc.id),
    ))
    assert len(positions) == 2
    assert all(p.managed for p in positions)


@pytest.mark.asyncio
async def test_dedup_skips_held_symbol(
    db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    r = _FakeRedis()
    await mguard.set_enabled(r, enabled=True)
    acc = await macc.ensure_managed_account(db_session)
    # 已持 CCC
    db_session.add(VirtualPerpPosition(
        account_id=acc.id, symbol="CCCUSDT", side=PerpSide.LONG,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal("100"), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        managed=True,
    ))
    await db_session.flush()
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mopen, "route_open_perp", _spy_open(captured, acc.id))
    _seed_snapshot(r, [
        _item("CCCUSDT", "偏多", 9.0, transition=True),  # ★已持 → 跳
        _item("DDDUSDT", "偏多", 3.0, transition=True),  # 开
    ])
    out = await mopen.run_managed_open(db_session, r, _mark_price)
    assert out["opened"] == ["DDDUSDT"]  # ★CCC 已持被跳,只开 DDD


# ── 开仓参数可调(margin/leverage 读 Redis · max_positions 总数约束)──────
@pytest.mark.asyncio
async def test_guard_open_params_defaults_and_set() -> None:
    # ★三参数 get/set(纯 · FakeRedis 真跑)· 默认 100/5/50 · set 后读新值
    r = _FakeRedis()
    assert await mguard.get_open_margin(r) == Decimal("100")
    assert await mguard.get_open_leverage(r) == 5
    assert await mguard.get_max_positions(r) == 50
    await mguard.set_open_margin(r, Decimal("250"))
    await mguard.set_open_leverage(r, 10)
    await mguard.set_max_positions(r, 30)
    assert await mguard.get_open_margin(r) == Decimal("250")
    assert await mguard.get_open_leverage(r) == 10
    assert await mguard.get_max_positions(r) == 30


@pytest.mark.asyncio
async def test_margin_leverage_from_redis(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★margin/leverage 读 Redis(不再 hardcode 100/5)
    r = _FakeRedis()
    await mguard.set_enabled(r, enabled=True)
    await mguard.set_open_margin(r, Decimal("200"))
    await mguard.set_open_leverage(r, 8)
    acc = await macc.ensure_managed_account(db_session)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mopen, "route_open_perp", _spy_open(captured, acc.id))
    _seed_snapshot(r, [_item("AAAUSDT", "偏多", 9.0, transition=True)])
    await mopen.run_managed_open(db_session, r, _mark_price)
    assert captured[0]["margin"] == Decimal("200")  # ★读 Redis
    assert captured[0]["leverage"] == 8


@pytest.mark.asyncio
async def test_max_positions_caps_to_exact_limit(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★已持 3 仓 + max_positions=5 → 本轮只开 2(开到刚好 5 · 不超)· 且仍受每轮≤5
    r = _FakeRedis()
    await mguard.set_enabled(r, enabled=True)
    await mguard.set_max_positions(r, 5)
    acc = await macc.ensure_managed_account(db_session)
    for i in range(3):  # 已持 3 仓
        db_session.add(VirtualPerpPosition(
            account_id=acc.id, symbol=f"HELD{i}USDT", side=PerpSide.LONG,
            margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
            entry_price=Decimal("100"), initial_margin=Decimal("20"),
            maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
            managed=True,
        ))
    await db_session.flush()
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mopen, "route_open_perp", _spy_open(captured, acc.id))
    # 候选 6 个新币(足够多)→ 但 max=5 · 已持 3 → 只能再开 2
    _seed_snapshot(r, [_item(f"N{i}USDT", "偏多", 9.0 - i, transition=True) for i in range(6)])
    out = await mopen.run_managed_open(db_session, r, _mark_price)
    assert len(out["opened"]) == 2  # ★开到刚好 5(3+2),不超


@pytest.mark.asyncio
async def test_max_positions_reached_no_open(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★已持 ≥ max_positions → 本轮不开新仓
    r = _FakeRedis()
    await mguard.set_enabled(r, enabled=True)
    await mguard.set_max_positions(r, 3)
    acc = await macc.ensure_managed_account(db_session)
    for i in range(3):  # 已持 3 = max
        db_session.add(VirtualPerpPosition(
            account_id=acc.id, symbol=f"HELD{i}USDT", side=PerpSide.LONG,
            margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
            entry_price=Decimal("100"), initial_margin=Decimal("20"),
            maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
            managed=True,
        ))
    await db_session.flush()
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mopen, "route_open_perp", _spy_open(captured, acc.id))
    _seed_snapshot(r, [_item(f"N{i}USDT", "偏多", 9.0 - i, transition=True) for i in range(6)])
    out = await mopen.run_managed_open(db_session, r, _mark_price)
    assert out["opened"] == []   # ★到上限不开
    assert captured == []        # 没调 route_open_perp


@pytest.mark.asyncio
async def test_both_constraints_per_round_and_max(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★每轮≤5 AND 总数≤max 并存:max=100(够大)+ 已持 0 + 候选 8 → 每轮 5 约束生效(开 5)
    r = _FakeRedis()
    await mguard.set_enabled(r, enabled=True)
    await mguard.set_max_positions(r, 100)
    acc = await macc.ensure_managed_account(db_session)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mopen, "route_open_perp", _spy_open(captured, acc.id))
    _seed_snapshot(r, [_item(f"N{i}USDT", "偏多", 9.0 - i, transition=True) for i in range(8)])
    out = await mopen.run_managed_open(db_session, r, _mark_price)
    assert len(out["opened"]) == mguard.MAX_PER_ROUND  # ★每轮≤5 生效(虽 max=100 够大)


# ── ★PR-4b 铂金 per-user 开仓(影子账户 + per-user 开关 + 遍历 + 并发兜底)──────────
def _spy_open_by_user(captured: list[dict[str, Any]]):  # noqa: ANN202
    """★mock route_open_perp:按 user_id 解析账户建仓(模拟引擎 user_id→account 路由)+ 捕获 user_id。"""
    async def fake(
        session: AsyncSession, *, user_id: Any, symbol: str, side: Any, leverage: int,
        preferred_mode: Any, **_kw: Any,
    ) -> Any:
        captured.append({"symbol": symbol, "side": side, "user_id": user_id})
        acc = await session.scalar(select(VirtualAccount).where(
            VirtualAccount.user_id == user_id, VirtualAccount.market == "crypto",
        ))
        assert acc is not None  # 影子账户应已 ensure
        q, e = Decimal("1"), Decimal("100")
        pos = VirtualPerpPosition(
            account_id=acc.id, symbol=symbol, side=side,
            margin_mode=preferred_mode, leverage=leverage, quantity=q, entry_price=e,
            initial_margin=q_money(q * e / Decimal(leverage)),
            maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
            managed=False,
        )
        session.add(pos)
        await session.flush()
        return SimpleNamespace(status=OrderStatus.FILLED, position_id=pos.id, reject_reason=None)
    return fake


@pytest.mark.asyncio
async def test_per_user_switch_gates_open(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★per-user 开关:全局 ON 但该铂金用户开关 OFF → skip;ON → 在影子账户用影子 uid 开。
    r = _FakeRedis()
    await mguard.set_enabled(r, enabled=True)  # 全局 ON(不影响 per-user 判定)
    real_uid = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
    shadow = await macc.ensure_managed_account_for_user(db_session, real_uid)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mopen, "route_open_perp", _spy_open_by_user(captured))
    _seed_snapshot(r, [_item("BTCUSDT", "偏多", 5.0, transition=True)])
    out = await mopen.run_managed_open(
        db_session, r, _mark_price, account=shadow, enabled_user_id=real_uid)
    assert out == {"status": "skip", "reason": "disabled"}  # per-user 默认 OFF
    assert captured == []
    await mguard.set_enabled(r, enabled=True, user_id=real_uid)
    out = await mopen.run_managed_open(
        db_session, r, _mark_price, account=shadow, enabled_user_id=real_uid)
    assert out["status"] == "ok"
    assert captured[0]["user_id"] == shadow.user_id  # ★用影子 uid 开


@pytest.mark.asyncio
async def test_open_platinum_loops_only_platinum(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★铂金 loop:遍历 is_platinum 用户 → 各自影子账户开仓;非铂金不被遍历。
    r = _FakeRedis()
    plat = await make_user(db_session)
    plat.is_platinum = True
    await make_user(db_session)  # 非铂金
    await db_session.commit()
    await mguard.set_enabled(r, enabled=True, user_id=plat.id)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mopen, "route_open_perp", _spy_open_by_user(captured))
    _seed_snapshot(r, [_item("BTCUSDT", "偏多", 5.0, transition=True)])
    results = await mopen.run_managed_open_platinum(db_session, r, _mark_price)
    assert len(results) == 1  # ★只遍历铂金用户
    assert results[0]["uid"] == str(plat.id)
    assert results[0]["status"] == "ok"
    shadow_uid = await macc.get_managed_user_id_for_user(db_session, plat.id)
    assert captured[0]["user_id"] == shadow_uid  # ★开在影子账户
    assert shadow_uid != plat.id


@pytest.mark.asyncio
async def test_ensure_shadow_retries_on_integrity_error(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★并发兜底:首建撞 User.email unique(IntegrityError)→ rollback 重查 → 第二次成功(不 500)。
    real_uid = uuid.UUID("dddddddd-0000-0000-0000-000000000009")
    real_ensure = macc.ensure_managed_account_for_user
    calls = {"n": 0}

    async def flaky(session: AsyncSession, user_id: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise IntegrityError("dup email", None, Exception("unique"))
        return await real_ensure(session, user_id)

    monkeypatch.setattr(macc, "ensure_managed_account_for_user", flaky)
    acc = await mopen._ensure_shadow_managed_account(db_session, real_uid)
    assert calls["n"] == 2  # ★第一次撞 → 第二次重查成功
    assert acc is not None
    assert acc.user_id != real_uid
