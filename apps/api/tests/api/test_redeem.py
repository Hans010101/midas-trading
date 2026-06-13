"""兑换码模块刀1 · pytest。

★ 重点:生成(唯一/period→days/expires+1年/AdminDep 403)· 兑换幂等(rowcount)·
4xx 各态(不存在/已用/过期)· 不封顶(对比 invite 封顶)· source='redeem' · plan=pro 联动 ·
🔴 红线:兑换码 import 树不含 engine。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.redeem_code import RedeemCode
from app.models.subscription import Subscription
from app.services.auth import issue_session
from app.services.membership import PERIOD_DAYS, resolve_plan
from app.services.redeem import generate_codes, redeem
from tests.factories import make_user


async def _headers(db: AsyncSession, *, role: str = "user") -> tuple[Any, dict[str, str]]:
    user = await make_user(db, role=role)
    token = await issue_session(db, user_id=user.id)
    await db.commit()
    return user, {"Authorization": f"Bearer {token}"}


# ===== 生成(管理员)=====


@pytest.mark.asyncio
async def test_generate_unique_and_days_and_expiry(db_session: AsyncSession):
    admin = await make_user(db_session, role="admin")
    rows = await generate_codes(db_session, admin_id=admin.id, period="quarter", count=5, note="赠送批次")
    codes = [r.code for r in rows]
    assert len(codes) == 5
    assert len(set(codes)) == 5  # 全唯一
    assert all(len(c) == 12 for c in codes)  # Crockford 12 位
    assert all(r.days == PERIOD_DAYS["quarter"] == 90 for r in rows)
    now = datetime.now(UTC)
    assert all(abs((r.expires_at - now).days - 365) <= 1 for r in rows)  # +1 年
    assert all(r.created_by == admin.id and r.note == "赠送批次" for r in rows)


@pytest.mark.asyncio
async def test_generate_period_days_mapping(db_session: AsyncSession):
    admin = await make_user(db_session, role="admin")
    for period, days in (("month", 30), ("quarter", 90), ("year", 365)):
        rows = await generate_codes(db_session, admin_id=admin.id, period=period, count=1)
        assert rows[0].days == days


@pytest.mark.asyncio
async def test_admin_generate_endpoint_403_matrix(client: AsyncClient, db_session: AsyncSession):
    # 未登录 401
    r0 = await client.post("/api/v1/admin/redeem-codes", json={"period": "month", "count": 2})
    assert r0.status_code == 401
    # 普通用户 403
    _u, uh = await _headers(db_session, role="user")
    r1 = await client.post("/api/v1/admin/redeem-codes", headers=uh, json={"period": "month", "count": 2})
    assert r1.status_code == 403
    # admin 200 + 返回 2 个码
    _a, ah = await _headers(db_session, role="admin")
    r2 = await client.post("/api/v1/admin/redeem-codes", headers=ah, json={"period": "month", "count": 2})
    assert r2.status_code == 200
    body = r2.json()
    assert len(body["codes"]) == 2
    assert body["days"] == 30


@pytest.mark.asyncio
async def test_admin_generate_count_bounds_422(client: AsyncClient, db_session: AsyncSession):
    _a, ah = await _headers(db_session, role="admin")
    assert (await client.post("/api/v1/admin/redeem-codes", headers=ah, json={"period": "month", "count": 0})).status_code == 422
    assert (await client.post("/api/v1/admin/redeem-codes", headers=ah, json={"period": "month", "count": 101})).status_code == 422


# ===== 兑换(登录用户)=====


async def _one_code(db: AsyncSession, admin_id: Any, period: str = "year") -> str:
    rows = await generate_codes(db, admin_id=admin_id, period=period, count=1)
    await db.commit()
    return rows[0].code


@pytest.mark.asyncio
async def test_redeem_success_opens_pro(client: AsyncClient, db_session: AsyncSession):
    admin = await make_user(db_session, role="admin")
    code = await _one_code(db_session, admin.id, "year")
    user, uh = await _headers(db_session, role="user")
    r = await client.post("/api/v1/redeem", headers=uh, json={"code": code})
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "pro"
    assert body["days_added"] == 365
    # plan 联动
    assert await resolve_plan(db_session, user.id) == "pro"


@pytest.mark.asyncio
async def test_redeem_idempotent_rowcount(client: AsyncClient, db_session: AsyncSession):
    """★ 同码二次兑换 → 第二次 409 且不重复开权益(天数不变)。"""
    admin = await make_user(db_session, role="admin")
    code = await _one_code(db_session, admin.id, "month")
    user, uh = await _headers(db_session, role="user")

    r1 = await client.post("/api/v1/redeem", headers=uh, json={"code": code})
    assert r1.status_code == 200
    exp1 = (await db_session.scalar(
        select(Subscription).where(Subscription.user_id == user.id),
    )).expires_at

    r2 = await client.post("/api/v1/redeem", headers=uh, json={"code": code})
    assert r2.status_code == 409
    assert r2.json()["detail"]["error"] == "already_used"
    exp2 = (await db_session.scalar(
        select(Subscription).where(Subscription.user_id == user.id),
    )).expires_at
    assert exp1 == exp2  # 天数没变


@pytest.mark.asyncio
async def test_redeem_4xx_states(client: AsyncClient, db_session: AsyncSession):
    """各态结构化:不存在 404 / 已过期 410 / 已被他人兑换 409。"""
    admin = await make_user(db_session, role="admin")
    _u, uh = await _headers(db_session, role="user")

    # 不存在
    rn = await client.post("/api/v1/redeem", headers=uh, json={"code": "NOTAREALCODE"})
    assert rn.status_code == 404
    assert rn.json()["detail"]["error"] == "not_found"

    # 已过期(直接造一条过期码)
    expired = RedeemCode(
        code="EXPIRED00000", period="year", days=365, created_by=admin.id,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(expired)
    await db_session.commit()
    re = await client.post("/api/v1/redeem", headers=uh, json={"code": "EXPIRED00000"})
    assert re.status_code == 410
    assert re.json()["detail"]["error"] == "expired"

    # 已被他人兑换
    other = await make_user(db_session)
    used = RedeemCode(
        code="USEDBYOTHER0", period="year", days=365, created_by=admin.id,
        expires_at=datetime.now(UTC) + timedelta(days=365),
        redeemed_by=other.id, redeemed_at=datetime.now(UTC),
    )
    db_session.add(used)
    await db_session.commit()
    ru = await client.post("/api/v1/redeem", headers=uh, json={"code": "USEDBYOTHER0"})
    assert ru.status_code == 409
    assert ru.json()["detail"]["error"] == "already_used"


@pytest.mark.asyncio
async def test_redeem_not_capped_unlike_invite(client: AsyncClient, db_session: AsyncSession):
    """★ 不封顶:已有长期 sub(剩 300 天)再兑年卡 → 纯累加到 ~665 天(对比 invite 90 封顶)。"""
    admin = await make_user(db_session, role="admin")
    code = await _one_code(db_session, admin.id, "year")
    user, uh = await _headers(db_session, role="user")
    now = datetime.now(UTC)
    db_session.add(Subscription(
        user_id=user.id, plan="pro", status="active", source="paid",
        expires_at=now + timedelta(days=300),
    ))
    await db_session.commit()

    r = await client.post("/api/v1/redeem", headers=uh, json={"code": code})
    assert r.status_code == 200
    sub = await db_session.scalar(select(Subscription).where(Subscription.user_id == user.id))
    assert abs((sub.expires_at - now).days - 665) <= 1  # 300 + 365,无 90 封顶
    assert sub.source == "redeem"


@pytest.mark.asyncio
async def test_redeem_case_insensitive(client: AsyncClient, db_session: AsyncSession):
    admin = await make_user(db_session, role="admin")
    code = await _one_code(db_session, admin.id, "month")
    _u, uh = await _headers(db_session, role="user")
    r = await client.post("/api/v1/redeem", headers=uh, json={"code": f"  {code.lower()}  "})
    assert r.status_code == 200  # trim + 大写归一


# ===== 服务层兑换幂等(并发竞态点直测)=====


@pytest.mark.asyncio
async def test_service_redeem_second_call_raises_used(db_session: AsyncSession):
    from app.services.redeem import RedeemAlreadyUsed

    admin = await make_user(db_session, role="admin")
    rows = await generate_codes(db_session, admin_id=admin.id, period="month", count=1)
    await db_session.commit()
    user = await make_user(db_session)
    await db_session.commit()

    days_added, _exp = await redeem(db_session, user_id=user.id, code=rows[0].code)
    assert days_added == 30
    with pytest.raises(RedeemAlreadyUsed):
        await redeem(db_session, user_id=user.id, code=rows[0].code)


# ===== 🔴 红线:兑换码域 import 树不含 engine(机器扫描)=====


def test_redeem_domain_does_not_import_engine():
    """兑换开的是会员权益,绝不碰交易引擎 —— 递归扫 redeem service/api 的 import 闭包。"""
    import importlib

    seen: set[str] = set()
    banned = ("engine", "virtual_trading", "matching")

    def walk(modname: str) -> None:
        if modname in seen:
            return
        seen.add(modname)
        try:
            mod = importlib.import_module(modname)
        except Exception:  # noqa: BLE001
            return
        src_file = getattr(mod, "__file__", None)
        if not src_file or "/app/" not in src_file:
            return  # 只走项目内模块
        import ast
        from pathlib import Path

        tree = ast.parse(Path(src_file).read_text())
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                low = n.lower()
                assert not any(b in low for b in banned), f"{modname} imports banned: {n}"
                if n.startswith("app."):
                    walk(n)

    walk("app.services.redeem")
    walk("app.api.v1.redeem")
