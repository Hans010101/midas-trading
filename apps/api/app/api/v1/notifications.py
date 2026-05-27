"""通知配置路由 · /api/v1/notifications/* · 0009 § 6 → 0025 G2a 统一 bot。

- GET  /config · 当前用户配置(未配置返默认对象 · 绑定状态 + 总开关)
- PUT  /config · 只更新总开关(Telegram 绑定经 bot 内 /start,不在此手填)
- POST /test?channel=telegram · 经统一 bot 发测试消息(需已绑定)
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.core.database import get_db
from app.models.notification import NotificationConfig
from app.schemas.notifications import (
    NotificationConfigResponse,
    NotificationConfigUpdate,
    NotificationTestResult,
    default_config_response,
    serialize_config_response,
)
from app.services.notifications.dispatcher import get_config, send_test

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get(
    "/config",
    response_model=NotificationConfigResponse,
    summary="当前用户通知配置 · 未配置返默认对象(未绑定 + 总开关 true)",
)
async def get_notification_config(
    current_user: CurrentUserDep, db: DbDep,
) -> NotificationConfigResponse:
    config = await get_config(db, current_user.id)
    if config is None:
        return default_config_response()
    return serialize_config_response(config)


@router.put(
    "/config",
    response_model=NotificationConfigResponse,
    summary="更新通知总开关(成交 / 价格异动)· None 保持原值",
)
async def update_notification_config(
    payload: NotificationConfigUpdate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> NotificationConfigResponse:
    """只更新总开关 · lazy create。Telegram 绑定经 bot 内 /start,不在此处理。"""
    config = await get_config(db, current_user.id)
    if config is None:
        config = NotificationConfig(user_id=current_user.id)
        db.add(config)

    if payload.trade_alert_enabled is not None:
        config.trade_alert_enabled = payload.trade_alert_enabled
    if payload.price_alert_enabled is not None:
        config.price_alert_enabled = payload.price_alert_enabled

    await db.commit()
    await db.refresh(config)
    return serialize_config_response(config)


@router.post(
    "/test",
    response_model=NotificationTestResult,
    summary="给统一 bot 发测试消息(需已绑定 Telegram)",
)
async def send_test_notification(
    current_user: CurrentUserDep,
    db: DbDep,
    channel: Annotated[Literal["telegram"], Query(...)] = "telegram",
) -> NotificationTestResult:
    config = await get_config(db, current_user.id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未绑定 Telegram · 请先在 bot 里 /start 绑定",
        )
    result = await send_test(config, channel)
    return NotificationTestResult(
        channel=result.channel,
        ok=result.ok,
        error=result.error,
    )
