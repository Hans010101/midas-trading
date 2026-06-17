"""用户资料端点 · /api/v1/user/*(头像选择器骨架)。

🔴 红线:头像【零图片存储】—— 只存 avatar_id(选第几个预设)· 绝不接受/存储上传图。
身份从 CurrentUserDep(session)取 · 不碰 engine/收款/门控。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["user"])

DbDep = Annotated[AsyncSession, Depends(get_db)]

# 预设头像数 · 与前端 lib/avatars.ts AVATAR_COUNT 一致(改数量两处同步)
_AVATAR_MAX = 16


class AvatarIn(BaseModel):
    # 0 = 恢复默认首字母;1-16 = 选第 N 个预设。范围外 → 422(pydantic 校验)。
    avatar_id: int = Field(ge=0, le=_AVATAR_MAX)


class AvatarOut(BaseModel):
    avatar_id: int | None


@router.patch("/avatar", response_model=AvatarOut)
async def set_avatar(
    payload: AvatarIn, current_user: CurrentUserDep, db: DbDep,
) -> AvatarOut:
    """选预设头像(★零图片存储 · 只存编号)· 0 → NULL 恢复默认首字母圆底。"""
    stored = payload.avatar_id or None  # 0 → None(默认首字母)
    current_user.avatar_id = stored
    await db.commit()
    logger.info("[user.avatar] user_id=%s avatar_id=%s", current_user.id, stored)
    return AvatarOut(avatar_id=stored)
