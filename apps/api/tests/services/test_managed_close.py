"""托管交易 PR-3 · 平仓编排单测:_exit_reason 三种退出 + run_managed_close + 记 managed_close_reason。

DB(midas_test · CI)+ FakeRedis(快照 bias)+ ★mock route_close_perp(不碰真引擎 · 平仓+返单)。
验:TP(mark≥entry×1.20)/ 信号(离开偏多)/ 超时(24h)各触发平仓 · 都不满足不平 · reason 写对 · ★不被开关拦。
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.models.virtual import OrderStatus, VirtualAccount
from app.services.virtual_trading.managed import account as macc
from app.services.virtual_trading.managed import close as mclose
from app.services.virtual_trading.managed import guard as mguard


class _FakeRedis:
    def __init__(self) -> None:
        self.kv: dict[str, Any] = {}

    async def get(self, k: str) -> Any:
        return self.kv.get(k)

    async def set(self, k: str, v: Any) -> None:
        self.kv[k] = v


_NOW = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
_ALL_ON = {"tp": True, "signal": True, "timeout": True}  # ★三平仓开关全开(默认)


def _pos(entry: str, *, opened_h_ago: float = 1.0) -> VirtualPerpPosition:
    return VirtualPerpPosition(
        symbol="BTCUSDT", side=PerpSide.LONG, entry_price=Decimal(entry),
        leverage=5,  # ★_exit_reason 用 pos.leverage 换算止盈阈值(盈利%÷杠杆)
        opened_at=_NOW - timedelta(hours=opened_h_ago),
    )


# ── _exit_reason 纯函数:TP > 信号 > 超时(★各条件先查开关)─────────────
def test_exit_reason_tp() -> None:
    p = _pos("100")  # leverage=5
    # 默认 tp_pct=100 → 价涨 100%÷5 = 20% → 阈值 entry×1.20
    assert mclose._exit_reason(p, Decimal("120"), "偏多", _NOW, _ALL_ON) == "tp"
    assert mclose._exit_reason(p, Decimal("119.99"), "偏多", _NOW, _ALL_ON) is None  # 差一点不止盈
    # ★tp_pct=30 → 价涨 30%÷5 = 6% → 阈值 entry×1.06(盈利30%≠价30%)
    assert mclose._exit_reason(p, Decimal("106"), "偏多", _NOW, _ALL_ON, 30) == "tp"
    assert mclose._exit_reason(p, Decimal("105.99"), "偏多", _NOW, _ALL_ON, 30) is None
    # ★tp_pct=200 → 价涨 40% → 阈值 1.40 · mark=120 不够
    assert mclose._exit_reason(p, Decimal("120"), "偏多", _NOW, _ALL_ON, 200) is None


def test_exit_reason_signal() -> None:
    p = _pos("100")
    assert mclose._exit_reason(p, Decimal("110"), "偏空", _NOW, _ALL_ON) == "signal"  # 离开偏多
    assert mclose._exit_reason(p, Decimal("110"), "中性", _NOW, _ALL_ON) == "signal"
    assert mclose._exit_reason(p, Decimal("110"), "偏多", _NOW, _ALL_ON) is None  # 还偏多 → 不平


def test_exit_reason_timeout() -> None:
    old = _pos("100", opened_h_ago=25)  # 持仓 25h > 24h
    assert mclose._exit_reason(old, Decimal("110"), "偏多", _NOW, _ALL_ON) == "timeout"
    fresh = _pos("100", opened_h_ago=23)
    assert mclose._exit_reason(fresh, Decimal("110"), "偏多", _NOW, _ALL_ON) is None


def test_exit_reason_priority_tp_over_others() -> None:
    # TP + 信号 + 超时同时满足 → 记 tp(最优先)
    old = _pos("100", opened_h_ago=25)
    assert mclose._exit_reason(old, Decimal("130"), "偏空", _NOW, _ALL_ON) == "tp"


def test_exit_reason_respects_switches() -> None:
    # ★开关关 → 该条件跳过(不触发)
    p = _pos("100", opened_h_ago=25)  # 同时满足 TP(mark130) + 信号(偏空) + 超时(25h)
    off_tp = {"tp": False, "signal": True, "timeout": True}
    assert mclose._exit_reason(p, Decimal("130"), "偏空", _NOW, off_tp) == "signal"  # tp 关 → 降到 signal
    off_tp_sig = {"tp": False, "signal": False, "timeout": True}
    assert mclose._exit_reason(p, Decimal("130"), "偏空", _NOW, off_tp_sig) == "timeout"  # 再降到 timeout
    all_off = {"tp": False, "signal": False, "timeout": False}
    assert mclose._exit_reason(p, Decimal("130"), "偏空", _NOW, all_off) is None  # ★全关 → 不平(仅手动)


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
    """★mock route_close_perp:模拟引擎按 user_id→account→symbol 解析活仓(与真引擎一致)。

    ★uid 错配(用别的账户 uid 平本仓)→ 解析不到 → REJECTED(=能抓 close uid 错配回归)。
    捕获 user_id 供断言「每仓用自己 owner uid 平」。
    """
    async def fake(
        session: AsyncSession, *, user_id: Any, symbol: str, close_all: bool, **_kw: Any,
    ) -> Any:
        captured.append({"symbol": symbol, "close_all": close_all, "user_id": user_id})
        pos = await session.scalar(
            select(VirtualPerpPosition)
            .join(VirtualAccount, VirtualPerpPosition.account_id == VirtualAccount.id)
            .where(
                VirtualAccount.user_id == user_id,
                VirtualPerpPosition.symbol == symbol,
                VirtualPerpPosition.closed_at.is_(None),
                VirtualPerpPosition.managed.is_(True),
            ),
        )
        if pos is None:
            return SimpleNamespace(status=OrderStatus.REJECTED, reject_reason="no active position")
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


# ── close_one_managed_position(手动平单 · 人工应急出口)─────────────────
@pytest.mark.asyncio
async def test_manual_close_ok(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★手动平 managed 活仓 → route_close_perp(close_all)+ 记 manual + 返回 realized_pnl
    acc = await macc.ensure_managed_account(db_session)
    pos = await _managed_pos(db_session, acc.id, "BTCUSDT", "100", opened_h_ago=1)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mclose, "route_close_perp", _spy_close(captured))
    out = await mclose.close_one_managed_position(db_session, await _mark("110"), pos.id)
    assert out["status"] == "ok"
    assert out["symbol"] == "BTCUSDT"
    assert out["realized_pnl"] == 100.0          # _spy_close 设的平仓盈亏
    assert captured[0]["close_all"] is True       # ★唯一入口 route_close_perp · close_all
    await db_session.refresh(pos)
    assert pos.managed_close_reason == "manual"   # ★记 manual(区别 tp/signal/timeout)
    assert pos.closed_at is not None


@pytest.mark.asyncio
async def test_manual_close_rejects_non_managed(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★非托管仓(managed=False)→ 拒(防误平用户自己的仓)· 不调 route_close_perp
    acc = await macc.ensure_managed_account(db_session)
    pos = VirtualPerpPosition(
        account_id=acc.id, symbol="XXXUSDT", side=PerpSide.LONG,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal("100"), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        opened_at=_NOW, managed=False,
    )
    db_session.add(pos)
    await db_session.flush()
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mclose, "route_close_perp", _spy_close(captured))
    out = await mclose.close_one_managed_position(db_session, await _mark("110"), pos.id)
    assert out == {"status": "error", "reason": "not_managed"}
    assert captured == []  # ★校验拦截 · 没调撮合


@pytest.mark.asyncio
async def test_manual_close_rejects_already_closed(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    acc = await macc.ensure_managed_account(db_session)
    pos = await _managed_pos(db_session, acc.id, "BTCUSDT", "100", opened_h_ago=1)
    pos.closed_at = _NOW  # 已平
    await db_session.flush()
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mclose, "route_close_perp", _spy_close(captured))
    out = await mclose.close_one_managed_position(db_session, await _mark("110"), pos.id)
    assert out == {"status": "error", "reason": "already_closed"}
    assert captured == []


@pytest.mark.asyncio
async def test_manual_close_rejects_not_found(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    await macc.ensure_managed_account(db_session)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mclose, "route_close_perp", _spy_close(captured))
    out = await mclose.close_one_managed_position(db_session, await _mark("110"), 999999)
    assert out == {"status": "error", "reason": "not_found"}
    assert captured == []


# ── last_bias 维持(补充·信号判平 + 信号列共同依赖)──────────────────────
@pytest.mark.asyncio
async def test_close_updates_last_bias_from_snapshot(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★快照有该币 → last_bias 更新为快照 bias(偏空)→ signal 平
    acc = await macc.ensure_managed_account(db_session)
    pos = await _managed_pos(db_session, acc.id, "BTCUSDT", "100", opened_h_ago=1)
    pos.last_bias = "偏多"
    await db_session.flush()
    monkeypatch.setattr(mclose, "route_close_perp", _spy_close([]))
    r = _FakeRedis()
    r.kv["boll:snapshot:latest"] = json.dumps({"items": [{"symbol": "BTCUSDT", "bias": "偏空"}]})
    out = await mclose.run_managed_close(db_session, r, await _mark("105"), now=_NOW)  # mark 不到 TP
    await db_session.refresh(pos)
    assert pos.last_bias == "偏空"                    # ★快照有 → 更新
    assert out["closed"] == [("BTCUSDT", "signal")]  # 偏空 → 信号平


@pytest.mark.asyncio
async def test_close_keeps_last_bias_when_not_in_snapshot(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★不在快照 → 保持上一次 bias(偏多)→ 不平(维持老信号)
    acc = await macc.ensure_managed_account(db_session)
    pos = await _managed_pos(db_session, acc.id, "BTCUSDT", "100", opened_h_ago=1)
    pos.last_bias = "偏多"
    await db_session.flush()
    monkeypatch.setattr(mclose, "route_close_perp", _spy_close([]))
    r = _FakeRedis()
    r.kv["boll:snapshot:latest"] = json.dumps({"items": [{"symbol": "ZZZUSDT", "bias": "偏空"}]})  # 不含 BTC
    out = await mclose.run_managed_close(db_session, r, await _mark("105"), now=_NOW)
    await db_session.refresh(pos)
    assert pos.last_bias == "偏多"  # ★不在快照 → 保持
    assert out["closed"] == []      # 维持偏多 → 不平


@pytest.mark.asyncio
async def test_close_all_switches_off_no_auto_close(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★三开关全关 → 即使 TP+信号+超时都满足也不自动平(仅手动)
    acc = await macc.ensure_managed_account(db_session)
    pos = await _managed_pos(db_session, acc.id, "BTCUSDT", "100", opened_h_ago=25)  # 超时
    pos.last_bias = "偏空"  # 信号也满足
    await db_session.flush()
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mclose, "route_close_perp", _spy_close(captured))
    r = _FakeRedis()
    await mguard.set_exit_switch(r, "tp", on=False)
    await mguard.set_exit_switch(r, "signal", on=False)
    await mguard.set_exit_switch(r, "timeout", on=False)
    r.kv["boll:snapshot:latest"] = json.dumps({"items": [{"symbol": "BTCUSDT", "bias": "偏空"}]})
    out = await mclose.run_managed_close(db_session, r, await _mark("130"), now=_NOW)  # mark130 TP 满足
    assert out["closed"] == []  # ★全关 → 不平
    assert captured == []        # 没调撮合


# ── 三开关 guard(默认开 + toggle)─────────────────────────────────────
@pytest.mark.asyncio
async def test_exit_switches_default_on_and_toggle() -> None:
    r = _FakeRedis()
    assert await mguard.get_exit_switches(r) == {"tp": True, "signal": True, "timeout": True}  # 默认全开
    await mguard.set_exit_switch(r, "signal", on=False)
    assert await mguard.get_exit_switches(r) == {"tp": True, "signal": False, "timeout": True}
    await mguard.set_exit_switch(r, "signal", on=True)
    assert (await mguard.get_exit_switches(r))["signal"] is True  # 重新开


@pytest.mark.asyncio
async def test_tp_pct_default_and_set() -> None:
    r = _FakeRedis()
    assert await mguard.get_tp_pct(r) == 100  # ★默认 100
    await mguard.set_tp_pct(r, 30)
    assert await mguard.get_tp_pct(r) == 30


@pytest.mark.asyncio
async def test_close_tp_uses_configured_tp_pct(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★tp_pct=30(价6%)· mark=106 触发 tp(默认 100=价20% 时 106 不触发 → 证明 run 真读了 tp_pct)
    acc = await macc.ensure_managed_account(db_session)
    pos = await _managed_pos(db_session, acc.id, "BTCUSDT", "100", opened_h_ago=1)
    pos.last_bias = "偏多"
    await db_session.flush()
    monkeypatch.setattr(mclose, "route_close_perp", _spy_close([]))
    r = _FakeRedis()
    await mguard.set_tp_pct(r, 30)
    r.kv["boll:snapshot:latest"] = json.dumps({"items": [{"symbol": "BTCUSDT", "bias": "偏多"}]})
    out = await mclose.run_managed_close(db_session, r, await _mark("106"), now=_NOW)  # 价 6%
    assert out["closed"] == [("BTCUSDT", "tp")]  # ★tp_pct=30 → 106 触发(默认 100 不会)


# ── ★PR-4a close uid 修复:影子仓 + 混合 + 手动平影子(逐仓按 account 反查 owner uid)──────
@pytest.mark.asyncio
async def test_close_shadow_managed_uses_shadow_uid(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★影子 managed 仓:close 用【影子账户 uid】平。影子 managed 仓免强平,close 是唯一出路——
    #   旧版用全局 uid 平不掉 = 永久挂仓(红线④),本测钉死修复。
    await macc.ensure_managed_account(db_session)  # 全局账户存在(过存在性闸)
    real_uid = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
    shadow_acc = await macc.ensure_managed_account_for_user(db_session, real_uid)
    pos = await _managed_pos(db_session, shadow_acc.id, "BTCUSDT", "100", opened_h_ago=1)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mclose, "route_close_perp", _spy_close(captured))
    r = _FakeRedis()
    r.kv["boll:snapshot:latest"] = json.dumps({"items": [{"symbol": "BTCUSDT", "bias": "偏多"}]})
    out = await mclose.run_managed_close(db_session, r, await _mark("120"), now=_NOW)  # TP
    assert out["closed"] == [("BTCUSDT", "tp")]
    assert captured[0]["user_id"] == shadow_acc.user_id  # ★影子 uid(不是全局)
    await db_session.refresh(pos)
    assert pos.closed_at is not None  # ★影子 managed 仓真平掉(不再永久挂仓)


@pytest.mark.asyncio
async def test_close_mixed_managed_each_own_uid(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★混合:全局 managed 仓 + 影子 managed 仓同轮各用各自 owner uid 平,互不串(红线①③)。
    g_acc = await macc.ensure_managed_account(db_session)
    real_uid = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
    s_acc = await macc.ensure_managed_account_for_user(db_session, real_uid)
    g_pos = await _managed_pos(db_session, g_acc.id, "BTCUSDT", "100", opened_h_ago=1)
    s_pos = await _managed_pos(db_session, s_acc.id, "ETHUSDT", "100", opened_h_ago=1)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mclose, "route_close_perp", _spy_close(captured))
    r = _FakeRedis()
    r.kv["boll:snapshot:latest"] = json.dumps({"items": [
        {"symbol": "BTCUSDT", "bias": "偏多"}, {"symbol": "ETHUSDT", "bias": "偏多"}]})
    out = await mclose.run_managed_close(db_session, r, await _mark("120"), now=_NOW)  # 两仓都 TP
    by_symbol = {c["symbol"]: c["user_id"] for c in captured}
    assert by_symbol == {"BTCUSDT": g_acc.user_id, "ETHUSDT": s_acc.user_id}  # ★各用各 uid·不串
    assert {s for s, _ in out["closed"]} == {"BTCUSDT", "ETHUSDT"}
    await db_session.refresh(g_pos)
    await db_session.refresh(s_pos)
    assert g_pos.closed_at is not None
    assert s_pos.closed_at is not None


@pytest.mark.asyncio
async def test_manual_close_shadow_uses_shadow_uid(db_session: AsyncSession, monkeypatch) -> None:  # noqa: ANN001
    # ★手动平影子 managed 仓:close_one 按 account_id 反查影子 uid(旧版写死全局 uid → 平不掉影子仓)。
    await macc.ensure_managed_account(db_session)
    real_uid = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000003")
    s_acc = await macc.ensure_managed_account_for_user(db_session, real_uid)
    pos = await _managed_pos(db_session, s_acc.id, "BTCUSDT", "100", opened_h_ago=1)
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(mclose, "route_close_perp", _spy_close(captured))
    out = await mclose.close_one_managed_position(db_session, await _mark("110"), pos.id)
    assert out["status"] == "ok"
    assert captured[0]["user_id"] == s_acc.user_id  # ★影子 uid 平影子仓
    await db_session.refresh(pos)
    assert pos.managed_close_reason == "manual"
    assert pos.closed_at is not None
