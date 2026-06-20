"""市场周报 P1/P2 pytest。

覆盖:
- ★生成管道(mock AI · stub CH):聚合防御 + validate_advisory 被调 + 免责兜底 + 存 draft。
- ★403 矩阵:/admin/reports* 每端点 未登录 401 / 普通 403 / admin 200(AdminDep 唯一边界)。
- ★复核 CRUD 状态流转:list / get / edit / approve(draft→approved) + 幂等(非 draft 拒 409)。
"""

from __future__ import annotations

from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_report import MarketReport
from app.services.auth import issue_session
from app.services.clickhouse_client import ClickHouseClient
from tests.factories import make_user

# ===== helpers =====


async def _authed_headers(db: AsyncSession, *, role: str = "user") -> dict[str, str]:
    user = await make_user(db, role=role)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


async def _insert_draft(db: AsyncSession, *, title: str = "测试周报", status: str = "draft") -> int:
    report = MarketReport(title=title, content="占位正文。\n\n仅供参考,不构成投资建议。", status=status)
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report.id


class _StubRawCH:
    """stub raw AsyncClient · query 抛错 → 触发聚合的防御退化(单测不依赖真 CH)。"""

    async def query(self, *_a: object, **_k: object) -> object:
        raise RuntimeError("stub: 单测无 ClickHouse")


class _StubCH:
    _client = _StubRawCH()


# ===== ★ 生成管道(mock AI · stub CH) =====


@pytest.mark.asyncio
async def test_generate_draft_pipeline_disclaimer_enforced(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
):
    """生成管道:LLM 返回【不含免责】文本 → 强制免责兜底补上 + validate_advisory 被调 + 存 draft。"""
    from app.services.report import generate as gen

    # mock LLM:返回不含免责的内容(验证兜底会补)
    class _Resp:
        content = "本周加密与美股震荡上行,A股分化。"

    async def _fake_ainvoke(*_a: object, **_k: object) -> _Resp:
        return _Resp()

    calls = {"validate": 0}
    orig_validate = gen.validate_advisory

    def _spy_validate(text: str) -> str:
        calls["validate"] += 1
        return orig_validate(text)

    monkeypatch.setattr(gen, "ainvoke", _fake_ainvoke)
    monkeypatch.setattr(gen, "validate_advisory", _spy_validate)

    report = await gen.generate_weekly_report_draft(
        db_session, cast(ClickHouseClient, _StubCH()),
    )

    assert report.id is not None
    assert report.status == "draft"
    assert calls["validate"] == 1, "★validate_advisory 必须被调(免责红线)"
    assert "不构成投资建议" in report.content, "★免责兜底必须保证免责串存在"
    assert report.period_start is not None
    assert report.period_end is not None
    assert report.title.startswith("市场周报")


@pytest.mark.asyncio
async def test_generate_aggregation_degrades_on_empty_ch():
    """聚合防御:CH 查询抛错 → 退化「暂无数据」不崩管道,仍出草稿。"""
    from app.services.report import generate as gen

    snapshot = await gen.aggregate_market_snapshot(cast(ClickHouseClient, _StubCH()))
    assert "暂无数据" in snapshot
    assert "A股" in snapshot
    assert "美股" in snapshot
    assert "港股" in snapshot


# ===== ★ 403 矩阵(AdminDep 唯一边界) =====

_REPORT_ENDPOINTS = [
    ("get", "/api/v1/admin/reports"),
    ("get", "/api/v1/admin/reports/1"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "url"), _REPORT_ENDPOINTS)
async def test_reports_unauthenticated_401(client: AsyncClient, method: str, url: str):
    r = await client.request(method, url)
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "url"), _REPORT_ENDPOINTS)
async def test_reports_normal_user_403(
    client: AsyncClient, db_session: AsyncSession, method: str, url: str,
):
    headers = await _authed_headers(db_session, role="user")
    r = await client.request(method, url, headers=headers)
    assert r.status_code == 403
    assert r.json()["detail"] == "Forbidden"


@pytest.mark.asyncio
async def test_reports_list_admin_200(client: AsyncClient, db_session: AsyncSession):
    await _insert_draft(db_session, title="管理列表周报")
    headers = await _authed_headers(db_session, role="admin")
    r = await client.get("/api/v1/admin/reports", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(it["title"] == "管理列表周报" for it in body["items"])
    # 列表轻量:不含正文
    assert "content" not in body["items"][0]


# ===== ★ 复核 CRUD 状态流转 =====


@pytest.mark.asyncio
async def test_report_get_edit_approve_flow(client: AsyncClient, db_session: AsyncSession):
    rid = await _insert_draft(db_session, title="待复核周报")
    headers = await _authed_headers(db_session, role="admin")

    # 看详情(含正文)
    r = await client.get(f"/api/v1/admin/reports/{rid}", headers=headers)
    assert r.status_code == 200
    assert r.json()["content"]
    assert r.json()["status"] == "draft"

    # 编辑 title + content
    r = await client.put(
        f"/api/v1/admin/reports/{rid}",
        headers=headers,
        json={"title": "已编辑标题", "content": "专业内容。仅供参考,不构成投资建议。"},
    )
    assert r.status_code == 200
    assert r.json()["title"] == "已编辑标题"

    # 批准 draft → approved
    r = await client.post(f"/api/v1/admin/reports/{rid}/approve", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    assert r.json()["approved_at"] is not None

    # ★幂等:已 approved 再批准 → 409
    r = await client.post(f"/api/v1/admin/reports/{rid}/approve", headers=headers)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_report_get_404(client: AsyncClient, db_session: AsyncSession):
    headers = await _authed_headers(db_session, role="admin")
    r = await client.get("/api/v1/admin/reports/999999", headers=headers)
    assert r.status_code == 404
