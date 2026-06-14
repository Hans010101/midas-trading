"""会员订阅支付(Phase 2a 刀1 · Bcon)· pytest。

🔴 红线:支付域收订阅费非交易 · 不 import engine(AST 扫描钉死)· 凭证不入代码。
覆盖:建单(mock Bcon)/ 回调开 pro(extend 'paid' 不封顶)/ ★幂等(只开一次)/
★防伪造四重(status≠2 · 查单金额不足 · external_id 不存在 · addr 不符)。
"""

from __future__ import annotations

import ast
import pathlib
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.payment.order as order_mod
from app.models.subscription import Subscription
from app.services.payment.order import (
    create_payment_order,
    get_order_status,
    process_bcon_callback,
)
from tests.factories import make_user


def _fake_create(addr: str, amount: str):  # noqa: ANN202
    async def _f(external_id: str, amount_usdt: str, *, chain: str = "binance") -> tuple[str, str]:  # noqa: ARG001
        return addr, amount
    return _f


def _fake_tx(sum_value: str):  # noqa: ANN202
    async def _f(txid: str) -> dict[str, Any]:  # noqa: ARG001
        return {"data": {"sum": sum_value, "status": 2}}
    return _f


async def _sub(db: AsyncSession, user_id: Any) -> Subscription | None:
    return await db.scalar(select(Subscription).where(Subscription.user_id == user_id))


# ── ★ create_address 方案 A:origin(必填)+ payment_amount(覆盖换算)三参数都传 ──────


@pytest.mark.asyncio
async def test_create_address_sends_origin_and_payment_amount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """body 传 origin(必填,删了 → Bcon 302)+ payment_amount(名义额);
    ★ 返回【Bcon 的 payment_amount】(唯一尾数收款额 · 用户付这个才被匹配),非我方传入额。"""
    import app.services.payment.bcon_client as bc

    captured: dict[str, Any] = {}

    async def fake_request(method: str, url: str, *, json: dict[str, Any] | None = None) -> Any:
        captured["method"] = method
        captured["url"] = url
        captured["body"] = json
        # Bcon 给唯一尾数收款额(4.9 → 4.93)· 用于固定地址区分订单
        return {"data": {"address": "0xRECV", "payment_amount": "4.93"}}

    monkeypatch.setattr(bc, "_request", fake_request)
    addr, amount = await bc.create_address("ext123", "4.9", chain="binance")

    assert addr == "0xRECV"
    assert amount == "4.93"  # ★ Bcon 返回的精确收款额(非传入的名义 4.9)
    body = captured["body"]
    assert body is not None
    # ★ origin 必填基础参数都在(删了会 302)
    assert body["origin_amount"] == "4.9"
    assert body["origin_currency"] == "USD"
    # ★ payment_amount 覆盖换算 → 实付精确 USDT(无零头)
    assert body["payment_amount"] == "4.9"
    assert body["payment_currency"] == "USDT"
    assert body["external_id"] == "ext123"
    assert body["chain"] == "binance"
    assert captured["method"] == "POST"


# ── 建单 ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_order_pending(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user(db_session)
    # Bcon 返回唯一尾数收款额 4.93(名义价 month=4.9)· ★ 必须用 Bcon 额,非名义额
    monkeypatch.setattr(order_mod, "create_address", _fake_create("0xRECV", "4.93"))
    order, payment_amount = await create_payment_order(db_session, user.id, "month")
    assert order.status == "pending"
    assert order.pay_address == "0xRECV"
    assert payment_amount == "4.93"               # ★ 返 Bcon 额(非名义 4.9)
    assert order.amount_usdt == Decimal("4.93")   # ★ 存 Bcon 额 = 匹配/核验额(非名义 4.9)
    assert order.plan == "pro"
    assert len(order.external_id) >= 16  # 不可猜(secrets.token_urlsafe(24))
    assert await _sub(db_session, user.id) is None  # 未付不开权益


@pytest.mark.asyncio
async def test_create_order_bad_period(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user(db_session)
    monkeypatch.setattr(order_mod, "create_address", _fake_create("0xRECV", "4.9"))
    with pytest.raises(ValueError, match="未知周期"):
        await create_payment_order(db_session, user.id, "week")


# ── 回调开 pro ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_callback_confirmed_grants_pro(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """status=2 + 查单实付 ≥ Bcon 收款额(非名义额)→ pending→paid + 开 pro(extend 'paid')。"""
    user = await make_user(db_session)
    # Bcon 收款额 9.93(名义 quarter=9.9)· 订单存 9.93,核验按 9.93
    monkeypatch.setattr(order_mod, "create_address", _fake_create("0xR", "9.93"))
    order, _ = await create_payment_order(db_session, user.id, "quarter")
    assert order.amount_usdt == Decimal("9.93")  # 核验基准 = Bcon 额
    monkeypatch.setattr(order_mod, "get_transaction", _fake_tx("9.93"))

    label = await process_bcon_callback(
        db_session, status="2", txid="0xTX", external_id=order.external_id, addr="0xR",
    )
    assert label == "paid"
    await db_session.refresh(order)
    assert order.status == "paid"
    assert order.gateway_txid == "0xTX"
    assert order.paid_at is not None
    sub = await _sub(db_session, user.id)
    assert sub is not None
    assert sub.plan == "pro"
    assert sub.status == "active"
    assert sub.source == "paid"


# ── ★ 幂等(同 external_id 回调两次只开一次)─────────────────────────────────────


@pytest.mark.asyncio
async def test_callback_idempotent_grants_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user(db_session)
    monkeypatch.setattr(order_mod, "create_address", _fake_create("0xR", "19.9"))
    order, _ = await create_payment_order(db_session, user.id, "year")
    monkeypatch.setattr(order_mod, "get_transaction", _fake_tx("19.9"))

    first = await process_bcon_callback(
        db_session, status="2", txid="0xTX", external_id=order.external_id, addr="0xR",
    )
    assert first == "paid"
    sub1 = await _sub(db_session, user.id)
    assert sub1 is not None
    exp1 = sub1.expires_at

    # 同回调再来一次 → 已 paid 忽略 · 权益不二次延长
    second = await process_bcon_callback(
        db_session, status="2", txid="0xTX", external_id=order.external_id, addr="0xR",
    )
    assert second.startswith("ignored")
    sub2 = await _sub(db_session, user.id)
    assert sub2 is not None
    assert sub2.expires_at == exp1  # 只延一次(非 ×2)


# ── ★ 防伪造四重 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_callback_status_not_confirmed_ignored(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user(db_session)
    monkeypatch.setattr(order_mod, "create_address", _fake_create("0xR", "4.9"))
    order, _ = await create_payment_order(db_session, user.id, "month")

    async def boom_tx(txid: str) -> dict[str, Any]:  # noqa: ARG001
        msg = "status≠2 不该查单"
        raise AssertionError(msg)

    monkeypatch.setattr(order_mod, "get_transaction", boom_tx)
    label = await process_bcon_callback(
        db_session, status="1", txid="0xTX", external_id=order.external_id, addr="0xR",
    )
    assert label.startswith("ignored")
    await db_session.refresh(order)
    assert order.status == "pending"  # 未开权益
    assert await _sub(db_session, user.id) is None


@pytest.mark.asyncio
async def test_callback_amount_insufficient_rejected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """查单真实金额 < 应付 → 拒绝(防伪造回调 / 少付)。"""
    user = await make_user(db_session)
    monkeypatch.setattr(order_mod, "create_address", _fake_create("0xR", "9.9"))
    order, _ = await create_payment_order(db_session, user.id, "quarter")
    monkeypatch.setattr(order_mod, "get_transaction", _fake_tx("5.0"))  # 实付仅 5 < 9.9

    label = await process_bcon_callback(
        db_session, status="2", txid="0xTX", external_id=order.external_id, addr="0xR",
    )
    assert label.startswith("rejected")
    await db_session.refresh(order)
    assert order.status == "pending"
    assert await _sub(db_session, user.id) is None


@pytest.mark.asyncio
async def test_callback_unknown_external_id_ignored(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom_tx(txid: str) -> dict[str, Any]:  # noqa: ARG001
        msg = "未知 external_id 不该查单"
        raise AssertionError(msg)

    monkeypatch.setattr(order_mod, "get_transaction", boom_tx)
    label = await process_bcon_callback(
        db_session, status="2", txid="0xTX", external_id="__NOPE__", addr="0xR",
    )
    assert label.startswith("ignored")


@pytest.mark.asyncio
async def test_callback_addr_mismatch_rejected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """回调地址与订单收款地址不符 → 拒(防拿别单 txid 套现)。"""
    user = await make_user(db_session)
    monkeypatch.setattr(order_mod, "create_address", _fake_create("0xORDER", "4.9"))
    order, _ = await create_payment_order(db_session, user.id, "month")
    monkeypatch.setattr(order_mod, "get_transaction", _fake_tx("4.9"))

    label = await process_bcon_callback(
        db_session, status="2", txid="0xTX", external_id=order.external_id, addr="0xOTHER",
    )
    assert label.startswith("rejected")
    await db_session.refresh(order)
    assert order.status == "pending"


# ── 订单状态查询(刀2 · 前端轮询 · 限本人)─────────────────────────────────────


@pytest.mark.asyncio
async def test_get_order_status_owner_only(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """本人查得到订单状态 · 他人查不到(None · 端点转 404,不泄露他人订单)。"""
    owner = await make_user(db_session)
    other = await make_user(db_session)
    monkeypatch.setattr(order_mod, "create_address", _fake_create("0xR", "4.9"))
    order, _ = await create_payment_order(db_session, owner.id, "month")

    mine = await get_order_status(db_session, owner.id, order.external_id)
    assert mine is not None
    assert mine.status == "pending"
    assert mine.period == "month"
    # 他人查同一 external_id → None(不泄露)
    assert await get_order_status(db_session, other.id, order.external_id) is None
    # 不存在的订单 → None
    assert await get_order_status(db_session, owner.id, "__NOPE__") is None


# ── ★ 红线:支付域 import 树不含 engine/virtual_trading(AST 扫描)──────────────


def test_payment_domain_no_engine_import() -> None:
    root = pathlib.Path(__file__).resolve().parents[1].parent  # apps/api
    files = [
        *(root / "app" / "services" / "payment").glob("*.py"),
        root / "app" / "api" / "v1" / "payment.py",
        root / "app" / "models" / "payment_order.py",
        root / "app" / "schemas" / "payment.py",
    ]
    bad: list[tuple[str, str]] = []
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [node.module or ""]
            for m in mods:
                if "virtual_trading" in m or "engine" in m.split("."):
                    bad.append((f.name, m))
    assert not bad, f"🔴 支付域不得 import 交易/engine(收订阅费非交易):{bad}"
