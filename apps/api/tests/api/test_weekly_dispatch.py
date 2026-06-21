"""周报全自动发送(weekly_dispatch)pytest。

覆盖:★md 解析 + 缺失标记 · ★should_auto_send_on_upload 补救窗口纯函数 · ★邮件渲染(含免责)·
upsert + ★发送幂等 · ★run_scheduled_dispatch(有/无/已发)· AdminDep 403 矩阵 · upload 端点 + 422。
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth import issue_session
from app.services.report import weekly_dispatch as wd
from app.services.report.weekly_email import build_subject, render_email_html
from app.services.report.weekly_md import WeeklyMdError, extract_to_json, parse_weekly_md
from tests.factories import make_user

CST = ZoneInfo("Asia/Shanghai")

MD_SAMPLE = """---
week: 25
period_start: 2026-06-15
period_end: 2026-06-21
title: 全球市场与行业机会周报
---
## 一句话导语
本周A股震荡上行,科技领涨。

## 核心结论
1. 结论一
2. 结论二
3. 结论三

## 行业强弱
### 走强
- 半导体
- AI算力
### 走弱
- 地产
- 银行

## 下周关注
- 美联储议息
- A股财报
"""


@pytest.fixture(autouse=True)
def _stub_oss(monkeypatch: pytest.MonkeyPatch) -> None:
    """★本文件 mock OSS 上传/下载(不打真 OSS · 真实接线见 test_report_oss.py)。"""

    async def _up(key: str, _data: bytes) -> str:
        return key

    async def _down(_key: str) -> bytes:
        return b"%PDF-fake-bytes"

    monkeypatch.setattr("app.services.report.weekly_dispatch.upload_material", _up)
    monkeypatch.setattr("app.services.report.weekly_dispatch.download_object", _down)


def _mock_broadcast(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_email(**_k: object) -> None:
        return None

    async def _fake_dispatch(_s: object, _u: object, _e: object) -> object:
        return SimpleNamespace(results=[])

    monkeypatch.setattr("app.services.email.send_report_email", _fake_email)
    monkeypatch.setattr("app.services.report.weekly_dispatch.dispatch", _fake_dispatch)


async def _admin_headers(db: AsyncSession, *, role: str = "admin") -> dict[str, str]:
    user = await make_user(db, role=role)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


# ===== ★ md 解析 =====


def test_parse_standard():
    ex = parse_weekly_md(MD_SAMPLE)
    assert ex.week == 25
    assert ex.period_start.isoformat() == "2026-06-15"
    assert "震荡上行" in ex.lead
    assert len(ex.conclusions) == 3
    assert ex.strong == ["半导体", "AI算力"]
    assert ex.weak == ["地产", "银行"]
    assert ex.next_week == ["美联储议息", "A股财报"]
    assert ex.missing == []


def test_parse_missing_headings_flagged():
    md = (
        "---\nweek: 25\nperiod_start: 2026-06-15\nperiod_end: 2026-06-21\ntitle: X\n---\n"
        "## 一句话导语\n仅有导语。\n"
    )
    ex = parse_weekly_md(md)
    assert ex.lead == "仅有导语。"
    assert ex.conclusions == []
    assert "核心结论" in ex.missing
    assert "行业强弱" in ex.missing
    assert "下周关注" in ex.missing


def test_parse_frontmatter_missing_raises():
    with pytest.raises(WeeklyMdError):
        parse_weekly_md("## 一句话导语\n没有 frontmatter。")
    with pytest.raises(WeeklyMdError, match="week"):
        parse_weekly_md(
            "---\nperiod_start: 2026-06-15\nperiod_end: 2026-06-21\n---\n## 一句话导语\nx\n",
        )


# ===== ★ 计划 / 取消计划 状态流转 =====


@pytest.mark.asyncio
async def test_schedule_cancel_transitions(db_session: AsyncSession):
    user = await make_user(db_session)
    rec, _ = await wd.create_or_update_dispatch(
        db_session, pdf_data=b"%PDF", pdf_filename="r.pdf",
        md_text=MD_SAMPLE, uploaded_by=user.id,
    )
    assert rec.status == "uploaded"

    # 计划发送 → scheduled
    rec = await wd.schedule_dispatch(db_session, rec.id)
    assert rec is not None
    assert rec.status == "scheduled"

    # 再计划 → 幂等仍 scheduled
    rec = await wd.schedule_dispatch(db_session, rec.id)
    assert rec is not None
    assert rec.status == "scheduled"

    # 取消计划 → uploaded
    rec = await wd.cancel_schedule(db_session, rec.id)
    assert rec is not None
    assert rec.status == "uploaded"

    # ★非 scheduled 取消 → ValueError
    with pytest.raises(ValueError, match="已计划"):
        await wd.cancel_schedule(db_session, rec.id)


@pytest.mark.asyncio
async def test_schedule_does_not_send_or_depend_on_time(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """★schedule 纯标记:不发送、不依赖当前时间(任意 now 结果都是 scheduled)。"""
    sent_calls: list[object] = []

    async def _spy_send(**_k: object) -> None:
        sent_calls.append(1)

    monkeypatch.setattr("app.services.email.send_report_email", _spy_send)
    user = await make_user(db_session)
    rec, _ = await wd.create_or_update_dispatch(
        db_session, pdf_data=b"%PDF", pdf_filename="r.pdf",
        md_text=MD_SAMPLE, uploaded_by=user.id,
    )
    # schedule 不接收 now、不发送
    out = await wd.schedule_dispatch(db_session, rec.id)
    assert out is not None
    assert out.status == "scheduled"
    assert sent_calls == [], "★计划发送绝不当场发邮件"


# ===== ★ 邮件渲染(含免责红线)=====


def test_email_render():
    j = extract_to_json(parse_weekly_md(MD_SAMPLE))
    html = render_email_html(j, unsubscribe_url="https://x/unsub")
    assert "核心结论" in html
    assert "半导体" in html
    assert "地产" in html
    assert "美联储议息" in html
    assert "第 25 周" in html
    assert "不构成任何投资建议" in html  # ★免责红线
    assert "https://x/unsub" in html
    assert build_subject(j).startswith("点金 Midas")


# ===== ★ next_sunday_2100 纯函数(下一个未过的周日21:00 · CST 边界)=====
# 2026-06 月历:每周日 = 6/7、6/14、6/21、6/28;6/26 周五、6/27 周六。


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 6, 26, 12, 0, tzinfo=CST), date(2026, 6, 28)),  # 周五 → 本周日
        (datetime(2026, 6, 27, 23, 0, tzinfo=CST), date(2026, 6, 28)),  # 周六 → 次日(本周日)
        (datetime(2026, 6, 28, 20, 59, tzinfo=CST), date(2026, 6, 28)),  # 周日20:59 → 今天
        (datetime(2026, 6, 28, 21, 0, tzinfo=CST), date(2026, 7, 5)),  # 周日21:00整 → ★下周日(跨月)
        (datetime(2026, 6, 28, 21, 1, tzinfo=CST), date(2026, 7, 5)),  # 周日21:01 → 下周日(跨月)
        (datetime(2026, 6, 22, 9, 0, tzinfo=CST), date(2026, 6, 28)),  # 周一 → 即将到来的周日
    ],
)
def test_next_sunday_2100(now: datetime, expected: date):
    assert wd.next_sunday_2100(now) == expected


def test_format_next_send_label():
    # 周五 6/26 → 本周日 6/28
    assert wd.format_next_send_label(datetime(2026, 6, 26, 12, 0, tzinfo=CST)) == "6月28日21:00"
    # ★跨月:周日 6/28 21:01 → 下周日 7/5
    assert wd.format_next_send_label(datetime(2026, 6, 28, 21, 1, tzinfo=CST)) == "7月5日21:00"


# ===== ★ upsert + 发送幂等 =====


@pytest.mark.asyncio
async def test_create_upsert_and_send_idempotent(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    _mock_broadcast(monkeypatch)
    user = await make_user(db_session)
    rec, _ex = await wd.create_or_update_dispatch(
        db_session, pdf_data=b"%PDF-x", pdf_filename="r.pdf",
        md_text=MD_SAMPLE, uploaded_by=user.id,
    )
    assert rec.year == 2026
    assert rec.week == 25
    assert rec.status == "uploaded"

    # 再上传同周 → upsert 同一行(year+week 唯一)
    rec2, _ = await wd.create_or_update_dispatch(
        db_session, pdf_data=b"%PDF-y", pdf_filename="r2.pdf",
        md_text=MD_SAMPLE, uploaded_by=user.id,
    )
    assert rec2.id == rec.id

    result = await wd.dispatch_and_send(db_session, year=2026, week=25)
    assert result.skipped is False
    # ★幂等:再发 → skipped
    result2 = await wd.dispatch_and_send(db_session, year=2026, week=25)
    assert result2.skipped is True


# ===== ★ run_scheduled_dispatch(定时★只发 scheduled)=====


@pytest.mark.asyncio
async def test_scheduled_dispatch_only_sends_scheduled(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    _mock_broadcast(monkeypatch)
    sun = datetime(2026, 6, 21, 21, 0, tzinfo=CST)  # ISO 周 25

    # 无上传 → no_scheduled(★不发提醒、安静)
    r = await wd.run_scheduled_dispatch(db_session, now=sun)
    assert r["action"] == "no_scheduled"

    # ★只上传未计划(uploaded)→ 仍 no_scheduled(不发)
    user = await make_user(db_session)
    rec, _ = await wd.create_or_update_dispatch(
        db_session, pdf_data=b"%PDF", pdf_filename="r.pdf",
        md_text=MD_SAMPLE, uploaded_by=user.id,
    )
    r2 = await wd.run_scheduled_dispatch(db_session, now=sun)
    assert r2["action"] == "no_scheduled", "★未点计划发送的不会被定时发"

    # 点计划发送(scheduled)→ 定时发 sent
    await wd.schedule_dispatch(db_session, rec.id)
    r3 = await wd.run_scheduled_dispatch(db_session, now=sun)
    assert r3["action"] == "sent"

    # 再跑 → already_sent(幂等)
    r4 = await wd.run_scheduled_dispatch(db_session, now=sun)
    assert r4["action"] == "already_sent"


# ===== ★ AdminDep 403 矩阵 + upload 端点 =====

_WD_ENDPOINTS = [
    ("get", "/api/v1/admin/weekly-dispatch"),
    ("get", "/api/v1/admin/weekly-dispatch/1"),
    ("post", "/api/v1/admin/weekly-dispatch/1/schedule"),
    ("post", "/api/v1/admin/weekly-dispatch/1/cancel-schedule"),
    ("post", "/api/v1/admin/weekly-dispatch/1/send-now"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "url"), _WD_ENDPOINTS)
async def test_wd_unauth_401(client: AsyncClient, method: str, url: str):
    r = await client.request(method, url)
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "url"), _WD_ENDPOINTS)
async def test_wd_normal_403(
    client: AsyncClient, db_session: AsyncSession, method: str, url: str,
):
    headers = await _admin_headers(db_session, role="user")
    r = await client.request(method, url, headers=headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_wd_upload_normal_403(client: AsyncClient, db_session: AsyncSession):
    headers = await _admin_headers(db_session, role="user")
    r = await client.post(
        "/api/v1/admin/weekly-dispatch/upload", headers=headers,
        files={
            "pdf": ("r.pdf", b"%PDF", "application/pdf"),
            "md": ("r.md", MD_SAMPLE.encode(), "text/markdown"),
        },
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_wd_upload_then_schedule_then_cancel(client: AsyncClient, db_session: AsyncSession):
    """端点全链:upload→uploaded · schedule→scheduled · cancel→uploaded(★上传不自动发)。"""
    headers = await _admin_headers(db_session, role="admin")
    r = await client.post(
        "/api/v1/admin/weekly-dispatch/upload", headers=headers,
        files={
            "pdf": ("周报.pdf", b"%PDF-data", "application/pdf"),
            "md": ("周报.md", MD_SAMPLE.encode(), "text/markdown"),
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["week"] == 25
    assert body["status"] == "uploaded"  # ★上传只入库,不自动发
    assert body["missing"] == []
    assert "核心结论" in body["email_html"]
    did = body["id"]

    # 计划发送 → scheduled
    r = await client.post(f"/api/v1/admin/weekly-dispatch/{did}/schedule", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "scheduled"

    # 取消计划 → uploaded
    r = await client.post(f"/api/v1/admin/weekly-dispatch/{did}/cancel-schedule", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "uploaded"

    # 列表可见
    r = await client.get("/api/v1/admin/weekly-dispatch", headers=headers)
    assert any(it["id"] == did for it in r.json()["items"])


@pytest.mark.asyncio
async def test_wd_upload_bad_frontmatter_422(client: AsyncClient, db_session: AsyncSession):
    headers = await _admin_headers(db_session, role="admin")
    r = await client.post(
        "/api/v1/admin/weekly-dispatch/upload", headers=headers,
        files={
            "pdf": ("r.pdf", b"%PDF", "application/pdf"),
            "md": ("r.md", b"no frontmatter here", "text/markdown"),
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_wd_send_now_404(client: AsyncClient, db_session: AsyncSession):
    headers = await _admin_headers(db_session, role="admin")
    r = await client.post("/api/v1/admin/weekly-dispatch/999999/send-now", headers=headers)
    assert r.status_code == 404
