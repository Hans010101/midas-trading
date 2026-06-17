"""管理员用户详情聚合 API pytest(用户管理刀3a · 纯只读)。

★ 重点:聚合各字段(基础/会员/额度/邀请/兑换)· AdminDep 403 · 404 · 纯只读(无写端点)。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.redeem_code import RedeemCode
from app.models.subscription import Subscription
from app.services.auth import issue_session
from app.services.growth import attribute_invite, get_or_create_invite_code
from app.services.membership import quota_key
from tests.factories import make_user


async def _admin_headers(db: AsyncSession) -> dict[str, str]:
    admin = await make_user(db, role="admin")
    token = await issue_session(db, user_id=admin.id)
    await db.commit()
    return {"Authorization": f"Bearer {token}"}


# ===== 403 / 404 =====


@pytest.mark.asyncio
async def test_detail_unauthenticated_401(client: AsyncClient, db_session: AsyncSession):
    target = await make_user(db_session)
    await db_session.commit()
    r = await client.get(f"/api/v1/admin/users/{target.id}")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_detail_normal_user_403(client: AsyncClient, db_session: AsyncSession):
    target = await make_user(db_session)
    token = await issue_session(db_session, user_id=target.id)  # 普通用户自己
    await db_session.commit()
    r = await client.get(
        f"/api/v1/admin/users/{target.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_detail_not_found_404(client: AsyncClient, db_session: AsyncSession):
    headers = await _admin_headers(db_session)
    import uuid

    r = await client.get(f"/api/v1/admin/users/{uuid.uuid4()}", headers=headers)
    assert r.status_code == 404
    # 非法 uuid 也 404(非 500)
    r2 = await client.get("/api/v1/admin/users/not-a-uuid", headers=headers)
    assert r2.status_code == 404


# ===== 聚合字段 =====


@pytest.mark.asyncio
async def test_detail_aggregates_all_fields(client: AsyncClient, db_session: AsyncSession):
    headers = await _admin_headers(db_session)
    now = datetime.now(UTC)

    # 目标用户:pro 订阅(source=redeem)+ 邀请码 + 邀过 1 人 + 兑换过 1 码
    target = await make_user(db_session)
    db_session.add(Subscription(
        user_id=target.id, plan="pro", status="active", source="redeem",
        expires_at=now + timedelta(days=200),
    ))
    code = await get_or_create_invite_code(db_session, target)
    invitee = await make_user(db_session)
    await attribute_invite(db_session, invitee.id, code)  # target 邀了 invitee(pending)
    db_session.add(RedeemCode(
        code="DETAILCODE01", period="month", days=30,
        expires_at=now + timedelta(days=300),
        redeemed_by=target.id, redeemed_at=now,
    ))
    await db_session.commit()

    # 今日额度计数塞 Redis
    redis_key = quota_key(target.id, "diagnose")
    from app.core.redis_client import get_redis

    await (await get_redis()).set(redis_key, 3, ex=3600)

    r = await client.get(f"/api/v1/admin/users/{target.id}", headers=headers)
    assert r.status_code == 200
    b = r.json()
    # 基础
    assert b["email"] == target.email
    assert b["email_verified"] is True
    # 会员
    assert b["plan"] == "pro"
    assert b["plan_status"] == "active"
    assert b["plan_source"] == "redeem"
    assert b["plan_expires_at"] is not None
    # 额度(diagnose 用了 3,pro 月 limit 300)
    by_feat = {q["feature"]: q for q in b["quota"]}
    assert by_feat["diagnose"]["used"] == 3
    assert by_feat["diagnose"]["limit"] == 300  # noqa: PLR2004 — pro diagnose 月额度
    assert by_feat["backtest"]["limit"] == 150  # noqa: PLR2004 — pro backtest 月额度
    # 邀请
    assert b["invite_code"] == code
    assert b["invited_count"] == 1
    assert b["rewarded_count"] == 0  # invitee 未验证兑现
    # 兑换
    assert len(b["redeemed"]) == 1
    assert b["redeemed"][0]["code"] == "DETAILCODE01"
    assert b["redeemed"][0]["period"] == "month"


@pytest.mark.asyncio
async def test_detail_free_user_defaults(client: AsyncClient, db_session: AsyncSession):
    """无订阅 → free + plan_* null + 额度 free 档 + 邀请/兑换空。"""
    headers = await _admin_headers(db_session)
    target = await make_user(db_session)
    await db_session.commit()
    r = await client.get(f"/api/v1/admin/users/{target.id}", headers=headers)
    b = r.json()
    assert b["plan"] == "free"
    assert b["plan_status"] is None
    assert b["plan_expires_at"] is None
    by_feat = {q["feature"]: q for q in b["quota"]}
    assert by_feat["diagnose"]["limit"] == 5  # noqa: PLR2004 — free diagnose 月额度
    assert b["invited_count"] == 0
    assert b["redeemed"] == []


# ===== ★ 纯只读:本刀 /admin/users/{id} 仅 GET(机器扫描)=====


def test_user_detail_route_is_get_only():
    from app.main import app

    methods: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if path == "/api/v1/admin/users/{user_id}":
            methods |= getattr(route, "methods", set()) or set()
    # 只读:仅 GET(+ 框架自动 HEAD)· 无 POST/PUT/PATCH/DELETE
    assert methods <= {"GET", "HEAD"}
    assert "GET" in methods
    assert not (methods & {"POST", "PUT", "PATCH", "DELETE"})
