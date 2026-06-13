"""兑换码 API · 兑换码模块刀1。

- POST /admin/redeem-codes  · 批量生成(AdminDep)
- GET  /admin/redeem-codes  · 分页列表(AdminDep · redeemed_by outerjoin 防 N+1)
- POST /redeem              · 兑换(CurrentUserDep · 任意登录用户)

🔴 AdminDep 是管理端唯一边界(后端 403);兑换码域不 import engine。
"""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep, CurrentUserDep
from app.core.database import get_db
from app.models.redeem_code import RedeemCode
from app.models.user import User
from app.services.redeem import (
    MAX_BATCH,
    RedeemError,
    count_codes,
    derive_status,
    generate_codes,
    redeem,
)

router = APIRouter(tags=["redeem"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


# ── 管理员:生成 ─────────────────────────────────────────────────────────


class GenerateIn(BaseModel):
    period: Literal["month", "quarter", "year"]
    count: int = Field(ge=1, le=MAX_BATCH)
    note: str | None = Field(default=None, max_length=128)


class GenerateOut(BaseModel):
    codes: list[str]
    period: str
    days: int


@router.post("/admin/redeem-codes", response_model=GenerateOut)
async def admin_generate(payload: GenerateIn, _admin: AdminDep, db: DbDep) -> GenerateOut:
    # _admin 是 AdminDep 解析出的 User(含 id)· 记 created_by
    rows = await generate_codes(
        db, admin_id=_admin.id, period=payload.period, count=payload.count, note=payload.note,
    )
    await db.commit()
    return GenerateOut(codes=[r.code for r in rows], period=payload.period, days=rows[0].days)


# ── 管理员:列表 ─────────────────────────────────────────────────────────


class RedeemCodeItem(BaseModel):
    code: str
    period: str
    status: str  # unused | redeemed | expired(派生)
    note: str | None
    redeemed_by_email: str | None
    created_at: datetime
    expires_at: datetime


class RedeemCodeListOut(BaseModel):
    items: list[RedeemCodeItem]
    total: int
    page: int
    page_size: int


@router.get("/admin/redeem-codes", response_model=RedeemCodeListOut)
async def admin_list(
    _admin: AdminDep,
    db: DbDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RedeemCodeListOut:
    now = datetime.now(UTC)
    # redeemed_by → email outerjoin(防 N+1)· created_at desc + id tie-break(分页稳定)
    rows = (
        await db.execute(
            select(RedeemCode, User.email)
            .outerjoin(User, User.id == RedeemCode.redeemed_by)
            .order_by(RedeemCode.created_at.desc(), RedeemCode.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size),
        )
    ).all()
    total = await count_codes(db)
    return RedeemCodeListOut(
        items=[
            RedeemCodeItem(
                code=rc.code,
                period=rc.period,
                status=derive_status(rc.redeemed_at, rc.expires_at, now),
                note=rc.note,
                redeemed_by_email=email,
                created_at=rc.created_at,
                expires_at=rc.expires_at,
            )
            for rc, email in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── 用户:兑换 ───────────────────────────────────────────────────────────


class RedeemIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class RedeemOut(BaseModel):
    plan: str
    days_added: int
    expires_at: datetime | None


@router.post("/redeem", response_model=RedeemOut)
async def redeem_endpoint(payload: RedeemIn, current_user: CurrentUserDep, db: DbDep) -> RedeemOut:
    try:
        days_added, expires_at = await redeem(db, user_id=current_user.id, code=payload.code)
    except RedeemError as e:
        # 各态结构化 detail(前端友好:not_found / already_used / expired)
        raise HTTPException(
            status_code=e.http_status,
            detail={"error": e.code, "message": str(e)},
        ) from e
    return RedeemOut(plan="pro", days_added=days_added, expires_at=expires_at)
