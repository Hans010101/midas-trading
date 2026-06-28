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
