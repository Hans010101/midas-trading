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


class LanguageIn(BaseModel):
    # 第一批仅中/英 · 范围外 → 422(pydantic pattern 校验)。
    language: str = Field(pattern="^(zh|en)$")


class LanguageOut(BaseModel):
    language: str


@router.patch("/language", response_model=LanguageOut)
async def set_language(
    payload: LanguageIn, current_user: CurrentUserDep, db: DbDep,
) -> LanguageOut:
    """设语言偏好(i18n Phase 0)· 跨设备同步层 · 前端 cookie 是即时生效层。"""
    current_user.language_pref = payload.language
    await db.commit()
    logger.info("[user.language] user_id=%s language=%s", current_user.id, payload.language)
    return LanguageOut(language=payload.language)


# ── 指标偏好(做T线后端 · 前端读它决定展示哪些分析)──────────────────────────
# ★纯偏好存储:GET/PATCH user.indicator_prefs(JSONB)· 绝不碰 boll-scan 引擎 / M1 影子 / 交易。
#   默认:布林 ON · 缠论 ON · 做T OFF(现有用户 NULL → 合并默认 · 零感知)。
# 前端(点金-3 接)据此渲染;做T 功能后续再据 day_trade 开关 gate(本刀只做偏好存取)。
_INDICATOR_DEFAULTS: dict[str, bool] = {
    "bollinger": True,   # 布林带分析(默认开)
    "chan": True,        # 缠论分析(默认开)
    "day_trade": False,  # 做T信号(默认关 · 进阶功能 · 用户显式开启)
}
_INDICATOR_KEYS = frozenset(_INDICATOR_DEFAULTS)


def _merged_prefs(stored: dict[str, bool] | None) -> dict[str, bool]:
    """存储值(可空/部分)合并到默认 · 只保留已知键(防脏数据/前端乱传)。"""
    out = dict(_INDICATOR_DEFAULTS)
    if stored:
        for k, v in stored.items():
            if k in _INDICATOR_KEYS:
                out[k] = bool(v)
    return out


class IndicatorPrefsOut(BaseModel):
    bollinger: bool
    chan: bool
    day_trade: bool


class IndicatorPrefsIn(BaseModel):
    # 全可选 · 只更新传入的键(PATCH 语义 · 部分更新)。范围外键 pydantic 忽略(extra=ignore 默认)。
    bollinger: bool | None = None
    chan: bool | None = None
    day_trade: bool | None = None


@router.get("/indicator-prefs", response_model=IndicatorPrefsOut)
async def get_indicator_prefs(current_user: CurrentUserDep) -> IndicatorPrefsOut:
    """取当前用户指标偏好 · NULL/部分 → 合并默认(布林/缠论 ON · 做T OFF)。"""
    return IndicatorPrefsOut(**_merged_prefs(current_user.indicator_prefs))


@router.patch("/indicator-prefs", response_model=IndicatorPrefsOut)
async def set_indicator_prefs(
    payload: IndicatorPrefsIn, current_user: CurrentUserDep, db: DbDep,
) -> IndicatorPrefsOut:
    """部分更新指标偏好(PATCH · 只改传入的键)· 存 JSONB · 返回合并后全量。"""
    merged = _merged_prefs(current_user.indicator_prefs)
    for k, v in payload.model_dump(exclude_none=True).items():
        if k in _INDICATOR_KEYS:
            merged[k] = bool(v)
    # ★重新赋值整个 dict(SQLAlchemy JSONB 就地改 dict 不触发脏检测 · 必须整体替换)
    current_user.indicator_prefs = dict(merged)
    await db.commit()
    logger.info("[user.indicator_prefs] user_id=%s prefs=%s", current_user.id, merged)
    return IndicatorPrefsOut(**merged)
