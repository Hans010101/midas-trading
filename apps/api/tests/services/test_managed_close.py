"""托管交易 PR-3 · 平仓编排单测:_exit_reason 三种退出 + run_managed_close + 记 managed_close_reason。

DB(midas_test · CI)+ FakeRedis(快照 bias)+ ★mock route_close_perp(不碰真引擎 · 平仓+返单)。
验:TP(mark≥entry×1.20)/ 信号(离开偏多)/ 超时(24h)各触发平仓 · 都不满足不平 · reason 写对 · ★不被开关拦。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.models.virtual import OrderStatus
from app.services.virtual_trading.managed import account as macc
from app.services.virtual_trading.managed import close as mclose


class _FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, Any] = {}

    async def get(self, k: str) -> Any:
        return self.kv.get(k)


_NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)


def _pos(entry: str, *, opened_h_ago: float = 1.0) -> VirtualPerpPosition:
    return VirtualPerpPosition(
        symbol="BTCUSDT", side=PerpSide.LONG, entry_price=Decimal(entry),
        opened_at=_NOW - timedelta(hours=opened_h_ago),
    )


# ── _exit_reason 纯函数:TP > 信号 > 超时 ─────────────────────────────
def test_exit_reason_tp() -> None:
    p = _pos("100")
    assert mclose._exit_reason(p, Decimal("120"), "偏多", _NOW) == "tp"  # mark≥entry×1.20
    assert mclose._exit_reason(p, Decimal("119.99"), "偏多", _NOW) is None  # 差一点不止盈


def test_exit_reason_signal() -> None:
    p = _pos("100")
    assert mclose._exit_reason(p, Decimal("110"), "偏空", _NOW) == "signal"  # 离开偏多
    assert mclose._exit_reason(p, Decimal("110"), "中性", _NOW) == "signal"
    assert mclose._exit_reason(p, Decimal("110"), "偏多", _NOW) is None     # 还偏多 → 不平


def test_exit_reason_timeout() -> None:
    old = _pos("100", opened_h_ago=25)  # 持仓 25h > 24h
    assert mclose._exit_reason(old, Decimal("110"), "偏多", _NOW) == "timeout"
    fresh = _pos("100", opened_h_ago=23)
    assert mclose._exit_reason(fresh, Decimal("110"), "偏多", _NOW) is None


def test_exit_reason_priority_tp_over_others() -> None:
    # TP + 信号 + 超时同时满足 → 记 tp(最优先)
    old = _pos("100", opened_h_ago=25)
    assert mclose._exit_reason(old, Decimal("130"), "偏空", _NOW) == "tp"


# ── run_managed_close(DB + mock route_close_perp)──────────────────────
async def _managed_pos(
    db: AsyncSession, account_id: int, symbol: str, entry: str, *, opened_h_ago: float,
) -> VirtualPerpPosition:
    pos = VirtualPerpPosition(
        account_id=account_id, symbol=symbol, side=PerpSide.LONG,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal(entry), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        opened_at=_NOW - timedelta(hours=opened_h_ago), managed=True,
    )
    db.add(pos)
    await db.flush()
    return pos


def _spy_close(captured: list[dict[str, Any]]):  # noqa: ANN202
    """★mock route_close_perp:平掉该 symbol 活仓(set closed_at)+ 返 FILLED 单。"""
    async def fake(
        session: AsyncSession, *, symbol: str, close_all: bool, **_kw: Any,
    ) -> Any:
        captured.append({"symbol": symbol, "close_all": close_all})
        pos = await session.scalar(select(VirtualPerpPosition).where(
            VirtualPerpPosition.symbol == symbol,
            VirtualPerpPosition.closed_at.is_(None),
            VirtualPerpPosition.managed.is_(True),
        ))
        if pos is not None:
            pos.closed_at = _NOW
            pos.realized_pnl = Decimal("100")
        await session.flush()
        return SimpleNamespace(status=OrderStatus.FILLED, reject_reason=None)
    return fake


async def _mark(price: str):  # noqa: ANN202
    async def f(_symbol: str) -> Decimal:
        return Decimal(price)
    return f


@pytest.mark.asyncio
async def test_close_skip_no_account(db_session: AsyncSession) -> None:
    out = await mclose.run_managed_close(db_session, _FakeRedis(), await _mark("100"), now=_NOW)
    assert out == {"status": "skip", "reason": "no_account"}


@pytest.mark.asyncio
async def test_close_empty_when_no_positions(db_session: AsyncSession) -> None:
    await macc.ensure_managed_account(db_session)  # 有账户但无仓
    out = await mclose.run_managed_close(db_session, _FakeRedis(), await _mark("100"), now=_NOW)
    assert out == {"status": "ok", "closed": []}  # ★空转


@pytest.mark.asyncio
async def test_close_tp_triggers(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    acc = await macc.ensure_managed_account(db_session)
    pos = await _managed_pos(db_session, acc.id, "BTCUSDT", "100", opened_h_ago=1)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mclose, "route_close_perp", _spy_close(captured))
    r = _FakeRedis()
    r.kv["boll:snapshot:latest"] = json.dumps({"items": [{"symbol": "BTCUSDT", "bias": "偏多"}]})
    # mark=120 ≥ 100×1.20 → TP
    out = await mclose.run_managed_close(db_session, r, await _mark("120"), now=_NOW)
    assert out["closed"] == [("BTCUSDT", "tp")]
    assert captured[0]["close_all"] is True  # ★全平
    await db_session.refresh(pos)
    assert pos.managed_close_reason == "tp"  # ★记原因
    assert pos.closed_at is not None


@pytest.mark.asyncio
async def test_close_signal_flip_triggers(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    acc = await macc.ensure_managed_account(db_session)
    pos = await _managed_pos(db_session, acc.id, "ETHUSDT", "100", opened_h_ago=1)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mclose, "route_close_perp", _spy_close(captured))
    r = _FakeRedis()
    r.kv["boll:snapshot:latest"] = json.dumps({"items": [{"symbol": "ETHUSDT", "bias": "偏空"}]})
    out = await mclose.run_managed_close(db_session, r, await _mark("105"), now=_NOW)  # mark 不到 TP
    assert out["closed"] == [("ETHUSDT", "signal")]
    await db_session.refresh(pos)
    assert pos.managed_close_reason == "signal"


@pytest.mark.asyncio
async def test_close_timeout_triggers(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    acc = await macc.ensure_managed_account(db_session)
    pos = await _managed_pos(db_session, acc.id, "SOLUSDT", "100", opened_h_ago=25)  # 25h
    monkeypatch.setattr(mclose, "route_close_perp", _spy_close([]))
    r = _FakeRedis()
    r.kv["boll:snapshot:latest"] = json.dumps({"items": [{"symbol": "SOLUSDT", "bias": "偏多"}]})
    out = await mclose.run_managed_close(db_session, r, await _mark("105"), now=_NOW)
    assert out["closed"] == [("SOLUSDT", "timeout")]
    await db_session.refresh(pos)
    assert pos.managed_close_reason == "timeout"


@pytest.mark.asyncio
async def test_close_none_when_holding(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★都不满足(mark<TP · 还偏多 · age<24h)→ 不平
    acc = await macc.ensure_managed_account(db_session)
    pos = await _managed_pos(db_session, acc.id, "BTCUSDT", "100", opened_h_ago=2)
    monkeypatch.setattr(mclose, "route_close_perp", _spy_close([]))
    r = _FakeRedis()
    r.kv["boll:snapshot:latest"] = json.dumps({"items": [{"symbol": "BTCUSDT", "bias": "偏多"}]})
    out = await mclose.run_managed_close(db_session, r, await _mark("110"), now=_NOW)
    assert out["closed"] == []  # 继续持有
    await db_session.refresh(pos)
    assert pos.managed_close_reason is None
    assert pos.closed_at is None
