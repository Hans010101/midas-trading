"""智能交易 PR-5 · 平仓编排单测:三退出(★做多做空对称)+ 不被开关拦 + 记 intelligent_close_reason。

- 纯函数 _exit_reason(本地无 DB 真跑):开多/开空 各 止损/止盈/信号反转 + 优先级 + 边界。
- 集成 run_intelligent_close(CI · DB + mock route_close_perp):不被开关拦 / 空转 / 平+记原因。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.models.virtual import OrderStatus
from app.services.virtual_trading.intelligent import account as iacc
from app.services.virtual_trading.intelligent import close
from app.services.virtual_trading.intelligent import strategy as istrategy


def _pos(side: PerpSide, stop: Decimal | None, tp: Decimal | None) -> VirtualPerpPosition:
    """构造纯函数测用 pos(只读 side/stop/tp · 不入库)。"""
    return VirtualPerpPosition(
        side=side, intelligent_stop_price=stop, intelligent_tp_price=tp,
    )


def _dec(score: float) -> istrategy.StrategyDecision:
    return istrategy.StrategyDecision(
        symbol="X", action="x", score=score, entry_price=100.0,
        stop_loss=None, take_profit=None, contributions={},
    )


# ── 纯函数 _exit_reason · 做多 ──────────────────────────────────────
def test_long_stop_loss() -> None:
    pos = _pos(PerpSide.LONG, Decimal("80"), Decimal("140"))
    assert close._exit_reason(pos, Decimal("80"), None) == "stop_loss"   # 标记价≤stop
    assert close._exit_reason(pos, Decimal("79"), None) == "stop_loss"
    assert close._exit_reason(pos, Decimal("100"), None) is None         # 中间不触


def test_long_take_profit() -> None:
    pos = _pos(PerpSide.LONG, Decimal("80"), Decimal("140"))
    assert close._exit_reason(pos, Decimal("140"), None) == "take_profit"  # 标记价≥tp
    assert close._exit_reason(pos, Decimal("141"), None) == "take_profit"


def test_long_signal_reversal() -> None:
    pos = _pos(PerpSide.LONG, Decimal("80"), Decimal("140"))
    assert close._exit_reason(pos, Decimal("100"), _dec(-0.5)) == "signal_reversal"  # 跌破0
    assert close._exit_reason(pos, Decimal("100"), _dec(0.0)) is None   # =0 不反转
    assert close._exit_reason(pos, Decimal("100"), _dec(5.0)) is None   # 还偏多


# ── 纯函数 _exit_reason · ★做空对称 ────────────────────────────────
def test_short_stop_loss() -> None:
    pos = _pos(PerpSide.SHORT, Decimal("120"), Decimal("60"))
    assert close._exit_reason(pos, Decimal("120"), None) == "stop_loss"  # ★开空 标记价≥stop
    assert close._exit_reason(pos, Decimal("121"), None) == "stop_loss"
    assert close._exit_reason(pos, Decimal("100"), None) is None


def test_short_take_profit() -> None:
    pos = _pos(PerpSide.SHORT, Decimal("120"), Decimal("60"))
    assert close._exit_reason(pos, Decimal("60"), None) == "take_profit"  # ★开空 标记价≤tp
    assert close._exit_reason(pos, Decimal("59"), None) == "take_profit"


def test_short_signal_reversal() -> None:
    pos = _pos(PerpSide.SHORT, Decimal("120"), Decimal("60"))
    assert close._exit_reason(pos, Decimal("100"), _dec(0.5)) == "signal_reversal"  # ★升破0
    assert close._exit_reason(pos, Decimal("100"), _dec(0.0)) is None
    assert close._exit_reason(pos, Decimal("100"), _dec(-5.0)) is None  # 还偏空


# ── 纯函数 _exit_reason · 优先级 + 边界 ────────────────────────────
def test_priority_stop_over_signal() -> None:
    # 同时触止损 + 信号反转 → 止损优先(先判)
    pos = _pos(PerpSide.LONG, Decimal("80"), Decimal("140"))
    assert close._exit_reason(pos, Decimal("79"), _dec(-5.0)) == "stop_loss"


def test_priority_tp_over_signal() -> None:
    # 同时触止盈 + 信号反转 → 止盈优先
    pos = _pos(PerpSide.SHORT, Decimal("120"), Decimal("60"))
    assert close._exit_reason(pos, Decimal("59"), _dec(5.0)) == "take_profit"


def test_mark_none_and_no_exit() -> None:
    pos = _pos(PerpSide.LONG, Decimal("80"), Decimal("140"))
    assert close._exit_reason(pos, None, _dec(-5.0)) is None    # 无价不判
    assert close._exit_reason(pos, Decimal("100"), _dec(5.0)) is None  # 都不满足


def test_missing_stop_tp_only_signal() -> None:
    # 止损止盈价缺(None)→ 只信号反转可触发
    pos = _pos(PerpSide.LONG, None, None)
    assert close._exit_reason(pos, Decimal("100"), _dec(-1.0)) == "signal_reversal"
    assert close._exit_reason(pos, Decimal("100"), None) is None


# ── 集成 run_intelligent_close(CI · DB + mock route_close_perp)───────
class _FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, Any] = {}

    async def get(self, k: str) -> Any:
        return self.kv.get(k)


def _make_pos(account_id: int, symbol: str, side: PerpSide,
              stop: Decimal, tp: Decimal) -> VirtualPerpPosition:
    """集成测:完整字段 intelligent 活仓(CI flush)。"""
    return VirtualPerpPosition(
        account_id=account_id, symbol=symbol, side=side,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal("100"), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        intelligent=True, intelligent_stop_price=stop, intelligent_tp_price=tp,
    )


def _spy_close(captured: list[str]):  # noqa: ANN202
    """★mock route_close_perp:标该 symbol 的 intelligent 活仓 closed_at(仿引擎平仓)+ 返 FILLED。"""
    async def fake(session: AsyncSession, *, symbol: str, **_kw: Any) -> Any:
        captured.append(symbol)
        pos = (await session.scalars(select(VirtualPerpPosition).where(
            VirtualPerpPosition.symbol == symbol,
            VirtualPerpPosition.intelligent.is_(True),
            VirtualPerpPosition.closed_at.is_(None),
        ))).first()
        if pos is not None:
            pos.closed_at = datetime.now(tz=UTC)
        return SimpleNamespace(status=OrderStatus.FILLED, reject_reason=None)
    return fake


async def _mark(value: str):  # noqa: ANN202
    async def fetch(_symbol: str) -> Decimal:
        return Decimal(value)
    return fetch


@pytest.mark.asyncio
async def test_close_not_blocked_by_switch(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★不被开关拦:开关 OFF(无快照·close 不读开关)· 开多触止损 → 仍平 + 记 stop_loss
    acc = await iacc.ensure_intelligent_account(db_session)
    pos = _make_pos(acc.id, "BTCUSDT", PerpSide.LONG, Decimal("80"), Decimal("140"))
    db_session.add(pos)
    await db_session.flush()
    captured: list[str] = []
    monkeypatch.setattr(close, "route_close_perp", _spy_close(captured))
    out = await close.run_intelligent_close(db_session, _FakeRedis(), await _mark("79"))
    assert captured == ["BTCUSDT"]
    assert out["closed"] == [("BTCUSDT", "stop_loss")]
    await db_session.refresh(pos)
    assert pos.intelligent_close_reason == "stop_loss"
    assert pos.closed_at is not None


@pytest.mark.asyncio
async def test_close_empty_when_no_positions(db_session: AsyncSession) -> None:
    await iacc.ensure_intelligent_account(db_session)
    out = await close.run_intelligent_close(db_session, _FakeRedis(), await _mark("100"))
    assert out == {"status": "ok", "closed": []}  # 空转零副作用


@pytest.mark.asyncio
async def test_close_short_take_profit(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★做空止盈:开空 tp=60 · mark=59 → 平 + 记 take_profit
    acc = await iacc.ensure_intelligent_account(db_session)
    pos = _make_pos(acc.id, "ETHUSDT", PerpSide.SHORT, Decimal("120"), Decimal("60"))
    db_session.add(pos)
    await db_session.flush()
    captured: list[str] = []
    monkeypatch.setattr(close, "route_close_perp", _spy_close(captured))
    out = await close.run_intelligent_close(db_session, _FakeRedis(), await _mark("59"))
    assert out["closed"] == [("ETHUSDT", "take_profit")]
    await db_session.refresh(pos)
    assert pos.intelligent_close_reason == "take_profit"


@pytest.mark.asyncio
async def test_close_long_signal_reversal(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★信号反转:开多 + 当前快照全偏空(build_decisions score=-8<0)→ 平 + 记 signal_reversal
    acc = await iacc.ensure_intelligent_account(db_session)
    # stop=1/tp=999999 极端不触发 · 只信号反转能触发
    pos = _make_pos(acc.id, "BTCUSDT", PerpSide.LONG, Decimal("1"), Decimal("999999"))
    db_session.add(pos)
    await db_session.flush()
    captured: list[str] = []
    monkeypatch.setattr(close, "route_close_perp", _spy_close(captured))
    r = _FakeRedis()
    r.kv["boll:snapshot:latest"] = json.dumps(
        {"items": [{"symbol": "BTCUSDT", "bias": "偏空", "close": 100.0}]})
    r.kv["intelligent:signals:latest"] = json.dumps({"items": [{
        "symbol": "BTCUSDT", "ma_dir": -1, "macd_dir": -1, "rsi_dir": -1,
        "kdj_dir": -1, "extreme_dir": -1, "atr": 10.0,
    }]})
    out = await close.run_intelligent_close(db_session, r, await _mark("100"))
    assert out["closed"] == [("BTCUSDT", "signal_reversal")]
    await db_session.refresh(pos)
    assert pos.intelligent_close_reason == "signal_reversal"
