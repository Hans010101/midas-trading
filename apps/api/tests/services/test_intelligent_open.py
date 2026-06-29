"""智能交易 PR-4 · 开仓编排单测:守卫 OFF skip + 决策做多做空 + 标 intelligent + 记止损止盈共振。

DB(midas_test · CI)+ FakeRedis(两快照)+ ★mock route_open_perp(不碰真引擎 · 建仓+返单)。
验:开关 OFF→skip · 开多→LONG/开空→SHORT · 标 intelligent + 记 stop/tp/signals · 同币去重。
"""

from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.models.virtual import OrderStatus
from app.services.virtual_trading.intelligent import account as iacc
from app.services.virtual_trading.intelligent import guard as iguard
from app.services.virtual_trading.intelligent import open as iopen
from app.services.virtual_trading.perp_fees import q_money


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
