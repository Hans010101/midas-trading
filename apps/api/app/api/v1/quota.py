"""GET /quota/me · 我的 AI 额度(会员 Phase 1 刀1 · 前端三处展示共用)。

只读自报 · 与 QuotaDep 同源口径(plan 解析 / Redis 计数 / UTC+8 reset)。
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.core.database import get_db
from app.models.subscription import Subscription
from app.services.membership import (
    PLAN_QUOTAS,
    QuotaFeature,
    get_quota_used,
    quota_reset_at,
    resolve_plan,
)

router = APIRouter(prefix="/quota", tags=["quota"])

DbDep = Annotated[AsyncSession, Depends(get_db)]

_FEATURES: tuple[QuotaFeature, ...] = ("diagnose", "backtest")


class QuotaItem(BaseModel):
    feature: str
    limit: int
    used: int


class QuotaMeOut(BaseModel):
    plan: str
    # pro 到期时间(ISO)· free / 永久 → null(profile 额度卡展示)
    plan_expires_at: str | None = None
    items: list[QuotaItem]
    reset_at: str


@router.get("/me", response_model=QuotaMeOut)
async def quota_me(current_user: CurrentUserDep, db: DbDep) -> QuotaMeOut:
    plan = await resolve_plan(db, current_user.id)
    expires_at: str | None = None
    if plan != "free":
        from sqlalchemy import select

        sub = await db.scalar(
            select(Subscription).where(Subscription.user_id == current_user.id),
        )
        if sub is not None and sub.expires_at is not None:
            expires_at = sub.expires_at.isoformat()
    items: list[QuotaItem] = []
    for feature in _FEATURES:
        try:
            used = await get_quota_used(current_user.id, feature)
        except Exception:  # noqa: BLE001 — Redis 故障自报 0(展示面 · 不阻塞)
            used = 0
        items.append(QuotaItem(feature=feature, limit=PLAN_QUOTAS[plan][feature], used=used))
    return QuotaMeOut(
        plan=plan, plan_expires_at=expires_at,
        items=items, reset_at=quota_reset_at().isoformat(),
    )
