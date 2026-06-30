"""铂金自助端点越权防护 pytest(多账户 PR-5a)· 🔴安全红线:A 的 token 拿不到/改不了 B 的数据。

★重点:① 非铂金→403(文案"需铂金权限")· 未登录→401 · ② per-user 开关隔离(A toggle 不影响 B)·
③ 看板隔离(A 看不到 B 影子仓)· ④ OpenAPI /platinum 路径/参数无 user_id(签名层结构性杜绝越权)。
需 DB + Redis · CI 真跑(④ OpenAPI 纯静态本地可跑)。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_clickhouse
from app.api.v1 import platinum_self
from app.main import app
from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.services.auth import issue_session
from app.services.virtual_trading.intelligent import account as iacc
from tests.factories import make_user


async def _no_marks(_client: Any, _symbols: list[str]) -> dict[str, Any]:
    """假 marks(无活 CH)· 返空 → 浮盈 None · 持仓仍出现(隔离测试只关心哪些仓出现)。"""
    return {}


@pytest.fixture(autouse=True)
def _ch_override():  # noqa: ANN202
    # status/positions 走 ClickHouseDep · 测试无 lifespan → 假 holder(无活仓时不触发 fetch)。
    app.dependency_overrides[get_clickhouse] = lambda: SimpleNamespace(_client=object())
    yield
    app.dependency_overrides.pop(get_clickhouse, None)


async def _platinum_headers(db: AsyncSession, **overrides: Any) -> tuple[Any, dict[str, str]]:
    user = await make_user(db, is_platinum=True, **overrides)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return user, {"Authorization": f"Bearer {token}"}


# ── ① 鉴权门:非铂金 403 · 未登录 401 ──────────────────────────────────
@pytest.mark.asyncio
async def test_non_platinum_403(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session, role="user")  # 登录但非铂金
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()
    r = await client.get(
        "/api/v1/platinum/intelligent/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "需铂金权限"  # ★明确文案(Hans 定)


@pytest.mark.asyncio
async def test_unauthenticated_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/platinum/intelligent/status")
    assert r.status_code == 401


# ── ② per-user 开关隔离:A toggle 不影响 B ─────────────────────────────
@pytest.mark.asyncio
async def test_toggle_isolated_per_user(client: AsyncClient, db_session: AsyncSession) -> None:
    _a, ha = await _platinum_headers(db_session)
    _b, hb = await _platinum_headers(db_session)
    # A 开自己的智能开关
    r = await client.post(
        "/api/v1/platinum/intelligent/toggle", json={"enabled": True}, headers=ha)
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    assert r.json()["account_ready"] is True  # ★开则幂等建自己的影子账户
    # ★B 的开关不受影响(per-user key={uid} 隔离)
    rb = await client.get("/api/v1/platinum/intelligent/status", headers=hb)
    assert rb.status_code == 200
    assert rb.json()["enabled"] is False
    # A 自己再查仍 True
    ra = await client.get("/api/v1/platinum/intelligent/status", headers=ha)
    assert ra.json()["enabled"] is True


@pytest.mark.asyncio
async def test_managed_toggle_isolated_per_user(client: AsyncClient, db_session: AsyncSession) -> None:
    _a, ha = await _platinum_headers(db_session)
    _b, hb = await _platinum_headers(db_session)
    r = await client.post(
        "/api/v1/platinum/managed/toggle", json={"enabled": True}, headers=ha)
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    rb = await client.get("/api/v1/platinum/managed/status", headers=hb)
    assert rb.json()["enabled"] is False  # ★B 不受影响


# ── ③ 看板隔离:A 看不到 B 的影子仓 ───────────────────────────────────
@pytest.mark.asyncio
async def test_positions_isolated_cannot_see_others(
    client: AsyncClient, db_session: AsyncSession, monkeypatch,  # noqa: ANN001
) -> None:
    monkeypatch.setattr(platinum_self, "select_premium_index_marks", _no_marks)  # 无活 CH
    _a, ha = await _platinum_headers(db_session)
    b_user, _hb = await _platinum_headers(db_session)
    # 在 B 的影子账户建一仓
    b_acc = await iacc.ensure_intelligent_account_for_user(db_session, b_user.id)
    db_session.add(VirtualPerpPosition(
        account_id=b_acc.id, symbol="BTCUSDT", side=PerpSide.LONG,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal("100"), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        intelligent=True,
    ))
    await db_session.commit()
    # ★A 的 token 查活仓 → 看不到 B 的仓(account_id 收窄到 A 自己的影子账户)
    r = await client.get("/api/v1/platinum/intelligent/positions", headers=ha)
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["total"] == 0
    # B 自己查得到(双确认隔离方向正确)
    b_token = (await _bearer(db_session, b_user))["Authorization"]
    rb = await client.get(
        "/api/v1/platinum/intelligent/positions",
        headers={"Authorization": b_token},
    )
    assert rb.json()["total"] == 1


async def _bearer(db: AsyncSession, user: Any) -> dict[str, str]:
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


# ── ④ OpenAPI 签名层杜绝越权:/platinum 路径/参数无 user_id(纯静态·本地可跑)──
def test_openapi_platinum_paths_have_no_user_id() -> None:
    schema = app.openapi()
    plat_paths = {p: item for p, item in schema["paths"].items() if "/platinum/" in p}
    assert plat_paths, "应有 /platinum 自助路径"
    for path, item in plat_paths.items():
        assert "{user_id}" not in path  # ★path 无 user_id
        for method in item.values():
            if not isinstance(method, dict):
                continue
            for param in method.get("parameters", []):
                assert param.get("name") != "user_id"  # ★query/path 参数无 user_id
    # toggle body 只有 enabled(IntelligentToggleIn/ManagedToggleIn)· 无 user_id → 结构上 A 指定不了 B
