"""托管交易 PR-2 · 开仓编排单测:守卫 skip + 选偏多transition + 去重/≤5 + ★标 managed。

DB(midas_test · CI)+ FakeRedis(开关/快照)+ ★mock route_open_perp(不碰真引擎 · 建仓+返单)。
验:只选偏多∩transition · 同币不重复 · 并行≤5 · route_open_perp 调参 LONG/100U/5x/CROSS · 仓标 managed。
"""

from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.models.virtual import OrderStatus
from app.services.virtual_trading.managed import account as macc
from app.services.virtual_trading.managed import guard as mguard
from app.services.virtual_trading.managed import open as mopen
from app.services.virtual_trading.perp_fees import q_money


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
