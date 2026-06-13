"""管理员手动调权益 pytest(用户管理刀3b-1 · 写操作)。

★ 重点:授予开 pro + 不封顶累加 · 审计写入(operator/target/action/detail)·
operator 取自鉴权防伪造 · 同事务回滚 · 403/404/非法天数 · 🔴 红线 import 扫描。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_action_log import AdminActionLog
from app.models.subscription import Subscription
from app.services.auth import issue_session
from app.services.membership import resolve_plan
from tests.factories import make_user


async def _admin(db: AsyncSession) -> tuple[Any, dict[str, str]]:
    admin = await make_user(db, role="admin")
    token = await issue_session(db, user_id=admin.id)
    await db.commit()
    return admin, {"Authorization": f"Bearer {token}"}


# ===== 授予 + 审计 =====


@pytest.mark.asyncio
async def test_grant_opens_pro_and_writes_audit(client: AsyncClient, db_session: AsyncSession):
    admin, headers = await _admin(db_session)
    target = await make_user(db_session)
    await db_session.commit()

    r = await client.post(
        f"/api/v1/admin/users/{target.id}/grant",
        headers=headers,
        json={"period": "year", "note": "VIP 客户"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "pro"
    assert body["days_added"] == 365
    assert await resolve_plan(db_session, target.id) == "pro"

    # 审计:operator=admin / target / action / detail
    log = await db_session.scalar(
        select(AdminActionLog).where(AdminActionLog.target_user_id == target.id),
    )
    assert log is not None
    assert log.operator_id == admin.id
    assert log.action == "grant_pro"
    assert log.detail["days"] == 365
    assert log.detail["note"] == "VIP 客户"


@pytest.mark.asyncio
async def test_grant_days_direct(client: AsyncClient, db_session: AsyncSession):
    _admin_u, headers = await _admin(db_session)
    target = await make_user(db_session)
    await db_session.commit()
    r = await client.post(
        f"/api/v1/admin/users/{target.id}/grant", headers=headers, json={"days": 45},
    )
    assert r.status_code == 200
    assert r.json()["days_added"] == 45


@pytest.mark.asyncio
async def test_grant_not_capped_accumulates(client: AsyncClient, db_session: AsyncSession):
    """★ 不封顶:已有 300 天 sub 再 grant 年卡 → 665 天纯累加。"""
    _admin_u, headers = await _admin(db_session)
    target = await make_user(db_session)
    now = datetime.now(UTC)
    db_session.add(Subscription(
        user_id=target.id, plan="pro", status="active", source="paid",
        expires_at=now + timedelta(days=300),
    ))
    await db_session.commit()

    r = await client.post(
        f"/api/v1/admin/users/{target.id}/grant", headers=headers, json={"period": "year"},
    )
    assert r.status_code == 200
    sub = await db_session.scalar(select(Subscription).where(Subscription.user_id == target.id))
    assert abs((sub.expires_at - now).days - 665) <= 1  # 300 + 365 无封顶
    assert sub.source == "admin"


# ===== 防伪造:operator 取自鉴权 =====


@pytest.mark.asyncio
async def test_operator_from_auth_not_payload(client: AsyncClient, db_session: AsyncSession):
    """前端即使塞 operator_id 也被忽略 → 审计 operator = 真实鉴权 admin。"""
    admin, headers = await _admin(db_session)
    target = await make_user(db_session)
    other = await make_user(db_session)  # 试图伪造成 other
    await db_session.commit()

    r = await client.post(
        f"/api/v1/admin/users/{target.id}/grant",
        headers=headers,
        json={"days": 30, "operator_id": str(other.id), "note": "x"},  # 伪造字段被忽略
    )
    assert r.status_code == 200
    log = await db_session.scalar(
        select(AdminActionLog).where(AdminActionLog.target_user_id == target.id),
    )
    assert log.operator_id == admin.id  # 取鉴权,非伪造的 other
    assert log.operator_id != other.id


# ===== 403 / 404 / 非法天数 =====


@pytest.mark.asyncio
async def test_grant_403_non_admin(client: AsyncClient, db_session: AsyncSession):
    target = await make_user(db_session)
    token = await issue_session(db_session, user_id=target.id)
    await db_session.commit()
    r = await client.post(
        f"/api/v1/admin/users/{target.id}/grant",
        headers={"Authorization": f"Bearer {token}"},
        json={"days": 30},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_grant_401_unauth(client: AsyncClient, db_session: AsyncSession):
    target = await make_user(db_session)
    await db_session.commit()
    r = await client.post(f"/api/v1/admin/users/{target.id}/grant", json={"days": 30})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_grant_404_target_missing(client: AsyncClient, db_session: AsyncSession):
    import uuid

    _admin_u, headers = await _admin(db_session)
    r = await client.post(
        f"/api/v1/admin/users/{uuid.uuid4()}/grant", headers=headers, json={"days": 30},
    )
    assert r.status_code == 404
    # 非法 uuid 也 404
    r2 = await client.post("/api/v1/admin/users/not-uuid/grant", headers=headers, json={"days": 30})
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_grant_invalid_days(client: AsyncClient, db_session: AsyncSession):
    _admin_u, headers = await _admin(db_session)
    target = await make_user(db_session)
    await db_session.commit()
    # 0 / 超上限 → 422(schema ge/le);无 days 无 period → 422(业务校验)
    assert (await client.post(f"/api/v1/admin/users/{target.id}/grant", headers=headers, json={"days": 0})).status_code == 422
    assert (await client.post(f"/api/v1/admin/users/{target.id}/grant", headers=headers, json={"days": 99999})).status_code == 422
    assert (await client.post(f"/api/v1/admin/users/{target.id}/grant", headers=headers, json={})).status_code == 422
    assert (await client.post(f"/api/v1/admin/users/{target.id}/grant", headers=headers, json={"period": "decade"})).status_code == 422


# ===== ★ 红线:grant 写端点不碰 engine / 不碰 login(import 闭包扫描)=====


def test_admin_domain_no_engine_no_login_import():
    import ast
    import importlib
    from pathlib import Path

    seen: set[str] = set()
    banned = ("engine", "virtual_trading", "matching")
    # login 链:不得 import auth 路由模块(services.auth 的 issue_session 等是会话工具,
    # 详情/grant 不需要;这里禁的是 api.v1.auth 登录端点逻辑)
    banned_exact = ("app.api.v1.auth",)

    def walk(modname: str) -> None:
        if modname in seen:
            return
        seen.add(modname)
        try:
            mod = importlib.import_module(modname)
        except Exception:  # noqa: BLE001
            return
        src = getattr(mod, "__file__", None)
        if not src or "/app/" not in src:
            return
        tree = ast.parse(Path(src).read_text())
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                assert not any(b in n.lower() for b in banned), f"{modname} imports banned: {n}"
                assert n not in banned_exact, f"{modname} imports login route: {n}"
                if n.startswith("app."):
                    walk(n)

    walk("app.api.v1.admin")
