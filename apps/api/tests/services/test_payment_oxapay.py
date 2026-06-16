"""会员订阅支付(Phase 2a · OxaPay 托管收款)· pytest。

🔴 红线:支付域收订阅费非交易 · 不 import engine(AST 扫描钉死)· 凭证不入代码。
覆盖:client 建单/查单(mock _request)· 建单 pending(存 track_id/payment_url/名义价)·
回调开 pro(extend 'paid' 不封顶)· ★幂等(只开一次)·
★防伪造多重(① HMAC raw-body 验签 = 命门 · ② 状态非 paid · ③ track_id 不符 · ④ 查单金额/状态不足)·
★大小写不敏感(Paid/PAID vs paid)· ★原始字节验签(re-serialize 必失败)。
"""

from __future__ import annotations

import ast
import hashlib
import hmac
import json
import pathlib
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.payment.order as order_mod
from app.core.config import settings
from app.models.subscription import Subscription
from app.services.payment.order import (
    create_payment_order,
    get_order_status,
    process_oxapay_callback,
)
from tests.factories import make_user

TEST_KEY = "test_merchant_key_abc123"


# ── helpers ───────────────────────────────────────────────────────────────────


def _fake_create_invoice(track_id: str, url: str):  # noqa: ANN202
    async def _f(
        order_id: str, amount_usdt: str, *, callback_url: str, sandbox: bool = False,  # noqa: ARG001
    ) -> tuple[str, str]:
        return track_id, url
    return _f


def _fake_get_payment(status: str = "paid", amount: str = "9.9"):  # noqa: ANN202
    async def _f(track_id: str) -> dict[str, Any]:
        return {"track_id": track_id, "status": status, "amount": amount, "currency": "USDT"}
    return _f


async def _boom_get_payment(track_id: str) -> dict[str, Any]:  # noqa: ARG001
    msg = "该分支不应触发查单"
    raise AssertionError(msg)


def _signed_callback(
    order_id: str, track_id: str, *, status: str = "Paid", key: str = TEST_KEY,
) -> tuple[bytes, str]:
    """构造 OxaPay 回调原始字节 + 对【该字节】的 HMAC-SHA512 签名(模拟真实回调)。"""
    payload = {
        "track_id": track_id, "status": status, "type": "invoice",
        "amount": "9.9", "currency": "USD", "order_id": order_id,
    }
    raw = json.dumps(payload).encode()
    sig = hmac.new(key.encode(), raw, hashlib.sha512).hexdigest()
    return raw, sig


async def _sub(db: AsyncSession, user_id: Any) -> Subscription | None:
    return await db.scalar(select(Subscription).where(Subscription.user_id == user_id))


@pytest.fixture(autouse=True)
def _set_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """所有用例固定商户密钥(验签密钥),不读真实 env。"""
    monkeypatch.setattr(settings, "oxapay_merchant_api_key", TEST_KEY)


# ── client:建单 / 查单(mock _request)─────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_invoice_sends_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """建单 body:amount(float)+ currency=USD + order_id + callback_url + sandbox + lifetime;
    返回 (track_id, payment_url)· 凭证只在 header(不在此断言,_request 已封装)。"""
    import app.services.payment.oxapay_client as oc

    captured: dict[str, Any] = {}

    async def fake_request(method: str, url: str, *, json: dict[str, Any] | None = None) -> Any:
        captured["method"] = method
        captured["url"] = url
        captured["body"] = json
        return {"data": {"track_id": "trk_1", "payment_url": "https://oxapay.com/pay/trk_1"}}

    monkeypatch.setattr(oc, "_request", fake_request)
    track_id, url = await oc.create_invoice(
        "ext123", "4.9", callback_url="https://api.midastrade.asia/api/v1/payment/oxapay/callback",
        sandbox=True,
    )

    assert track_id == "trk_1"
    assert url == "https://oxapay.com/pay/trk_1"
    body = captured["body"]
    assert body is not None
    assert body["amount"] == 4.9  # noqa: PLR2004 — float 计价
    assert body["currency"] == "USD"
    assert body["order_id"] == "ext123"
    assert body["callback_url"].endswith("/api/v1/payment/oxapay/callback")
    assert body["sandbox"] is True
    assert body["lifetime"] == settings.oxapay_lifetime_minutes
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/v1/payment/invoice")


@pytest.mark.asyncio
async def test_create_invoice_missing_fields_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """响应缺 track_id/payment_url → OxaPayError(端点转 502)。"""
    import app.services.payment.oxapay_client as oc

    async def fake_request(method: str, url: str, *, json: dict[str, Any] | None = None) -> Any:  # noqa: ARG001
        return {"data": {"track_id": "trk_1"}}  # 缺 payment_url

    monkeypatch.setattr(oc, "_request", fake_request)
    with pytest.raises(oc.OxaPayError):
        await oc.create_invoice("ext", "4.9", callback_url="https://x/cb")


@pytest.mark.asyncio
async def test_get_payment_returns_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """查单返回内层 data(真实 status/amount 核验用)。"""
    import app.services.payment.oxapay_client as oc

    async def fake_request(method: str, url: str, *, json: dict[str, Any] | None = None) -> Any:  # noqa: ARG001
        return {"data": {"track_id": "trk_1", "status": "paid", "amount": "9.9"}}

    monkeypatch.setattr(oc, "_request", fake_request)
    info = await oc.get_payment("trk_1")
    assert info["status"] == "paid"
    assert info["amount"] == "9.9"


# ── 建单 ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_order_pending(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """建 pending:pay_address=payment_url · gateway_txid=track_id · amount_usdt=名义价(无尾数)。"""
    user = await make_user(db_session)
    monkeypatch.setattr(
        order_mod, "create_invoice", _fake_create_invoice("trk_x", "https://oxapay.com/pay/trk_x"),
    )
    order, payment_url = await create_payment_order(db_session, user.id, "month")
    assert order.status == "pending"
    assert payment_url == "https://oxapay.com/pay/trk_x"
    assert order.pay_address == "https://oxapay.com/pay/trk_x"  # 复用字段存 URL
    assert order.gateway_txid == "trk_x"                        # 建单即存 track_id
    assert order.amount_usdt == Decimal("4.9")                  # 名义价(OxaPay 无唯一尾数)
    assert order.chain == "multi"
    assert order.plan == "pro"
    assert len(order.external_id) >= 16  # 不可猜(secrets.token_urlsafe(24))
    assert await _sub(db_session, user.id) is None  # 未付不开权益


@pytest.mark.asyncio
async def test_create_order_bad_period(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = await make_user(db_session)
    monkeypatch.setattr(order_mod, "create_invoice", _fake_create_invoice("trk", "https://x"))
    with pytest.raises(ValueError, match="未知周期"):
        await create_payment_order(db_session, user.id, "week")


# ── 回调开 pro(全链路通过)──────────────────────────────────────────────────────


async def _make_pending(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch, period: str, track_id: str,
) -> Any:
    user = await make_user(db)
    monkeypatch.setattr(
        order_mod, "create_invoice", _fake_create_invoice(track_id, f"https://oxapay.com/{track_id}"),
    )
    order, _ = await create_payment_order(db, user.id, period)
    return order


@pytest.mark.asyncio
async def test_callback_confirmed_grants_pro(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验签过 + 状态 Paid + track_id 绑定 + 查单 paid&金额≥ → pending→paid + 开 pro(extend 'paid')。"""
    order = await _make_pending(db_session, monkeypatch, "quarter", "trk_ok")
    assert order.amount_usdt == Decimal("9.9")
    monkeypatch.setattr(order_mod, "get_payment", _fake_get_payment("paid", "9.9"))

    raw, sig = _signed_callback(order.external_id, "trk_ok", status="Paid")
    label = await process_oxapay_callback(db_session, raw_body=raw, hmac_header=sig)
    assert label == "paid"

    await db_session.refresh(order)
    assert order.status == "paid"
    assert order.gateway_txid == "trk_ok"  # 建单存的 track_id 不被覆写
    assert order.paid_at is not None
    sub = await _sub(db_session, order.user_id)
    assert sub is not None
    assert sub.plan == "pro"
    assert sub.status == "active"
    assert sub.source == "paid"


@pytest.mark.asyncio
async def test_callback_case_insensitive(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ 状态大小写不敏感:回调 'PAID' + 查单 'Paid' → 仍开通(两侧均 .lower() 比较)。"""
    order = await _make_pending(db_session, monkeypatch, "month", "trk_case")
    monkeypatch.setattr(order_mod, "get_payment", _fake_get_payment("Paid", "4.9"))

    raw, sig = _signed_callback(order.external_id, "trk_case", status="PAID")
    label = await process_oxapay_callback(db_session, raw_body=raw, hmac_header=sig)
    assert label == "paid"


# ── ★ 幂等(同回调两次只开一次)──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_callback_idempotent_grants_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    order = await _make_pending(db_session, monkeypatch, "year", "trk_idem")
    monkeypatch.setattr(order_mod, "get_payment", _fake_get_payment("paid", "19.9"))
    raw, sig = _signed_callback(order.external_id, "trk_idem", status="Paid")

    first = await process_oxapay_callback(db_session, raw_body=raw, hmac_header=sig)
    assert first == "paid"
    sub1 = await _sub(db_session, order.user_id)
    assert sub1 is not None
    exp1 = sub1.expires_at

    second = await process_oxapay_callback(db_session, raw_body=raw, hmac_header=sig)
    assert second.startswith("ignored")
    sub2 = await _sub(db_session, order.user_id)
    assert sub2 is not None
    assert sub2.expires_at == exp1  # 只延一次(非 ×2)


# ── ★ 防伪造多重 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_callback_bad_signature_rejected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """① 命门:HMAC 头不符 → 拒(端点转 400)· 不查单、不解析业务、不开权益。"""
    order = await _make_pending(db_session, monkeypatch, "month", "trk_sig")
    monkeypatch.setattr(order_mod, "get_payment", _boom_get_payment)

    raw, _ = _signed_callback(order.external_id, "trk_sig", status="Paid")
    label = await process_oxapay_callback(db_session, raw_body=raw, hmac_header="deadbeef")
    assert label == "rejected: bad signature"
    await db_session.refresh(order)
    assert order.status == "pending"
    assert await _sub(db_session, order.user_id) is None


@pytest.mark.asyncio
async def test_callback_missing_signature_rejected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺 HMAC 头(None)→ 拒。"""
    order = await _make_pending(db_session, monkeypatch, "month", "trk_nosig")
    monkeypatch.setattr(order_mod, "get_payment", _boom_get_payment)
    raw, _ = _signed_callback(order.external_id, "trk_nosig")
    label = await process_oxapay_callback(db_session, raw_body=raw, hmac_header=None)
    assert label == "rejected: bad signature"


@pytest.mark.asyncio
async def test_callback_raw_body_bytes_must_match(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ 验签基于【原始字节】:同一 JSON 不同字节编码(re-serialize)→ 签名不符 → 拒。

    证明绝不可 json 解析再 dumps 后验签(那样字节会变,真实回调会被误拒/伪造可绕过)。
    """
    order = await _make_pending(db_session, monkeypatch, "month", "trk_raw")
    monkeypatch.setattr(order_mod, "get_payment", _boom_get_payment)
    payload = {
        "track_id": "trk_raw", "status": "Paid", "type": "invoice",
        "amount": "4.9", "currency": "USD", "order_id": order.external_id,
    }
    raw_compact = json.dumps(payload, separators=(",", ":")).encode()  # 紧凑字节
    raw_spaced = json.dumps(payload).encode()                         # 默认带空格字节
    assert raw_compact != raw_spaced
    sig_compact = hmac.new(TEST_KEY.encode(), raw_compact, hashlib.sha512).hexdigest()

    # 用对 raw_compact 的签名,却送 raw_spaced 字节 → 字节不同 → 验签失败
    label = await process_oxapay_callback(db_session, raw_body=raw_spaced, hmac_header=sig_compact)
    assert label == "rejected: bad signature"


@pytest.mark.asyncio
async def test_callback_status_paying_ignored(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """② 验签过但状态 'Paying'(中间态)→ 忽略 · 不查单、不开权益。"""
    order = await _make_pending(db_session, monkeypatch, "month", "trk_paying")
    monkeypatch.setattr(order_mod, "get_payment", _boom_get_payment)

    raw, sig = _signed_callback(order.external_id, "trk_paying", status="Paying")
    label = await process_oxapay_callback(db_session, raw_body=raw, hmac_header=sig)
    assert label.startswith("ignored")
    await db_session.refresh(order)
    assert order.status == "pending"
    assert await _sub(db_session, order.user_id) is None


@pytest.mark.asyncio
async def test_callback_track_id_mismatch_rejected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """③ 验签过、状态 Paid,但 track_id ≠ 建单存的 gateway_txid → 拒(防拿别单 track_id 套现)。"""
    order = await _make_pending(db_session, monkeypatch, "month", "trk_real")
    monkeypatch.setattr(order_mod, "get_payment", _boom_get_payment)

    raw, sig = _signed_callback(order.external_id, "trk_FORGED", status="Paid")
    label = await process_oxapay_callback(db_session, raw_body=raw, hmac_header=sig)
    assert label == "rejected: track_id mismatch"
    await db_session.refresh(order)
    assert order.status == "pending"
    assert await _sub(db_session, order.user_id) is None


@pytest.mark.asyncio
async def test_callback_amount_insufficient_rejected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """④ 查单真实金额 < 应付 → 拒(防伪造回调 / 少付)。"""
    order = await _make_pending(db_session, monkeypatch, "quarter", "trk_low")
    monkeypatch.setattr(order_mod, "get_payment", _fake_get_payment("paid", "5.0"))  # 实付 5 < 9.9

    raw, sig = _signed_callback(order.external_id, "trk_low", status="Paid")
    label = await process_oxapay_callback(db_session, raw_body=raw, hmac_header=sig)
    assert label.startswith("rejected")
    await db_session.refresh(order)
    assert order.status == "pending"
    assert await _sub(db_session, order.user_id) is None


@pytest.mark.asyncio
async def test_callback_query_status_not_paid_rejected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """④ 回调称 Paid 但独立查单真实 status='new'(未付)→ 拒(只信查单)。"""
    order = await _make_pending(db_session, monkeypatch, "quarter", "trk_fakepaid")
    monkeypatch.setattr(order_mod, "get_payment", _fake_get_payment("new", "9.9"))

    raw, sig = _signed_callback(order.external_id, "trk_fakepaid", status="Paid")
    label = await process_oxapay_callback(db_session, raw_body=raw, hmac_header=sig)
    assert label.startswith("rejected")
    await db_session.refresh(order)
    assert order.status == "pending"


@pytest.mark.asyncio
async def test_callback_unknown_order_id_ignored(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验签过但 order_id 无对应 pending 订单 → 忽略 · 不查单。"""
    monkeypatch.setattr(order_mod, "get_payment", _boom_get_payment)
    raw, sig = _signed_callback("__NOPE__", "trk_any", status="Paid")
    label = await process_oxapay_callback(db_session, raw_body=raw, hmac_header=sig)
    assert label.startswith("ignored")


# ── 订单状态查询(前端轮询 · 限本人)─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_order_status_owner_only(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """本人查得到订单状态 · 他人查不到(None · 端点转 404,不泄露他人订单)。"""
    owner = await make_user(db_session)
    other = await make_user(db_session)
    monkeypatch.setattr(order_mod, "create_invoice", _fake_create_invoice("trk", "https://x/trk"))
    order, _ = await create_payment_order(db_session, owner.id, "month")

    mine = await get_order_status(db_session, owner.id, order.external_id)
    assert mine is not None
    assert mine.status == "pending"
    assert mine.period == "month"
    assert await get_order_status(db_session, other.id, order.external_id) is None
    assert await get_order_status(db_session, owner.id, "__NOPE__") is None


# ── ★ 红线:支付域 import 树不含 engine/virtual_trading(AST 扫描,含 oxapay_client.py)──


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
