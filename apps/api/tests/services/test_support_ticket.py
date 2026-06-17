"""支付工单 / 退款(support 模块)· pytest。

🔴 红线:support 域不 import engine/virtual_trading/收款逻辑(AST 扫描钉死)· 凭证不入代码。
覆盖:create_ticket 存 DB · send_ticket_email(Resend 附件 base64 · from support@midastrade.asia)·
POST 端点(登录建单 / 校验 422 / 未登录 401 / ★邮件失败工单仍创建)· 图走附件不落盘(仅记数量)。
"""

from __future__ import annotations

import ast
import base64
import pathlib
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.support.ticket as ticket_mod
from app.core.config import settings
from app.models.support_ticket import SupportTicket
from app.services.auth import issue_session
from app.services.support.ticket import create_ticket, send_ticket_email
from tests.factories import make_user

_URL = "/api/v1/support/ticket"


async def _authed(db: AsyncSession) -> tuple[Any, dict[str, str]]:
    user = await make_user(db)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return user, {"Authorization": f"Bearer {token}"}


def _install_fake_resend(
    monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any], *, fail: bool = False,
) -> None:
    """替身 Resend HTTP · 捕获请求 body(或模拟失败)· 不真发网络。"""

    class _FakeClient:
        def __init__(self, *_a: Any, **_k: Any) -> None:
            pass

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *_a: Any) -> bool:
            return False

        async def post(
            self, url: str, *, headers: Any = None, json: Any = None,
        ) -> SimpleNamespace:
            if fail:
                raise ticket_mod.httpx.HTTPError("boom")
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr(ticket_mod.httpx, "AsyncClient", _FakeClient)


# ── 服务层:建单 + Resend 附件 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_ticket_stores(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    t = await create_ticket(
        db_session, user.id,
        contact_email="a@b.com", category="not_received", description="支付没开通",
        related_order_id="ord_1", image_count=2,
    )
    assert t.id > 0
    assert t.status == "open"
    assert t.image_count == 2  # noqa: PLR2004
    assert t.user_id == user.id
    assert t.related_order_id == "ord_1"


@pytest.mark.asyncio
async def test_send_ticket_email_attachments_base64(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ from=已验证域名 support@midastrade.asia · to=客服箱 · 附件 content 为 base64 · subject 含工单ID。"""
    user = await make_user(db_session)
    t = await create_ticket(
        db_session, user.id,
        contact_email="c@d.com", category="duplicate_charge", description="重复扣了两次",
        related_order_id=None, image_count=1,
    )
    monkeypatch.setenv("RESEND_API_KEY", "test_key")
    captured: dict[str, Any] = {}
    _install_fake_resend(monkeypatch, captured)

    ok = await send_ticket_email(ticket=t, user_email=user.email, images=[("p.png", b"IMGBYTES")])
    assert ok is True
    body = captured["json"]
    assert "support@midastrade.asia" in body["from"]
    assert body["from"] == settings.support_email_from
    assert body["to"] == [settings.support_email_to]
    assert f"#{t.id}" in body["subject"]
    # ★ category 英文值 → 中文标签(邮件 subject + 正文展示)
    assert "重复扣款" in body["subject"]
    assert "重复扣款" in body["html"]
    assert body["attachments"][0]["content"] == base64.b64encode(b"IMGBYTES").decode("ascii")
    assert body["attachments"][0]["filename"] == "p.png"
    # 凭证只在 header,不进 body
    assert "Bearer test_key" in captured["headers"]["Authorization"]


@pytest.mark.asyncio
async def test_send_ticket_email_no_key_returns_false(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无 RESEND_API_KEY(dev)→ 返回 False(不抛 · 工单已存不阻塞)。"""
    user = await make_user(db_session)
    t = await create_ticket(
        db_session, user.id,
        contact_email="c@d.com", category="other", description="x",
        related_order_id=None, image_count=0,
    )
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert await send_ticket_email(ticket=t, user_email=user.email, images=[]) is False


# ── 端点:登录建单 / 校验 / 未登录 / 邮件失败仍建单 ─────────────────────────────────


@pytest.mark.asyncio
async def test_submit_ticket_creates(client: AsyncClient, db_session: AsyncSession) -> None:
    """登录用户提工单(无图)→ 200 + 存 DB(默认联系邮箱=账号邮箱 · image_count=0)。"""
    user, headers = await _authed(db_session)
    resp = await client.post(
        _URL, data={"category": "not_received", "description": "支付后没开通会员"}, headers=headers,
    )
    assert resp.status_code == 200  # noqa: PLR2004
    body = resp.json()
    assert body["status"] == "open"
    assert body["ticket_id"] > 0
    t = await db_session.get(SupportTicket, body["ticket_id"])
    assert t is not None
    assert t.user_id == user.id
    assert t.category == "not_received"
    assert t.image_count == 0
    assert t.contact_email == user.email  # 未填 → 默认账号邮箱


@pytest.mark.asyncio
async def test_submit_ticket_with_images_and_email(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """带图 + 邮件成功 → image_count=2 · 附件 base64 · related_order_id 存 · email_sent=True。"""
    user, headers = await _authed(db_session)
    monkeypatch.setenv("RESEND_API_KEY", "test_key")
    captured: dict[str, Any] = {}
    _install_fake_resend(monkeypatch, captured)

    files = [
        ("images", ("a.png", b"PNG1", "image/png")),
        ("images", ("b.jpg", b"JPG2", "image/jpeg")),
    ]
    resp = await client.post(
        _URL,
        data={"category": "duplicate_charge", "description": "重复扣款了", "related_order_id": "ord_123"},
        files=files, headers=headers,
    )
    assert resp.status_code == 200  # noqa: PLR2004
    body = resp.json()
    assert body["email_sent"] is True
    t = await db_session.get(SupportTicket, body["ticket_id"])
    assert t is not None
    assert t.image_count == 2  # noqa: PLR2004
    assert t.related_order_id == "ord_123"
    atts = captured["json"]["attachments"]
    assert len(atts) == 2  # noqa: PLR2004
    assert atts[0]["content"] == base64.b64encode(b"PNG1").decode("ascii")


@pytest.mark.asyncio
async def test_submit_ticket_unauthed_401(client: AsyncClient) -> None:
    """🔴 未登录 → 401(CurrentUserDep 拦 · 不接受伪造身份)。"""
    resp = await client.post(_URL, data={"category": "not_received", "description": "x"})
    assert resp.status_code == 401  # noqa: PLR2004


@pytest.mark.asyncio
async def test_submit_ticket_blank_description_422(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _user, headers = await _authed(db_session)
    resp = await client.post(
        _URL, data={"category": "not_received", "description": "   "}, headers=headers,
    )
    assert resp.status_code == 422  # noqa: PLR2004


@pytest.mark.asyncio
async def test_submit_ticket_bad_category_422(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _user, headers = await _authed(db_session)
    resp = await client.post(
        _URL, data={"category": "hack", "description": "x"}, headers=headers,
    )
    assert resp.status_code == 422  # noqa: PLR2004


@pytest.mark.asyncio
async def test_submit_ticket_bad_email_422(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _user, headers = await _authed(db_session)
    resp = await client.post(
        _URL,
        data={"category": "not_received", "description": "x", "contact_email": "notanemail"},
        headers=headers,
    )
    assert resp.status_code == 422  # noqa: PLR2004


@pytest.mark.asyncio
async def test_submit_ticket_too_many_images_422(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """图片 4 张(> support_max_images=3)→ 422。"""
    _user, headers = await _authed(db_session)
    files = [("images", (f"{i}.png", b"x", "image/png")) for i in range(4)]
    resp = await client.post(
        _URL, data={"category": "not_received", "description": "多图"}, files=files, headers=headers,
    )
    assert resp.status_code == 422  # noqa: PLR2004


@pytest.mark.asyncio
async def test_submit_ticket_non_image_type_422(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """非 JPEG/PNG(text/plain)→ 422。"""
    _user, headers = await _authed(db_session)
    files = [("images", ("evil.txt", b"hi", "text/plain"))]
    resp = await client.post(
        _URL, data={"category": "not_received", "description": "坏类型"}, files=files, headers=headers,
    )
    assert resp.status_code == 422  # noqa: PLR2004


@pytest.mark.asyncio
async def test_submit_ticket_oversize_image_422(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单张超上限 → 422(monkeypatch 上限 1MB,送 ~1MB+ 触发)。"""
    _user, headers = await _authed(db_session)
    monkeypatch.setattr(settings, "support_max_image_mb", 1)
    big = b"x" * (1024 * 1024 + 16)
    files = [("images", ("big.png", big, "image/png"))]
    resp = await client.post(
        _URL, data={"category": "not_received", "description": "超大图"}, files=files, headers=headers,
    )
    assert resp.status_code == 422  # noqa: PLR2004


@pytest.mark.asyncio
async def test_submit_ticket_email_failure_still_creates(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ Resend 发送失败 → 工单仍创建(DB 有行)+ email_sent=False + 提示延迟(不 500)。"""
    _user, headers = await _authed(db_session)
    monkeypatch.setenv("RESEND_API_KEY", "test_key")
    captured: dict[str, Any] = {}
    _install_fake_resend(monkeypatch, captured, fail=True)

    resp = await client.post(
        _URL, data={"category": "not_received", "description": "邮件挂了但工单要在"}, headers=headers,
    )
    assert resp.status_code == 200  # noqa: PLR2004
    body = resp.json()
    assert body["email_sent"] is False
    assert "延迟" in body["message"]
    assert await db_session.get(SupportTicket, body["ticket_id"]) is not None


@pytest.mark.asyncio
async def test_my_tickets_owner_only(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """GET /support/tickets 限本人 · 只返回自己的工单。"""
    user, headers = await _authed(db_session)
    await create_ticket(
        db_session, user.id,
        contact_email=user.email, category="not_received", description="我的工单",
        related_order_id=None, image_count=0,
    )
    other = await make_user(db_session)
    await create_ticket(
        db_session, other.id,
        contact_email=other.email, category="not_received", description="他人工单",
        related_order_id=None, image_count=0,
    )
    resp = await client.get("/api/v1/support/tickets", headers=headers)
    assert resp.status_code == 200  # noqa: PLR2004
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["description"] == "我的工单"


# ── ★ 红线:support 域 import 树不含 engine/虚拟交易/收款逻辑(AST 扫描)─────────────


def test_support_domain_no_engine_or_payment_import() -> None:
    root = pathlib.Path(__file__).resolve().parents[1].parent  # apps/api
    files = [
        *(root / "app" / "services" / "support").glob("*.py"),
        root / "app" / "api" / "v1" / "support.py",
        root / "app" / "models" / "support_ticket.py",
        root / "app" / "schemas" / "support.py",
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
                if (
                    "virtual_trading" in m
                    or "engine" in m.split(".")
                    or m.startswith("app.services.payment")
                ):
                    bad.append((f.name, m))
    assert not bad, f"🔴 support 域不得 import 交易/engine/收款逻辑:{bad}"
