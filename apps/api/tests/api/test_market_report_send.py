"""市场周报 P3/P4 pytest(发送广播 + 订阅)。

覆盖:
- ★PDF 生成(内容 → 非空 PDF · 中文不崩 · %PDF 头)。
- ★邮件带附件(mock Resend → 验 attachments base64)。
- ★收件人查询(只取订阅用户 weekly_report_enabled)。
- ★广播失败隔离(一个用户邮件失败不影响其他人 / 不阻止 status=sent)。
- ★TG/飞书提示(dispatch 被调 WeeklyReportSentEvent)。
- ★status 流转 approved→sent · 只 approved 可发(draft/sent → ValueError/409)。
- ★send 端点 403 矩阵 + 404 + 409 + 0 订阅 happy path。
- ★订阅开关 PUT/GET 持久化。
"""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_report import MarketReport
from app.models.notification import NotificationConfig
from app.services.auth import issue_session
from app.services.report.pdf import render_report_pdf
from app.services.report.send import query_subscribers, send_report
from tests.factories import make_user

# ===== helpers =====


async def _authed_headers(db: AsyncSession, *, role: str = "user") -> dict[str, str]:
    user = await make_user(db, role=role)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


async def _insert_report(
    db: AsyncSession, *, title: str = "测试周报", status: str = "approved",
) -> int:
    report = MarketReport(
        title=title,
        content="本周A股震荡。\n美股科技领涨。\n仅供参考,不构成投资建议。",
        status=status,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report.id


async def _make_subscriber(
    db: AsyncSession, *, email: str, subscribed: bool,
) -> object:
    user = await make_user(db, email=email)
    db.add(NotificationConfig(user_id=user.id, weekly_report_enabled=subscribed))
    await db.commit()
    return user.id


# ===== ★ PDF 生成 =====


def test_render_report_pdf_nonempty():
    """内容 → 非空 PDF · %PDF 头 · 中文不崩。"""
    pdf = render_report_pdf("市场周报 · 中文标题", "第一段。\n第二段更长一些的内容。\n仅供参考,不构成投资建议。")
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 1000


def test_render_report_pdf_disclaimer_fallback_does_not_crash():
    """content 不含免责 → 兜底补一行 · 仍出有效 PDF(免责红线双保险不崩)。"""
    pdf = render_report_pdf("无免责标题", "纯内容没有免责语。")
    assert pdf[:5] == b"%PDF-"


# ===== ★ 邮件带附件(mock Resend) =====


@pytest.mark.asyncio
async def test_send_report_email_attaches_pdf(monkeypatch: pytest.MonkeyPatch):
    """send_report_email → Resend body 含 attachments(filename + base64 内容)。"""
    from app.services import email as email_mod

    captured: dict[str, object] = {}

    class _FakeResp:
        def raise_for_status(self) -> None:
            return None

    class _FakeClient:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *_a: object) -> bool:
            return False

        async def post(
            self, _url: str, *, json: object = None, **_kwargs: object,
        ) -> _FakeResp:
            captured["json"] = json
            return _FakeResp()

    monkeypatch.setenv("RESEND_API_KEY", "test_key")
    monkeypatch.setattr(email_mod.httpx, "AsyncClient", _FakeClient)

    pdf = b"%PDF-fake-bytes"
    await email_mod.send_report_email(
        to="sub@example.com", subject="本周周报", html="<p>正文</p>",
        pdf_bytes=pdf, pdf_filename="周报.pdf",
    )

    body = captured["json"]
    assert isinstance(body, dict)
    assert body["to"] == ["sub@example.com"]
    att = body["attachments"][0]
    assert att["filename"] == "周报.pdf"
    assert att["content"] == base64.b64encode(pdf).decode("ascii")


@pytest.mark.asyncio
async def test_send_report_email_no_key_simulated(monkeypatch: pytest.MonkeyPatch):
    """无 RESEND_API_KEY → 模拟投递不抛(dev 友好)。"""
    from app.services import email as email_mod

    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    # 不应抛
    await email_mod.send_report_email(
        to="x@y.com", subject="s", html="h", pdf_bytes=b"%PDF-", pdf_filename="r.pdf",
    )


# ===== ★ 收件人查询(只取订阅用户) =====


@pytest.mark.asyncio
async def test_query_subscribers_only_subscribed(db_session: AsyncSession):
    """只返回 weekly_report_enabled=true 的用户(未订阅 / 无配置不返回)。"""
    sub1 = await _make_subscriber(db_session, email="s1@ex.com", subscribed=True)
    sub2 = await _make_subscriber(db_session, email="s2@ex.com", subscribed=True)
    await _make_subscriber(db_session, email="n1@ex.com", subscribed=False)
    await make_user(db_session, email="noconfig@ex.com")  # 无 NotificationConfig
    await db_session.commit()

    subs = await query_subscribers(db_session)
    ids = {uid for uid, _email in subs}
    emails = {email for _uid, email in subs}
    assert sub1 in ids
    assert sub2 in ids
    assert len(subs) == 2, "★只发订阅用户(未订阅 / 无配置不在收件人内)"
    assert "n1@ex.com" not in emails
    assert "noconfig@ex.com" not in emails


# ===== ★ 广播失败隔离 + status 流转 + dispatch 提示 =====


@pytest.mark.asyncio
async def test_send_report_broadcast_failure_isolation(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """一个用户邮件失败 → 其他人照发 + status 仍 sent · dispatch 每人都调(轻提示)。"""
    from app.services import email as email_mod
    from app.services.report import send as send_mod

    await _make_subscriber(db_session, email="ok@ex.com", subscribed=True)
    await _make_subscriber(db_session, email="fail@ex.com", subscribed=True)
    await _make_subscriber(db_session, email="off@ex.com", subscribed=False)
    rid = await _insert_report(db_session, status="approved")

    # mock 邮件:fail@ 抛,其他成功(★失败隔离验证)
    async def _fake_email(*, to: str, **_k: object) -> None:
        if to == "fail@ex.com":
            msg = "模拟投递失败"
            raise RuntimeError(msg)

    # mock dispatch:记录被调的事件 + 返回有投递结果
    dispatched: list[object] = []

    async def _fake_dispatch(_session: object, user_id: object, event: object) -> object:
        dispatched.append((user_id, event))
        return SimpleNamespace(results=[object()])

    monkeypatch.setattr(email_mod, "send_report_email", _fake_email)
    monkeypatch.setattr(send_mod, "dispatch", _fake_dispatch)

    result = await send_report(db_session, rid)

    assert result.recipients == 2, "★只 2 个订阅用户(off@ 不在内)"
    assert result.email_sent == 1
    assert result.email_failed == 1, "★失败隔离:fail@ 失败不影响 ok@"
    assert result.notify_sent == 2, "★每个订阅用户都发轻提示"
    assert len(dispatched) == 2
    # ★dispatch 用 WeeklyReportSentEvent
    from app.services.notifications.events import WeeklyReportSentEvent

    assert all(isinstance(ev, WeeklyReportSentEvent) for _uid, ev in dispatched)

    # ★status 流转 approved → sent
    report = await db_session.get(MarketReport, rid)
    assert report is not None
    assert report.status == "sent"
    assert report.sent_at is not None


@pytest.mark.asyncio
async def test_send_report_only_approved(db_session: AsyncSession):
    """只 approved 可发:draft / sent 抛 ValueError(→ 端点 409)· 不存在抛 LookupError(→ 404)。"""
    draft_id = await _insert_report(db_session, status="draft")
    with pytest.raises(ValueError, match="approved"):
        await send_report(db_session, draft_id)

    sent_id = await _insert_report(db_session, status="sent")
    with pytest.raises(ValueError, match="approved"):
        await send_report(db_session, sent_id)

    with pytest.raises(LookupError):
        await send_report(db_session, 999999)


# ===== ★ send 端点(403 矩阵 + 404 + 409 + 0 订阅 happy) =====


@pytest.mark.asyncio
async def test_send_endpoint_unauthenticated_401(client: AsyncClient):
    r = await client.post("/api/v1/admin/reports/1/send")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_send_endpoint_normal_user_403(client: AsyncClient, db_session: AsyncSession):
    headers = await _authed_headers(db_session, role="user")
    r = await client.post("/api/v1/admin/reports/1/send", headers=headers)
    assert r.status_code == 403
    assert r.json()["detail"] == "Forbidden"


@pytest.mark.asyncio
async def test_send_endpoint_404_missing(client: AsyncClient, db_session: AsyncSession):
    headers = await _authed_headers(db_session, role="admin")
    r = await client.post("/api/v1/admin/reports/999999/send", headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_send_endpoint_409_not_approved(client: AsyncClient, db_session: AsyncSession):
    rid = await _insert_report(db_session, status="draft")
    headers = await _authed_headers(db_session, role="admin")
    r = await client.post(f"/api/v1/admin/reports/{rid}/send", headers=headers)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_send_endpoint_zero_subscribers_ok(client: AsyncClient, db_session: AsyncSession):
    """approved + 0 订阅 → 200 · recipients=0 · status=sent(端点 wiring + 状态机)。"""
    rid = await _insert_report(db_session, status="approved")
    headers = await _authed_headers(db_session, role="admin")
    r = await client.post(f"/api/v1/admin/reports/{rid}/send", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "sent"
    assert body["recipients"] == 0
    assert body["email_sent"] == 0


# ===== ★ 订阅开关 PUT/GET 持久化 =====


@pytest.mark.asyncio
async def test_subscription_toggle_persists(client: AsyncClient, db_session: AsyncSession):
    """PUT weekly_report_enabled=true → GET 返回 true(订阅开关落库)。"""
    headers = await _authed_headers(db_session, role="user")

    # 默认 false(未配置 → lazy create 默认对象)
    r = await client.get("/api/v1/notifications/config", headers=headers)
    assert r.status_code == 200
    assert r.json()["weekly_report_enabled"] is False

    # 开启订阅
    r = await client.put(
        "/api/v1/notifications/config", headers=headers,
        json={"weekly_report_enabled": True},
    )
    assert r.status_code == 200
    assert r.json()["weekly_report_enabled"] is True

    # GET 复核持久化
    r = await client.get("/api/v1/notifications/config", headers=headers)
    assert r.json()["weekly_report_enabled"] is True
