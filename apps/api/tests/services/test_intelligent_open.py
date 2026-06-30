"""智能交易 PR-4 · 开仓编排单测:守卫 OFF skip + 决策做多做空 + 标 intelligent + 记止损止盈共振。

DB(midas_test · CI)+ FakeRedis(两快照)+ ★mock route_open_perp(不碰真引擎 · 建仓+返单)。
验:开关 OFF→skip · 开多→LONG/开空→SHORT · 标 intelligent + 记 stop/tp/signals · 同币去重。
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
from app.services.virtual_trading.intelligent import account as iacc
from app.services.virtual_trading.intelligent import guard as iguard
from app.services.virtual_trading.intelligent import open as iopen
from app.services.virtual_trading.perp_fees import q_money
from tests.factories import make_user


class _FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, Any] = {}

    async def get(self, k: str) -> Any:
        return self.kv.get(k)

    async def set(self, k: str, v: Any) -> None:
        self.kv[k] = v


async def _mark(_symbol: str) -> Decimal:
    return Decimal("100")


def _bull(sym: str) -> dict[str, Any]:
    """全偏多信号(score=8.0 → 开多)。"""
    return {
        "symbol": sym, "ma_dir": 1, "macd_dir": 1, "rsi_dir": 1, "kdj_dir": 1,
        "extreme_dir": 1, "atr": 10.0,
    }


def _bear(sym: str) -> dict[str, Any]:
    return {
        "symbol": sym, "ma_dir": -1, "macd_dir": -1, "rsi_dir": -1, "kdj_dir": -1,
        "extreme_dir": -1, "atr": 10.0,
    }


def _seed_snapshots(r: _FakeRedis, boll: list[dict], signals: list[dict]) -> None:
    r.kv["boll:snapshot:latest"] = json.dumps({"items": boll})
    r.kv["intelligent:signals:latest"] = json.dumps({"items": signals})


def _spy_open(captured: list[dict[str, Any]], account_id: int):  # noqa: ANN202
    """★mock route_open_perp:建一条 intelligent=False 仓(仿引擎)+ 返 FILLED 单 · 捕获 side。"""
    async def fake(
        session: AsyncSession, *, symbol: str, side: Any, leverage: int,
        margin: Any, **_kw: Any,
    ) -> Any:
        captured.append({"symbol": symbol, "side": side, "leverage": leverage, "margin": margin})
        q, e = Decimal("1"), Decimal("100")
        pos = VirtualPerpPosition(
            account_id=account_id, symbol=symbol, side=side,
            margin_mode=MarginMode.CROSS, leverage=leverage, quantity=q, entry_price=e,
            initial_margin=q_money(q * e / Decimal(leverage)),
            maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
            intelligent=False,  # ★引擎默认非智能 · 编排 post-open 标 True
        )
        session.add(pos)
        await session.flush()
        return SimpleNamespace(status=OrderStatus.FILLED, position_id=pos.id, reject_reason=None)
    return fake


@pytest.mark.asyncio
async def test_skip_disabled(db_session: AsyncSession) -> None:
    r = _FakeRedis()  # 开关默认 OFF
    out = await iopen.run_intelligent_open(db_session, r, _mark)
    assert out == {"status": "skip", "reason": "disabled"}


@pytest.mark.asyncio
async def test_open_long_and_short_marks_intelligent(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    r = _FakeRedis()
    await iguard.set_enabled(r, enabled=True)
    acc = await iacc.ensure_intelligent_account(db_session)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(iopen, "route_open_perp", _spy_open(captured, acc.id))
    # BTC 全偏多 → 开多(LONG)· ETH 全偏空 → 开空(SHORT)
    _seed_snapshots(
        r,
        boll=[{"symbol": "BTCUSDT", "bias": "偏多", "close": 100.0},
              {"symbol": "ETHUSDT", "bias": "偏空", "close": 100.0}],
        signals=[_bull("BTCUSDT"), _bear("ETHUSDT")],
    )
    out = await iopen.run_intelligent_open(db_session, r, _mark)
    assert out["status"] == "ok"
    assert len(out["opened"]) == 2
    sides = {c["symbol"]: c["side"] for c in captured}
    assert sides["BTCUSDT"] == PerpSide.LONG   # ★开多 → LONG
    assert sides["ETHUSDT"] == PerpSide.SHORT  # ★开空 → SHORT
    assert all(c["margin"] == Decimal("100") and c["leverage"] == 5 for c in captured)
    # ★标 intelligent + 记止损止盈 + 共振明细
    positions = list(await db_session.scalars(
        select(VirtualPerpPosition).where(VirtualPerpPosition.account_id == acc.id),
    ))
    assert len(positions) == 2
    assert all(p.intelligent for p in positions)
    btc = next(p for p in positions if p.symbol == "BTCUSDT")
    # 开多 entry=100 ATR=10 · 止损=100−2×10=80 · 止盈=100+4×10=140
    assert btc.intelligent_stop_price == Decimal("80")
    assert btc.intelligent_tp_price == Decimal("140")
    assert btc.intelligent_signals["score"] == 8.0  # type: ignore[index]
    eth = next(p for p in positions if p.symbol == "ETHUSDT")
    assert eth.intelligent_stop_price == Decimal("120")  # 开空止损 = 100+2×10
    assert eth.intelligent_tp_price == Decimal("60")


@pytest.mark.asyncio
async def test_hold_not_opened(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # 混合信号(score 在 ±3.0 内)→ 不开
    r = _FakeRedis()
    await iguard.set_enabled(r, enabled=True)
    acc = await iacc.ensure_intelligent_account(db_session)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(iopen, "route_open_perp", _spy_open(captured, acc.id))
    _seed_snapshots(
        r,
        boll=[{"symbol": "BTCUSDT", "bias": "偏多", "close": 100.0}],
        signals=[{"symbol": "BTCUSDT", "macd_dir": -1, "atr": 10.0}],  # 2.0−1.5=0.5 → hold
    )
    out = await iopen.run_intelligent_open(db_session, r, _mark)
    assert out["opened"] == []
    assert captured == []  # 没调 route_open_perp


@pytest.mark.asyncio
async def test_dedup_skips_held_symbol(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    r = _FakeRedis()
    await iguard.set_enabled(r, enabled=True)
    acc = await iacc.ensure_intelligent_account(db_session)
    # 已持 BTC
    db_session.add(VirtualPerpPosition(
        account_id=acc.id, symbol="BTCUSDT", side=PerpSide.LONG,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal("100"), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        intelligent=True,
    ))
    await db_session.flush()
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(iopen, "route_open_perp", _spy_open(captured, acc.id))
    _seed_snapshots(
        r,
        boll=[{"symbol": "BTCUSDT", "bias": "偏多", "close": 100.0},
              {"symbol": "ETHUSDT", "bias": "偏多", "close": 100.0}],
        signals=[_bull("BTCUSDT"), _bull("ETHUSDT")],
    )
    out = await iopen.run_intelligent_open(db_session, r, _mark)
    assert [o["symbol"] for o in out["opened"]] == ["ETHUSDT"]  # ★BTC 已持跳过,只开 ETH


# ── 开仓参数可调(margin/leverage 读 Redis · max_positions 总数约束 · ★ATR 不受杠杆)──
@pytest.mark.asyncio
async def test_guard_open_params_defaults_and_set() -> None:
    # ★三参数 get/set(纯 · FakeRedis 真跑)· 默认 100/5/50
    r = _FakeRedis()
    assert await iguard.get_open_margin(r) == Decimal("100")
    assert await iguard.get_open_leverage(r) == 5
    assert await iguard.get_max_positions(r) == 50
    await iguard.set_open_margin(r, Decimal("300"))
    await iguard.set_open_leverage(r, 12)
    await iguard.set_max_positions(r, 20)
    assert await iguard.get_open_margin(r) == Decimal("300")
    assert await iguard.get_open_leverage(r) == 12
    assert await iguard.get_max_positions(r) == 20


@pytest.mark.asyncio
async def test_margin_leverage_from_redis(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★margin/leverage 读 Redis(不再 hardcode 100/5)· 做多做空都用
    r = _FakeRedis()
    await iguard.set_enabled(r, enabled=True)
    await iguard.set_open_margin(r, Decimal("250"))
    await iguard.set_open_leverage(r, 8)
    acc = await iacc.ensure_intelligent_account(db_session)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(iopen, "route_open_perp", _spy_open(captured, acc.id))
    _seed_snapshots(
        r,
        boll=[{"symbol": "BTCUSDT", "bias": "偏多", "close": 100.0}],
        signals=[_bull("BTCUSDT")],
    )
    await iopen.run_intelligent_open(db_session, r, _mark)
    assert captured[0]["margin"] == Decimal("250")  # ★读 Redis
    assert captured[0]["leverage"] == 8


@pytest.mark.asyncio
async def test_max_positions_caps_to_exact_limit(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★已持 2 仓 + max_positions=3 → 本轮只开 1(开到刚好 3·不超)· 智能原本并发不限
    r = _FakeRedis()
    await iguard.set_enabled(r, enabled=True)
    await iguard.set_max_positions(r, 3)
    acc = await iacc.ensure_intelligent_account(db_session)
    for i in range(2):  # 已持 2 仓
        db_session.add(VirtualPerpPosition(
            account_id=acc.id, symbol=f"HELD{i}USDT", side=PerpSide.LONG,
            margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
            entry_price=Decimal("100"), initial_margin=Decimal("20"),
            maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
            intelligent=True,
        ))
    await db_session.flush()
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(iopen, "route_open_perp", _spy_open(captured, acc.id))
    # 候选 4 个新币(全偏多)→ 但 max=3·已持 2 → 只能再开 1
    _seed_snapshots(
        r,
        boll=[{"symbol": f"N{i}USDT", "bias": "偏多", "close": 100.0} for i in range(4)],
        signals=[_bull(f"N{i}USDT") for i in range(4)],
    )
    out = await iopen.run_intelligent_open(db_session, r, _mark)
    assert len(out["opened"]) == 1  # ★开到刚好 3(2+1),不超


@pytest.mark.asyncio
async def test_max_positions_reached_no_open(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★已持 ≥ max_positions → 本轮不开新仓
    r = _FakeRedis()
    await iguard.set_enabled(r, enabled=True)
    await iguard.set_max_positions(r, 2)
    acc = await iacc.ensure_intelligent_account(db_session)
    for i in range(2):  # 已持 2 = max
        db_session.add(VirtualPerpPosition(
            account_id=acc.id, symbol=f"HELD{i}USDT", side=PerpSide.LONG,
            margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
            entry_price=Decimal("100"), initial_margin=Decimal("20"),
            maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
            intelligent=True,
        ))
    await db_session.flush()
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(iopen, "route_open_perp", _spy_open(captured, acc.id))
    _seed_snapshots(
        r,
        boll=[{"symbol": f"N{i}USDT", "bias": "偏多", "close": 100.0} for i in range(4)],
        signals=[_bull(f"N{i}USDT") for i in range(4)],
    )
    out = await iopen.run_intelligent_open(db_session, r, _mark)
    assert out["opened"] == []   # ★到上限不开
    assert captured == []


# ── ★PR-4b 铂金 per-user 开仓(影子账户 + per-user 开关 + 遍历 + 并发兜底)──────────
def _spy_open_by_user(captured: list[dict[str, Any]]):  # noqa: ANN202
    """★mock route_open_perp:按 user_id 解析账户建仓(模拟引擎 user_id→account 路由)+ 捕获 user_id。"""
    async def fake(
        session: AsyncSession, *, user_id: Any, symbol: str, side: Any, leverage: int,
        margin: Any, **_kw: Any,
    ) -> Any:
        captured.append({"symbol": symbol, "side": side, "user_id": user_id, "margin": margin})
        acc = await session.scalar(select(VirtualAccount).where(
            VirtualAccount.user_id == user_id, VirtualAccount.market == "crypto",
        ))
        assert acc is not None  # 影子账户应已 ensure
        q, e = Decimal("1"), Decimal("100")
        pos = VirtualPerpPosition(
            account_id=acc.id, symbol=symbol, side=side,
            margin_mode=MarginMode.CROSS, leverage=leverage, quantity=q, entry_price=e,
            initial_margin=q_money(q * e / Decimal(leverage)),
            maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
            intelligent=False,
        )
        session.add(pos)
        await session.flush()
        return SimpleNamespace(status=OrderStatus.FILLED, position_id=pos.id, reject_reason=None)
    return fake


@pytest.mark.asyncio
async def test_per_user_switch_gates_open(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★per-user 开关:即使全局 ON,该铂金用户开关 OFF → skip(不开);ON → 在影子账户用影子 uid 开。
    r = _FakeRedis()
    await iguard.set_enabled(r, enabled=True)  # 全局 ON(不影响 per-user 判定)
    real_uid = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
    shadow = await iacc.ensure_intelligent_account_for_user(db_session, real_uid)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(iopen, "route_open_perp", _spy_open_by_user(captured))
    _seed_snapshots(r, boll=[{"symbol": "BTCUSDT", "bias": "偏多", "close": 100.0}],
                    signals=[_bull("BTCUSDT")])
    # per-user 开关默认 OFF → skip(全局 ON 不带开 per-user)
    out = await iopen.run_intelligent_open(
        db_session, r, _mark, account=shadow, enabled_user_id=real_uid)
    assert out == {"status": "skip", "reason": "disabled"}
    assert captured == []
    # per-user 开关 ON → 开(在影子账户·route 用影子 uid)
    await iguard.set_enabled(r, enabled=True, user_id=real_uid)
    out = await iopen.run_intelligent_open(
        db_session, r, _mark, account=shadow, enabled_user_id=real_uid)
    assert out["status"] == "ok"
    assert captured[0]["user_id"] == shadow.user_id  # ★用影子 uid 开(不是全局)


@pytest.mark.asyncio
async def test_open_platinum_loops_only_platinum_each_shadow(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★铂金 loop:遍历 is_platinum 用户 → 各自影子账户开仓;非铂金用户不被遍历。
    r = _FakeRedis()
    plat = await make_user(db_session)
    plat.is_platinum = True
    await make_user(db_session)  # 非铂金(不应被遍历)
    await db_session.commit()
    await iguard.set_enabled(r, enabled=True, user_id=plat.id)  # 该铂金用户 per-user 开关 ON
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(iopen, "route_open_perp", _spy_open_by_user(captured))
    _seed_snapshots(r, boll=[{"symbol": "BTCUSDT", "bias": "偏多", "close": 100.0}],
                    signals=[_bull("BTCUSDT")])
    results = await iopen.run_intelligent_open_platinum(db_session, r, _mark)
    assert len(results) == 1  # ★只遍历了铂金用户(非铂金不在内)
    assert results[0]["uid"] == str(plat.id)
    assert results[0]["status"] == "ok"
    # ★开在该铂金用户的【影子账户】(影子 uid ≠ 真人 plat.id)· 真人自己名下不被开仓
    shadow_uid = await iacc.get_intelligent_user_id_for_user(db_session, plat.id)
    assert captured[0]["user_id"] == shadow_uid
    assert shadow_uid != plat.id
    real_cnt = await db_session.scalar(select(VirtualPerpPosition).where(
        VirtualPerpPosition.account_id.in_(
            select(VirtualAccount.id).where(VirtualAccount.user_id == plat.id)),
    ))
    assert real_cnt is None  # 真人 user_id 名下无影子仓(影子挂独立影子 user)


@pytest.mark.asyncio
async def test_ensure_shadow_retries_on_integrity_error(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★并发兜底:首建撞 User.email unique(IntegrityError)→ rollback 重查 → 第二次成功(不 500)。
    real_uid = uuid.UUID("cccccccc-0000-0000-0000-000000000009")
    real_ensure = iacc.ensure_intelligent_account_for_user
    calls = {"n": 0}

    async def flaky(session: AsyncSession, user_id: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise IntegrityError("dup email", None, Exception("unique"))  # 模拟并发首建撞 unique
        return await real_ensure(session, user_id)

    monkeypatch.setattr(iacc, "ensure_intelligent_account_for_user", flaky)
    acc = await iopen._ensure_shadow_intelligent_account(db_session, real_uid)
    assert calls["n"] == 2  # ★第一次撞 → 第二次重查成功
    assert acc is not None
    assert acc.user_id != real_uid  # 影子账户(独立影子 user)
