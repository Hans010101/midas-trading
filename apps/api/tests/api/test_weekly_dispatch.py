"""周报全自动发送(weekly_dispatch)pytest。

覆盖:★md 解析 + 缺失标记 · ★should_auto_send_on_upload 补救窗口纯函数 · ★邮件渲染(含免责)·
upsert + ★发送幂等 · ★run_scheduled_dispatch(有/无/已发)· AdminDep 403 矩阵 · upload 端点 + 422。
"""

from __future__ import annotations

from datetime import datetime
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


# ===== ★ 补救窗口纯函数 =====


@pytest.mark.parametrize(
    ("now", "year", "week", "status", "expected"),
    [
        (datetime(2026, 6, 21, 21, 30, tzinfo=CST), 2026, 25, "uploaded", True),  # 周日21:30 本周未发
        (datetime(2026, 6, 21, 21, 30, tzinfo=CST), 2026, 25, "sent", False),  # 已发
        (datetime(2026, 6, 21, 20, 0, tzinfo=CST), 2026, 25, "uploaded", False),  # 21:00前
        (datetime(2026, 6, 22, 8, 0, tzinfo=CST), 2026, 25, "uploaded", True),  # 周一08:00 本周(跨周)
        (datetime(2026, 6, 22, 10, 0, tzinfo=CST), 2026, 25, "uploaded", False),  # 周一10:00 窗口后
        (datetime(2026, 6, 21, 21, 30, tzinfo=CST), 2026, 24, "uploaded", False),  # 非本周
        (datetime(2026, 6, 17, 12, 0, tzinfo=CST), 2026, 25, "uploaded", False),  # 周三 窗口外
    ],
)
def test_should_auto_send(
    now: datetime, year: int, week: int, status: str, expected: bool,
):
    assert wd.should_auto_send_on_upload(now, year, week, status) is expected


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


# ===== ★ run_scheduled_dispatch(定时:有/无/已发)=====


@pytest.mark.asyncio
async def test_scheduled_dispatch_paths(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    _mock_broadcast(monkeypatch)
    sun = datetime(2026, 6, 21, 21, 0, tzinfo=CST)  # ISO 周 25

    # 无上传 → skipped_no_upload
    r = await wd.run_scheduled_dispatch(db_session, now=sun)
    assert r["action"] == "skipped_no_upload"

    # 上传本周 → 定时发 sent
    user = await make_user(db_session)
    await wd.create_or_update_dispatch(
        db_session, pdf_data=b"%PDF", pdf_filename="r.pdf",
        md_text=MD_SAMPLE, uploaded_by=user.id,
    )
    r2 = await wd.run_scheduled_dispatch(db_session, now=sun)
    assert r2["action"] == "sent"

    # 再跑 → already_sent(幂等)
    r3 = await wd.run_scheduled_dispatch(db_session, now=sun)
    assert r3["action"] == "already_sent"


# ===== ★ AdminDep 403 矩阵 + upload 端点 =====

_WD_ENDPOINTS = [
    ("get", "/api/v1/admin/weekly-dispatch"),
    ("get", "/api/v1/admin/weekly-dispatch/1"),
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
async def test_wd_upload_flow(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    # 非补救窗口时刻(周三)→ 不自动发,只测解析 + 存储 + 预览
    monkeypatch.setattr(
        "app.api.v1.admin.cn_now", lambda: datetime(2026, 6, 17, 12, 0, tzinfo=CST),
    )
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
    assert body["auto_sent"] is False
    assert body["missing"] == []
    assert "核心结论" in body["email_html"]

    r = await client.get("/api/v1/admin/weekly-dispatch", headers=headers)
    assert any(it["week"] == 25 for it in r.json()["items"])
    r = await client.get(f"/api/v1/admin/weekly-dispatch/{body['id']}", headers=headers)
    assert r.status_code == 200
    assert "email_html" in r.json()


@pytest.mark.asyncio
async def test_wd_upload_bad_frontmatter_422(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "app.api.v1.admin.cn_now", lambda: datetime(2026, 6, 17, 12, 0, tzinfo=CST),
    )
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
