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
from app.services.membership import resolve_plan
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
    summary="更新通知总开关 + 安静时段(0028 N2)· None 字段保持原值",
)
async def update_notification_config(
    payload: NotificationConfigUpdate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> NotificationConfigResponse:
    """局部更新通知配置 · lazy create。

    本期(N2)扩展为接受 quiet_hours_* 4 个字段(同样 None=不动)。
    Telegram 绑定不在此处理 —— 经 bot 内 /start(0025 统一 bot)。
    🟢 红线:仅写入 quiet_hours 配置字段;不动 dispatcher / alert_scan 求值逻辑。
    """
    config = await get_config(db, current_user.id)
    if config is None:
        config = NotificationConfig(user_id=current_user.id)
        db.add(config)

    if payload.trade_alert_enabled is not None:
        config.trade_alert_enabled = payload.trade_alert_enabled
    if payload.price_alert_enabled is not None:
        config.price_alert_enabled = payload.price_alert_enabled
    if payload.weekly_report_enabled is not None:
        config.weekly_report_enabled = payload.weekly_report_enabled
    # 做T信号 TG 通知 · M2-4 拆两体系(定时全景 / 行情转换)· ★Pro 专属:任一开关设 true 需 Pro
    #   (后端二道 gate · 防 F12 绕前端禁用)· 设 false(退订)任何人都允许 · 仅「开启」拦非 Pro。
    wants_dott_enable = bool(payload.dott_digest_enabled) or bool(payload.dott_transition_enabled)
    if wants_dott_enable and await resolve_plan(db, current_user.id) != "pro":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="做T信号 TG 通知为 Pro 会员专属 · 请先开通 Pro",
        )
    if payload.dott_digest_enabled is not None:
        config.dott_digest_enabled = payload.dott_digest_enabled
    if payload.dott_transition_enabled is not None:
        config.dott_transition_enabled = payload.dott_transition_enabled

    # 0028 N2 · quiet_hours 4 字段(各自可选)
    if payload.quiet_hours_enabled is not None:
        config.quiet_hours_enabled = payload.quiet_hours_enabled
    if payload.quiet_hours_start is not None:
        config.quiet_hours_start = payload.quiet_hours_start
    if payload.quiet_hours_end is not None:
        config.quiet_hours_end = payload.quiet_hours_end
    if payload.quiet_hours_tz is not None:
        config.quiet_hours_tz = payload.quiet_hours_tz

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
