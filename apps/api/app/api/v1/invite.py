"""GET /invite/me · 我的邀请(Phase 1.5 刀A)。

lazy 生成邀请码(首次访问 · 存量用户零回填)+ 链接 + 统计。
"""

import os
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.core.database import get_db
from app.services.growth import INVITE_DAYS, get_or_create_invite_code, invite_stats

router = APIRouter(prefix="/invite", tags=["invite"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


class InviteMeOut(BaseModel):
    code: str
    invite_url: str
    invited_count: int
    rewarded_count: int
    # 累计获赠 = 兑现数 × 15(如实算术 · 封顶截断不反映在此,以 subscription 为准)
    earned_days: int


@router.get("/me", response_model=InviteMeOut)
async def invite_me(current_user: CurrentUserDep, db: DbDep) -> InviteMeOut:
    code = await get_or_create_invite_code(db, current_user)
    await db.commit()  # lazy 生成的码落库
    invited, rewarded = await invite_stats(db, current_user.id)
    # 与 register 验证邮件链接同源(auth._public_base_url 的 env 口径)
    base = os.getenv("PUBLIC_WEB_URL", "http://localhost:3000").rstrip("/")
    return InviteMeOut(
        code=code,
        invite_url=f"{base}/register?ref={code}",
        invited_count=invited,
        rewarded_count=rewarded,
        earned_days=rewarded * INVITE_DAYS,
    )
