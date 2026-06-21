"""周报素材模块(第三刀-A)pytest。

覆盖:
- ★提取:md 直读 / PDF pypdf / 损坏 PDF + 不支持类型 → MaterialExtractError。
- ★注入:build_materials_text 拼接 + 截断 + ★总预算守卫(超限丢最大并 log)+ 无素材空串。
- ★生成注入:generate 把素材文本注入 prompt;无素材优雅降级(不加素材块、不崩)。
- ★清理:cleanup_expired_materials 删 7 天前行。
- ★AdminDep 403 矩阵(upload/list/delete)+ 素材 CRUD(上传 md→列表→删除)+ 损坏 422。
"""

from __future__ import annotations

import io
from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth import issue_session
from app.services.clickhouse_client import ClickHouseClient
from app.services.report import generate as gen
from app.services.report import materials as mat
from tests.factories import make_user

# ===== helpers =====


async def _authed_headers(db: AsyncSession, *, role: str = "user") -> dict[str, str]:
    user = await make_user(db, role=role)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


def _make_pdf(text: str) -> bytes:
    """reportlab 造一个含 text 的最小 PDF(测 pypdf 提取)。"""
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(80, 750, text)
    c.save()
    return buf.getvalue()


class _StubRawCH:
    async def query(self, *_a: object, **_k: object) -> object:
        raise RuntimeError("stub: 单测无 ClickHouse")


class _StubCH:
    _client = _StubRawCH()


async def _add_material(
    db: AsyncSession, *, text: str, filename: str = "m.md",
) -> int:
    ps, pe = gen.current_report_period()
    user = await make_user(db)
    m = await mat.create_material(
        db, filename=filename, content_type="text/markdown",
        data=text.encode("utf-8"), period_start=ps, period_end=pe, uploaded_by=user.id,
    )
    return m.id


# ===== ★ 提取 =====


def test_extract_md():
    kind, text = mat.extract_text("a.md", "text/markdown", "本周A股震荡。".encode())
    assert kind == "md"
    assert text == "本周A股震荡。"


def test_extract_pdf():
    kind, text = mat.extract_text("b.pdf", "application/pdf", _make_pdf("Weekly research 2026"))
    assert kind == "pdf"
    assert "Weekly research 2026" in text


def test_extract_corrupt_pdf_raises():
    with pytest.raises(mat.MaterialExtractError):
        mat.extract_text("x.pdf", "application/pdf", b"not a real pdf at all")


def test_extract_unsupported_raises():
    with pytest.raises(mat.MaterialExtractError):
        mat.extract_text("a.docx", "application/octet-stream", b"\x00\x01")


# ===== ★ 注入:拼接 + 截断 + 预算守卫 + 空 =====


@pytest.mark.asyncio
async def test_build_materials_text_joins(db_session: AsyncSession):
    await _add_material(db_session, text="独家调研:某板块景气回升。", filename="r1.md")
    out = await mat.build_materials_text(db_session, period_start=gen.current_report_period()[0])
    assert "独家调研:某板块景气回升。" in out
    assert "【素材:r1.md】" in out


@pytest.mark.asyncio
async def test_build_materials_text_empty(db_session: AsyncSession):
    out = await mat.build_materials_text(db_session, period_start=gen.current_report_period()[0])
    assert out == ""


@pytest.mark.asyncio
async def test_build_materials_text_truncates(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(mat, "_PER_MATERIAL_CHAR_CAP", 5)
    await _add_material(db_session, text="一二三四五六七八九十", filename="long.md")
    out = await mat.build_materials_text(db_session, period_start=gen.current_report_period()[0])
    assert "[已截断]" in out, "★单份超 cap 必须截断标记"
    assert "六七八九十" not in out


@pytest.mark.asyncio
async def test_build_materials_text_budget_guard_drops_largest(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """★总预算守卫:超预算丢『估算 token 最大』的素材 + ★log 丢了什么(不静默)。"""
    monkeypatch.setattr(mat, "_TOTAL_TOKEN_BUDGET", 10)  # 极小预算逼出守卫
    # ★直接捕获 logger.warning(不依赖 caplog 传播配置 · 验「丢弃必须 log」)
    logged: list[tuple[object, ...]] = []
    monkeypatch.setattr(mat.logger, "warning", lambda *a, **_k: logged.append(a))

    await _add_material(db_session, text="短", filename="small.md")
    await _add_material(db_session, text="这是一份很长很长很长很长很长的素材内容用来撑爆预算", filename="big.md")
    out = await mat.build_materials_text(db_session, period_start=gen.current_report_period()[0])

    assert "big.md" not in out, "★最大素材应被丢弃"
    assert "small.md" in out, "★保留较小素材"
    assert logged, "★丢弃必须 log 出来(不静默)"
    logmsg = " ".join(str(x) for args in logged for x in args)
    assert "丢弃" in logmsg
    assert "big.md" in logmsg, "★log 必须含被丢弃的素材名"


@pytest.mark.asyncio
async def test_cleanup_expired_materials(db_session: AsyncSession):
    from datetime import UTC, datetime, timedelta

    await _add_material(db_session, text="本期素材", filename="keep.md")
    # before=未来 → 删全部(验证删除逻辑);返回行数 ≥ 1
    deleted = await mat.cleanup_expired_materials(
        db_session, before=datetime.now(tz=UTC) + timedelta(days=1),
    )
    assert deleted >= 1
    out = await mat.build_materials_text(db_session, period_start=gen.current_report_period()[0])
    assert out == "", "★清理后本期无素材"


# ===== ★ 生成注入 + 无素材降级 =====


@pytest.mark.asyncio
async def test_generate_injects_materials(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    await _add_material(db_session, text="独家调研:景气回升。", filename="r.md")

    captured: dict[str, str] = {}

    class _Resp:
        content = "市场动态概述。仅供参考,不构成投资建议。"

    async def _fake_ainvoke(prompt: str, **_k: object) -> _Resp:
        captured["prompt"] = prompt
        return _Resp()

    monkeypatch.setattr(gen, "ainvoke", _fake_ainvoke)
    await gen.generate_weekly_report_draft(db_session, cast(ClickHouseClient, _StubCH()))

    assert "独家调研:景气回升。" in captured["prompt"], "★素材文本必须注入 prompt"
    assert "参考素材" in captured["prompt"]


@pytest.mark.asyncio
async def test_generate_no_materials_degrades(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, str] = {}

    class _Resp:
        content = "市场动态概述。仅供参考,不构成投资建议。"

    async def _fake_ainvoke(prompt: str, **_k: object) -> _Resp:
        captured["prompt"] = prompt
        return _Resp()

    monkeypatch.setattr(gen, "ainvoke", _fake_ainvoke)
    report = await gen.generate_weekly_report_draft(db_session, cast(ClickHouseClient, _StubCH()))

    assert "参考素材" not in captured["prompt"], "★无素材不加素材块"
    assert report.status == "draft"


# ===== ★ AdminDep 403 矩阵 =====

_MAT_ENDPOINTS = [
    ("get", "/api/v1/admin/report-materials"),
    ("delete", "/api/v1/admin/report-materials/1"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "url"), _MAT_ENDPOINTS)
async def test_materials_unauthenticated_401(client: AsyncClient, method: str, url: str):
    r = await client.request(method, url)
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "url"), _MAT_ENDPOINTS)
async def test_materials_normal_user_403(
    client: AsyncClient, db_session: AsyncSession, method: str, url: str,
):
    headers = await _authed_headers(db_session, role="user")
    r = await client.request(method, url, headers=headers)
    assert r.status_code == 403
    assert r.json()["detail"] == "Forbidden"


@pytest.mark.asyncio
async def test_material_upload_normal_user_403(client: AsyncClient, db_session: AsyncSession):
    headers = await _authed_headers(db_session, role="user")
    r = await client.post(
        "/api/v1/admin/report-materials",
        headers=headers,
        files={"file": ("m.md", b"x", "text/markdown")},
    )
    assert r.status_code == 403


# ===== ★ 素材 CRUD(upload md → list → delete)=====


@pytest.mark.asyncio
async def test_material_crud_flow(client: AsyncClient, db_session: AsyncSession):
    headers = await _authed_headers(db_session, role="admin")

    # 上传 md
    r = await client.post(
        "/api/v1/admin/report-materials",
        headers=headers,
        files={"file": ("研报.md", "本周A股震荡上行。".encode(), "text/markdown")},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["content_type"] == "md"
    assert body["char_count"] == len("本周A股震荡上行。")
    mid = body["id"]

    # 列表含本期素材
    r = await client.get("/api/v1/admin/report-materials", headers=headers)
    assert r.status_code == 200
    lst = r.json()
    assert any(it["id"] == mid for it in lst["items"])
    assert lst["period_start"]
    assert lst["period_end"]

    # 删除
    r = await client.delete(f"/api/v1/admin/report-materials/{mid}", headers=headers)
    assert r.status_code == 204

    # 删后不在列表
    r = await client.get("/api/v1/admin/report-materials", headers=headers)
    assert not any(it["id"] == mid for it in r.json()["items"])


@pytest.mark.asyncio
async def test_material_upload_corrupt_pdf_422(client: AsyncClient, db_session: AsyncSession):
    headers = await _authed_headers(db_session, role="admin")
    r = await client.post(
        "/api/v1/admin/report-materials",
        headers=headers,
        files={"file": ("bad.pdf", b"not a real pdf", "application/pdf")},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_material_delete_404(client: AsyncClient, db_session: AsyncSession):
    headers = await _authed_headers(db_session, role="admin")
    r = await client.delete("/api/v1/admin/report-materials/999999", headers=headers)
    assert r.status_code == 404
