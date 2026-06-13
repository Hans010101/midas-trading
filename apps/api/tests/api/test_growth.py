"""Phase 1.5 刀A · 试用 + 邀请体系 pytest。

★ 重点:linking 老用户不送不归因(G 调研陷阱)· created 三分支矩阵 ·
三态累加 + 90 天封顶边界 · 兑现幂等(rowcount)· 双向到账 · 试用只发一次。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invitation import Invitation
from app.models.subscription import Subscription
from app.services.auth import find_or_create_oauth_user, issue_session
from app.services.growth import (
    attribute_invite,
    extend_subscription,
    get_or_create_invite_code,
    grant_trial_if_eligible,
    redeem_invite_if_pending,
)
from app.services.membership import resolve_plan
from tests.factories import make_user, random_email

# ===== extend_subscription 三态 + 90 天封顶 =====


@pytest.mark.asyncio
async def test_extend_no_row_insert(db_session: AsyncSession):
    user = await make_user(db_session)
    exp = await extend_subscription(db_session, user.id, 7, "trial")
    assert exp is not None
    sub = await db_session.scalar(select(Subscription).where(Subscription.user_id == user.id))
    assert sub is not None
    assert sub.plan == "pro"
    assert sub.status == "active"
    assert abs((sub.expires_at - datetime.now(UTC)).days - 7) <= 1


@pytest.mark.asyncio
async def test_extend_active_accumulates(db_session: AsyncSession):
    """有效行累加:试用 7 天内被邀 → 7+15=22 天连续。"""
    user = await make_user(db_session)
    await extend_subscription(db_session, user.id, 7, "trial")
    exp2 = await extend_subscription(db_session, user.id, 15, "invite", cap_days=90)
    assert exp2 is not None
    assert abs((exp2 - datetime.now(UTC)).days - 22) <= 1


@pytest.mark.asyncio
async def test_extend_expired_restarts_from_now(db_session: AsyncSession):
    """过期行从 now 起算(过期部分不补)。"""
    user = await make_user(db_session)
    db_session.add(Subscription(
        user_id=user.id, plan="pro", status="active", source="trial",
        expires_at=datetime.now(UTC) - timedelta(days=30),
    ))
    await db_session.flush()
    exp = await extend_subscription(db_session, user.id, 15, "invite", cap_days=90)
    assert exp is not None
    assert abs((exp - datetime.now(UTC)).days - 15) <= 1


@pytest.mark.asyncio
async def test_extend_cap_90_boundary(db_session: AsyncSession):
    """★ 封顶边界:剩 80 天再兑 15 → 只到 90(不是 95);已满 90 → None 零增量。"""
    user = await make_user(db_session)
    now = datetime.now(UTC)
    db_session.add(Subscription(
        user_id=user.id, plan="pro", status="active", source="invite",
        expires_at=now + timedelta(days=80),
    ))
    await db_session.flush()
    exp = await extend_subscription(db_session, user.id, 15, "invite", cap_days=90)
    assert exp is not None
    assert abs((exp - now).days - 90) <= 1  # 80+15 截断到 90

    # 已达封顶 → 再兑零增量(None · 调用方不展示"获赠")
    exp2 = await extend_subscription(db_session, user.id, 15, "invite", cap_days=90)
    assert exp2 is None

    # trial 不受 cap 参数约束(不传 cap)
    exp3 = await extend_subscription(db_session, user.id, 7, "trial")
    assert exp3 is not None


# ===== 试用只发一次 + 与 quota 联动 =====


@pytest.mark.asyncio
async def test_trial_only_once(db_session: AsyncSession):
    user = await make_user(db_session)
    assert await grant_trial_if_eligible(db_session, user.id) is True
    assert await grant_trial_if_eligible(db_session, user.id) is False  # 行已存在不再发


@pytest.mark.asyncio
async def test_trial_makes_plan_pro_and_quota_100(db_session: AsyncSession):
    """试用期内 plan=pro → diagnose 限额走 100(quota 与 plan 联动)。"""
    from app.services.membership import PLAN_QUOTAS

    user = await make_user(db_session)
    await grant_trial_if_eligible(db_session, user.id)
    plan = await resolve_plan(db_session, user.id)
    assert plan == "pro"
    assert PLAN_QUOTAS[plan]["diagnose"] == 100


# ===== 归因:无效码静默 / 正常归因 =====


@pytest.mark.asyncio
async def test_attribute_invalid_code_silent(db_session: AsyncSession):
    invitee = await make_user(db_session)
    await attribute_invite(db_session, invitee.id, "NOEXIST1")  # 不抛
    await attribute_invite(db_session, invitee.id, None)
    await attribute_invite(db_session, invitee.id, "")
    rows = (await db_session.execute(
        select(Invitation).where(Invitation.invitee_id == invitee.id),
    )).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_attribute_and_redeem_both_sides(db_session: AsyncSession):
    """正常归因 + 兑现:双向各 +15d · invitee 含 trial 7d = 22d。"""
    inviter = await make_user(db_session)
    code = await get_or_create_invite_code(db_session, inviter)
    invitee = await make_user(db_session)

    await attribute_invite(db_session, invitee.id, code.lower())  # 大小写归一
    row = await db_session.scalar(
        select(Invitation).where(Invitation.invitee_id == invitee.id),
    )
    assert row is not None
    assert row.rewarded_at is None  # pending

    # 模拟 verify 流程顺序:trial 先 → redeem 后
    assert await grant_trial_if_eligible(db_session, invitee.id) is True
    assert await redeem_invite_if_pending(db_session, invitee.id) is True

    now = datetime.now(UTC)
    sub_invitee = await db_session.scalar(
        select(Subscription).where(Subscription.user_id == invitee.id),
    )
    sub_inviter = await db_session.scalar(
        select(Subscription).where(Subscription.user_id == inviter.id),
    )
    assert abs((sub_invitee.expires_at - now).days - 22) <= 1  # 7 trial + 15 invite
    assert abs((sub_inviter.expires_at - now).days - 15) <= 1  # 邀请方无 trial


@pytest.mark.asyncio
async def test_redeem_idempotent_rowcount(db_session: AsyncSession):
    """★ 兑现幂等:二次 redeem rowcount=0 → False · 不重复加天。"""
    inviter = await make_user(db_session)
    code = await get_or_create_invite_code(db_session, inviter)
    invitee = await make_user(db_session)
    await attribute_invite(db_session, invitee.id, code)

    assert await redeem_invite_if_pending(db_session, invitee.id) is True
    exp_after_first = (await db_session.scalar(
        select(Subscription).where(Subscription.user_id == inviter.id),
    )).expires_at

    assert await redeem_invite_if_pending(db_session, invitee.id) is False  # 幂等
    exp_after_second = (await db_session.scalar(
        select(Subscription).where(Subscription.user_id == inviter.id),
    )).expires_at
    assert exp_after_first == exp_after_second  # 天数没变


@pytest.mark.asyncio
async def test_redeem_without_attribution_noop(db_session: AsyncSession):
    user = await make_user(db_session)
    assert await redeem_invite_if_pending(db_session, user.id) is False


# ===== ★ Google created 三分支矩阵(G 调研陷阱钉死)=====


@pytest.mark.asyncio
async def test_oauth_created_matrix(db_session: AsyncSession):
    """分支1 sub命中→False · 分支2 email linking→False(陷阱)· 分支3 新建→True。"""
    # 分支 3:全新 → created=True
    u3, created3 = await find_or_create_oauth_user(
        db_session, google_sub="sub-new-1", email=random_email(),
    )
    assert created3 is True

    # 分支 1:同 sub 再来 → created=False
    u1, created1 = await find_or_create_oauth_user(
        db_session, google_sub="sub-new-1", email=u3.email,
    )
    assert created1 is False
    assert u1.id == u3.id

    # 分支 2(★陷阱):邮箱注册的老用户首次 Google 登录(linking)→ created=False
    old = await make_user(db_session)  # password 用户 · 无 google_sub
    u2, created2 = await find_or_create_oauth_user(
        db_session, google_sub="sub-link-1", email=old.email,
    )
    assert created2 is False
    assert u2.id == old.id
    # linking 老用户绝不送试用(主张:created 标志是唯一判据)
    assert await db_session.scalar(
        select(Subscription).where(Subscription.user_id == old.id),
    ) is None


# ===== 端点级:register ref 归因 + verify 兑现感知 + invite/me =====


@pytest.mark.asyncio
async def test_register_with_ref_then_verify_rewards(
    client: AsyncClient, db_session: AsyncSession,
):
    """全链路:带 ref 注册 → verify → trial+invite 双标志 + 双方到账。"""
    from app.models.verification_token import VerificationToken  # noqa: F401
    from app.services.auth import create_verification_token  # noqa: F401

    inviter = await make_user(db_session)
    code = await get_or_create_invite_code(db_session, inviter)
    await db_session.commit()

    email = random_email()
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email, "password": "testpass1234",
            "age_confirmed": True, "ref": code,
        },
    )
    assert r.status_code == 201

    # 取验证 token(测试侧直查 DB · 同 test_auth 范式)
    from app.models.user import User

    new_user = await db_session.scalar(select(User).where(User.email == email))
    token_row = await db_session.scalar(
        select(VerificationToken).where(VerificationToken.user_id == new_user.id),
    )
    rv = await client.post("/api/v1/auth/verify", json={"token": token_row.token})
    assert rv.status_code == 200
    body = rv.json()
    assert body["trial_granted"] is True
    assert body["invite_rewarded"] is True

    plan = await resolve_plan(db_session, new_user.id)
    assert plan == "pro"


@pytest.mark.asyncio
async def test_invite_me_lazy_code_and_stats(client: AsyncClient, db_session: AsyncSession):
    user = await make_user(db_session)
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}

    r1 = await client.get("/api/v1/invite/me", headers=headers)
    assert r1.status_code == 200
    body = r1.json()
    assert len(body["code"]) == 8
    assert body["invite_url"].endswith(f"/register?ref={body['code']}")
    assert body["invited_count"] == 0
    assert body["rewarded_count"] == 0
    assert body["earned_days"] == 0

    # 二次访问码不变(lazy 只生成一次)
    r2 = await client.get("/api/v1/invite/me", headers=headers)
    assert r2.json()["code"] == body["code"]

    # 未登录 401
    assert (await client.get("/api/v1/invite/me")).status_code == 401
