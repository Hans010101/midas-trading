"""条件单扫描内核单测(ADR 0041 刀2)· 成交入口全 mock(★红线验证:只调唯一入口)。

process_active_conditionals 用真 PG(db_session)+ 注入 fakes:
命中调入口 / 价未到不动 / 休市跳过 / 无价跳过 / 竞争锁 miss / spot SL 平全仓量 /
无活仓 EXPIRED / perp 拒单 EXPIRED / crypto+LIMIT 防御终态化。
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.virtual_trading.conditional_trigger as trig_mod
from app.models.conditional_order import (
    ConditionalKind,
    ConditionalOrder,
    ConditionalStatus,
)
from app.models.perp import MarginMode, PerpSide
from app.models.virtual import OrderSide, OrderStatus, PositionSide, VirtualPosition
from app.services.virtual_trading.conditional_trigger import (
    process_active_conditionals,
)
from tests.factories import make_user, make_virtual_account


def _cond(
    user_id: Any, *, market: str = "us", symbol: str = "NVDA",
    kind: ConditionalKind = ConditionalKind.LIMIT,
    side: OrderSide = OrderSide.BUY,
    pside: PositionSide = PositionSide.LONG,
    trigger: str = "100", qty: str | None = "5",
    leverage: int | None = None, margin: str | None = None,
    margin_mode: str | None = None,  # 二期刀2:perp 限价开仓字段(spot/SLTP 留 None)
) -> ConditionalOrder:
    return ConditionalOrder(
        user_id=user_id, symbol=symbol, market=market, order_kind=kind,
        side=side, position_side=pside, trigger_price=Decimal(trigger),
        quantity=Decimal(qty) if qty is not None else None,
        leverage=leverage,
        margin=Decimal(margin) if margin is not None else None,
        margin_mode=margin_mode,
        status=ConditionalStatus.ACTIVE,
    )


def _filled(order_id: int = 11) -> SimpleNamespace:
    return SimpleNamespace(id=order_id, status=OrderStatus.FILLED, reject_reason=None)


def _rejected(order_id: int = 12, reason: str = "余额不足(虚拟)") -> SimpleNamespace:
    return SimpleNamespace(id=order_id, status=OrderStatus.REJECTED, reject_reason=reason)


def _injects(
    *, spot_price: Decimal | None = Decimal("90"),
    perp_mark: Decimal | None = Decimal("120000"),
    open_markets: bool = True,
) -> dict[str, Any]:
    async def get_spot_price(symbol: str, market: str) -> Decimal | None:  # noqa: ARG001
        return spot_price

    async def get_perp_mark(symbol: str) -> Decimal | None:  # noqa: ARG001
        return perp_mark

    return {
        "get_spot_price": get_spot_price,
        "get_perp_mark": get_perp_mark,
        "is_market_open": lambda m: open_markets or m == "crypto",  # noqa: ARG005
    }


@pytest.mark.asyncio
async def test_spot_limit_hit_calls_place_market_order(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★红线验证:命中后成交=调 place_market_order(notify=True · 入参逐项对)→ TRIGGERED。"""
    user = await make_user(db_session)
    row = _cond(user.id, trigger="100", qty="5")  # BUY limit 100 · 现价 90 → 触发
    db_session.add(row)
    await db_session.flush()

    captured: dict[str, Any] = {}

    async def spy_place(_db: Any, req: Any, _fetcher: Any) -> SimpleNamespace:
        captured["req"] = req
        return _filled(21)

    monkeypatch.setattr(trig_mod, "place_market_order", spy_place)
    # 恰好三入口:spot 只调 place_market_order,不碰两个 perp 入口
    monkeypatch.setattr(trig_mod, "route_close_perp", _never_factory())
    monkeypatch.setattr(trig_mod, "route_open_perp", _never_factory())
    stats, perp_ids = await process_active_conditionals(db_session, **_injects())

    assert stats["triggered"] == 1
    assert perp_ids == []
    req = captured["req"]
    assert (req.user_id, req.symbol, req.market) == (user.id, "NVDA", "us")
    assert (req.side, req.quantity, req.notify) == (OrderSide.BUY, Decimal("5"), True)
    await db_session.refresh(row)
    assert row.status == ConditionalStatus.TRIGGERED
    assert row.triggered_order_id == 21


@pytest.mark.asyncio
async def test_price_not_reached_stays_active(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user(db_session)
    row = _cond(user.id, trigger="80", qty="5")  # BUY limit 80 · 现价 90 → 不触发
    db_session.add(row)
    await db_session.flush()

    async def never(*_a: Any, **_k: Any) -> SimpleNamespace:
        pytest.fail("价未到不应调成交入口")

    monkeypatch.setattr(trig_mod, "place_market_order", never)
    stats, _ = await process_active_conditionals(db_session, **_injects())
    assert stats["checked"] == 1
    assert stats["triggered"] == 0
    await db_session.refresh(row)
    assert row.status == ConditionalStatus.ACTIVE


@pytest.mark.asyncio
async def test_closed_market_skips_group(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user(db_session)
    db_session.add(_cond(user.id, trigger="100", qty="5"))
    await db_session.flush()

    async def never(*_a: Any, **_k: Any) -> SimpleNamespace:
        pytest.fail("休市不应判价/成交")

    monkeypatch.setattr(trig_mod, "place_market_order", never)
    stats, _ = await process_active_conditionals(
        db_session, **_injects(open_markets=False),
    )
    assert stats["skipped_closed_market"] == 1
    assert stats["checked"] == 0


@pytest.mark.asyncio
async def test_no_price_skips(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user(db_session)
    row = _cond(user.id, trigger="100", qty="5")
    db_session.add(row)
    await db_session.flush()
    monkeypatch.setattr(trig_mod, "place_market_order", _never_factory())
    stats, _ = await process_active_conditionals(
        db_session, **_injects(spot_price=None),
    )
    assert stats["skipped_no_price"] == 1
    await db_session.refresh(row)
    assert row.status == ConditionalStatus.ACTIVE  # 不误触发


def _never_factory() -> Any:
    async def never(*_a: Any, **_k: Any) -> SimpleNamespace:
        pytest.fail("不应调成交入口")
    return never


@pytest.mark.asyncio
async def test_raced_cancel_skips(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """竞争:判价后、锁前被撤 → 锁 miss(status==ACTIVE 条件)→ 跳过不成交(幂等)。"""
    user = await make_user(db_session)
    row = _cond(user.id, trigger="100", qty="5")
    db_session.add(row)
    await db_session.flush()

    async def cancel_then_price(symbol: str, market: str) -> Decimal:  # noqa: ARG001
        row.status = ConditionalStatus.CANCELLED  # 模拟并发撤单发生在判价时刻
        await db_session.flush()
        return Decimal("90")

    monkeypatch.setattr(trig_mod, "place_market_order", _never_factory())
    stats, _ = await process_active_conditionals(
        db_session,
        get_spot_price=cancel_then_price,
        get_perp_mark=_injects()["get_perp_mark"],
        is_market_open=lambda _m: True,
    )
    assert stats["skipped_raced"] == 1


@pytest.mark.asyncio
async def test_spot_sl_close_all_uses_position_quantity(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """spot SL quantity=NULL → 触发时读活仓量平全仓。"""
    user = await make_user(db_session)
    account = await make_virtual_account(db_session, user_id=user.id, market="us")
    db_session.add(
        VirtualPosition(
            account_id=account.id, symbol="NVDA", market="us",
            position_side=PositionSide.LONG, quantity=Decimal("7"),
            avg_entry_price=Decimal("100"), opened_at=datetime.now(UTC),
        ),
    )
    row = _cond(
        user.id, kind=ConditionalKind.STOP_LOSS, side=OrderSide.SELL,
        trigger="95", qty=None,  # 现价 90 ≤ 95 → 触发 · 平全仓
    )
    db_session.add(row)
    await db_session.flush()

    captured: dict[str, Any] = {}

    async def spy_place(_db: Any, req: Any, _f: Any) -> SimpleNamespace:
        captured["req"] = req
        return _filled(31)

    monkeypatch.setattr(trig_mod, "place_market_order", spy_place)
    stats, _ = await process_active_conditionals(db_session, **_injects())
    assert stats["triggered"] == 1
    assert captured["req"].quantity == Decimal("7")  # 活仓量


@pytest.mark.asyncio
async def test_spot_sl_no_position_expires(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="us")
    row = _cond(
        user.id, kind=ConditionalKind.STOP_LOSS, side=OrderSide.SELL,
        trigger="95", qty=None,
    )
    db_session.add(row)
    await db_session.flush()
    monkeypatch.setattr(trig_mod, "place_market_order", _never_factory())
    stats, _ = await process_active_conditionals(db_session, **_injects())
    assert stats["expired"] == 1
    await db_session.refresh(row)
    assert row.status == ConditionalStatus.EXPIRED
    assert row.note is not None
    assert "无可平持仓" in row.note


@pytest.mark.asyncio
async def test_perp_tp_calls_route_close_and_collects_emit(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★红线验证:perp TP 成交=调 route_close_perp(close_all=True)→ TRIGGERED + emit 收集。"""
    user = await make_user(db_session)
    row = _cond(
        user.id, market="crypto", symbol="BTCUSDT",
        kind=ConditionalKind.TAKE_PROFIT, side=OrderSide.SELL,
        pside=PositionSide.LONG, trigger="110000", qty=None,  # mark 120000 ≥ → 触发
    )
    db_session.add(row)
    await db_session.flush()

    captured: dict[str, Any] = {}

    async def spy_route(_db: Any, **kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return _filled(41)

    monkeypatch.setattr(trig_mod, "route_close_perp", spy_route)
    # 恰好三入口:perp SL/TP 只调 route_close_perp(平仓),绝不开仓 / 不碰 spot 入口
    monkeypatch.setattr(trig_mod, "place_market_order", _never_factory())
    monkeypatch.setattr(trig_mod, "route_open_perp", _never_factory())
    stats, perp_ids = await process_active_conditionals(db_session, **_injects())
    assert stats["triggered"] == 1
    assert perp_ids == [41]  # commit 后由壳 emit_perp_order
    assert captured["user_id"] == user.id
    assert captured["symbol"] == "BTCUSDT"
    assert captured["close_all"] is True  # quantity NULL = 平全仓
    await db_session.refresh(row)
    assert row.status == ConditionalStatus.TRIGGERED


@pytest.mark.asyncio
async def test_perp_rejected_expires_with_note(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user(db_session)
    row = _cond(
        user.id, market="crypto", symbol="BTCUSDT",
        kind=ConditionalKind.TAKE_PROFIT, side=OrderSide.SELL,
        pside=PositionSide.LONG, trigger="110000", qty=None,
    )
    db_session.add(row)
    await db_session.flush()

    async def reject_route(_db: Any, **_k: Any) -> SimpleNamespace:
        return _rejected(42, "无可平的合约持仓")

    monkeypatch.setattr(trig_mod, "route_close_perp", reject_route)
    stats, perp_ids = await process_active_conditionals(db_session, **_injects())
    assert stats["expired"] == 1
    assert perp_ids == []
    await db_session.refresh(row)
    assert row.status == ConditionalStatus.EXPIRED
    assert row.triggered_order_id == 42  # rejected 单 id 也回填(审计)
    assert row.note is not None
    assert "无可平的合约持仓" in row.note


# ── perp 限价触发开仓(二期刀2 · ★唯一改触发器红线 · 替换刀1 的 EXPIRED 防御)──────


def _spy_open(captured: dict[str, Any], order_id: int = 51) -> Any:
    """route_open_perp 间谍:捕获入参 + 返回成交单(证只调开仓唯一入口、不自己撮合)。"""
    async def spy(_db: Any, **kwargs: Any) -> SimpleNamespace:
        captured.update(kwargs)
        return _filled(order_id)
    return spy


@pytest.mark.asyncio
async def test_perp_limit_open_long_calls_route_open_perp(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★红线+功能:perp 限价【开多】(BUY+LONG · 低吸 P≤T)命中=调 route_open_perp 开仓入口
    (side=LONG · leverage/margin/mode 由刀1 字段映射)→ TRIGGERED + emit 收集;
    place_market_order / route_close_perp 绝不被调(恰好三入口)。"""
    user = await make_user(db_session)
    # mark 120000 ≤ trigger 125000 → 低吸开多触发
    row = _cond(
        user.id, market="crypto", symbol="BTCUSDT", kind=ConditionalKind.LIMIT,
        side=OrderSide.BUY, pside=PositionSide.LONG, trigger="125000", qty=None,
        leverage=10, margin="500", margin_mode="isolated",
    )
    db_session.add(row)
    await db_session.flush()

    captured: dict[str, Any] = {}
    monkeypatch.setattr(trig_mod, "route_open_perp", _spy_open(captured, 51))
    monkeypatch.setattr(trig_mod, "place_market_order", _never_factory())  # 不走 spot
    monkeypatch.setattr(trig_mod, "route_close_perp", _never_factory())  # 开仓不平仓

    stats, perp_ids = await process_active_conditionals(db_session, **_injects())
    assert stats["triggered"] == 1
    assert perp_ids == [51]  # commit 后由壳 emit_perp_order(开仓/平仓同口径)
    # 字段映射:position_side LONG → 开多 side=PerpSide.LONG · 刀1 落的开仓参数逐项进入口
    assert captured["side"] == PerpSide.LONG
    assert captured["leverage"] == 10
    assert captured["margin"] == Decimal("500")
    assert captured["preferred_mode"] == MarginMode.ISOLATED
    assert captured["symbol"] == "BTCUSDT"
    await db_session.refresh(row)
    assert row.status == ConditionalStatus.TRIGGERED
    assert row.triggered_order_id == 51


@pytest.mark.asyncio
async def test_perp_limit_open_short_calls_route_open_perp(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ 空头限价核心:perp 限价【开空】(SELL+SHORT · 高抛 P≥T)命中=调 route_open_perp
    开仓入口(side=SHORT)→ TRIGGERED。"""
    user = await make_user(db_session)
    # mark 120000 ≥ trigger 115000 → 高抛开空触发
    row = _cond(
        user.id, market="crypto", symbol="BTCUSDT", kind=ConditionalKind.LIMIT,
        side=OrderSide.SELL, pside=PositionSide.SHORT, trigger="115000", qty=None,
        leverage=5, margin="300", margin_mode="cross",
    )
    db_session.add(row)
    await db_session.flush()

    captured: dict[str, Any] = {}
    monkeypatch.setattr(trig_mod, "route_open_perp", _spy_open(captured, 52))
    monkeypatch.setattr(trig_mod, "place_market_order", _never_factory())
    monkeypatch.setattr(trig_mod, "route_close_perp", _never_factory())

    stats, perp_ids = await process_active_conditionals(db_session, **_injects())
    assert stats["triggered"] == 1
    assert perp_ids == [52]
    assert captured["side"] == PerpSide.SHORT  # ★ 开空方向
    assert captured["leverage"] == 5
    assert captured["preferred_mode"] == MarginMode.CROSS
    await db_session.refresh(row)
    assert row.status == ConditionalStatus.TRIGGERED


@pytest.mark.asyncio
async def test_perp_limit_idempotent_open_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ 幂等:同一限价单连扫两轮,只开仓一次(首轮 TRIGGERED 后非 ACTIVE,次轮不再扫到)。"""
    user = await make_user(db_session)
    row = _cond(
        user.id, market="crypto", symbol="BTCUSDT", kind=ConditionalKind.LIMIT,
        side=OrderSide.BUY, pside=PositionSide.LONG, trigger="125000", qty=None,
        leverage=10, margin="500", margin_mode="isolated",
    )
    db_session.add(row)
    await db_session.flush()

    calls: list[int] = []

    async def spy(_db: Any, **_k: Any) -> SimpleNamespace:
        calls.append(1)
        return _filled(53)

    monkeypatch.setattr(trig_mod, "route_open_perp", spy)
    monkeypatch.setattr(trig_mod, "place_market_order", _never_factory())
    monkeypatch.setattr(trig_mod, "route_close_perp", _never_factory())

    await process_active_conditionals(db_session, **_injects())  # 首轮:开仓
    await process_active_conditionals(db_session, **_injects())  # 次轮:已 TRIGGERED 不再扫
    assert len(calls) == 1  # 只开一次
    await db_session.refresh(row)
    assert row.status == ConditionalStatus.TRIGGERED


@pytest.mark.asyncio
async def test_perp_limit_missing_fields_expires(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """防御:perp 限价单缺开仓参数(理论不达 · 端点强制必填)→ EXPIRED + note,不调任何入口。
    保留一条"防御终态化"测试(原因从'暂不支持'改为'缺开仓参数')。"""
    user = await make_user(db_session)
    row = _cond(
        user.id, market="crypto", symbol="BTCUSDT", kind=ConditionalKind.LIMIT,
        side=OrderSide.BUY, pside=PositionSide.LONG, trigger="125000", qty=None,
        leverage=None, margin=None, margin_mode=None,  # 脏数据:缺开仓字段
    )
    db_session.add(row)
    await db_session.flush()
    monkeypatch.setattr(trig_mod, "route_open_perp", _never_factory())
    monkeypatch.setattr(trig_mod, "place_market_order", _never_factory())
    monkeypatch.setattr(trig_mod, "route_close_perp", _never_factory())
    stats, perp_ids = await process_active_conditionals(db_session, **_injects())
    assert stats["expired"] == 1
    assert perp_ids == []
    await db_session.refresh(row)
    assert row.status == ConditionalStatus.EXPIRED
    assert row.note is not None
    assert "缺开仓参数" in row.note
