"""通知配置路由 · /api/v1/notifications/* · 0009 § 6。

3 个端点:
- GET /config · 当前用户配置(未配置返默认对象 · token 截断展示)
- PUT /config · 部分更新(空字符串清空 · None 保持)
- POST /test?channel=feishu|telegram · 发送测试消息
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
    summary="当前用户通知配置 · 未配置返默认对象(全 None + 总开关 true)",
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
    summary="部分更新通知配置 · 空字符串清空 · None 保持原值",
)
async def update_notification_config(
    payload: NotificationConfigUpdate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> NotificationConfigResponse:
    """部分更新 · ORM 直接赋值(比 pg_insert ON CONFLICT 对 NULL 值更可靠)。"""
    config = await get_config(db, current_user.id)
    if config is None:
        # 首次保存 · lazy create
        config = NotificationConfig(user_id=current_user.id)
        db.add(config)

    # 部分更新 · 空字符串 → None 清空 · None 不动
    if payload.feishu_webhook_url is not None:
        config.feishu_webhook_url = (
            payload.feishu_webhook_url.strip() or None
        )
    if payload.tg_bot_token is not None:
        config.tg_bot_token = payload.tg_bot_token.strip() or None
    if payload.tg_chat_id is not None:
        config.tg_chat_id = payload.tg_chat_id.strip() or None
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
    summary="给指定通道发送测试消息(用当前已保存的配置)",
)
async def send_test_notification(
    current_user: CurrentUserDep,
    db: DbDep,
    channel: Annotated[Literal["feishu", "telegram"], Query(...)],
) -> NotificationTestResult:
    config = await get_config(db, current_user.id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未配置任何通道 · 请先填写 webhook / token 再保存",
        )
    result = await send_test(config, channel)
    return NotificationTestResult(
        channel=result.channel,
        ok=result.ok,
        error=result.error,
    )
