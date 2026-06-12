"""管理员 · 用户管理 API(用户管理刀1 · 纯只读)。

🔴 安全边界:每个端点必挂 AdminDep(后端 403 强制)—— 前端藏菜单/middleware
   只是 UX 层,不是边界。新增端点时 AdminDep 一个不许漏(pytest 403 矩阵钉死)。
🔴 红线:本文件零写操作 · 交易链路零碰。

口径说明:
- last_active_7d:该用户未过期 session 的 MAX(last_used_at)。session 是 7 天
  滚动 TTL(过期即不算),所以「最后活跃」只覆盖最近 7 天,更早 → null。
- active_sessions:未过期 session 数(≈ 在线设备数,上限 5)。
- register_method:由 google_sub / password_hash 非空推导(google|password|both)。
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep
from app.core.database import get_db
from app.models.session import Session
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


class AdminUserItem(BaseModel):
    id: str
    email: str
    role: str
    created_at: datetime
    email_verified: bool
    register_method: str  # google | password | both
    last_active_7d: datetime | None
    active_sessions: int


class AdminUserListOut(BaseModel):
    items: list[AdminUserItem]
    total: int
    page: int
    page_size: int


def _register_method(google_sub: str | None, password_hash: str | None) -> str:
    if google_sub is not None and password_hash is not None:
        return "both"
    return "google" if google_sub is not None else "password"


@router.get("/users", response_model=AdminUserListOut)
async def list_users(
    _admin: AdminDep,
    db: DbDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AdminUserListOut:
    """用户列表(分页 · created_at desc)· session 聚合一条 outerjoin 防 N+1。"""
    now = datetime.now(UTC)
    # 未过期 session 按 user 聚合(7 天滚动 TTL → last_active 天然 7d 口径)
    sess_agg = (
        select(
            Session.user_id,
            func.max(Session.last_used_at).label("last_active"),
            func.count(Session.id).label("session_count"),
        )
        .where(Session.expires_at > now)
        .group_by(Session.user_id)
        .subquery()
    )

    rows = (
        await db.execute(
            select(User, sess_agg.c.last_active, sess_agg.c.session_count)
            .outerjoin(sess_agg, sess_agg.c.user_id == User.id)
            .order_by(User.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size),
        )
    ).all()
    total = (await db.execute(select(func.count()).select_from(User))).scalar_one()

    return AdminUserListOut(
        items=[
            AdminUserItem(
                id=str(u.id),
                email=u.email,
                role=u.role,
                created_at=u.created_at,
                email_verified=u.email_verified_at is not None,
                register_method=_register_method(u.google_sub, u.password_hash),
                last_active_7d=last_active,
                active_sessions=session_count or 0,
            )
            for u, last_active, session_count in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
