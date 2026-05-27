"""Telegram 统一 bot 路由 · /api/v1/telegram/* · 0024 v2 · M1-G G1。

- POST /telegram/bind-token · 登录态 · 生成一次性绑定 token + deep link
- POST /telegram/webhook    · Telegram 入站 · secret_token 头校验 · 处理 /start 绑定

纯新增 · 不碰旧 per-user bot / 飞书 / dispatcher / 下单 emit。
"""

from __future__ import annotations

import hmac
import logging
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    status,
)
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.core.config import settings
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.services.notifications import telegram
from app.services.notifications.telegram_bind import (
    create_bind_token,
    deep_link,
    handle_start,
    webhook_secret,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[Redis, Depends(get_redis)]


class TgBindTokenResponse(BaseModel):
    """POST /telegram/bind-token 响应。"""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(description="一次性绑定 token · 发给 bot 的 /start 参数")
    deep_link: str | None = Field(
        default=None,
        description="t.me deep link · bot 用户名未配时为 null(前端 G3 补)",
    )
    expires_in: int = Field(description="token 有效秒数")


@router.post(
    "/bind-token",
    response_model=TgBindTokenResponse,
    summary="生成 Telegram 绑定一次性 token(登录态)",
)
async def create_telegram_bind_token(
    current_user: CurrentUserDep, redis: RedisDep,
) -> TgBindTokenResponse:
    if not settings.tg_bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram bot 未配置(TG_BOT_TOKEN 未设)",
        )
    token = await create_bind_token(redis, current_user.id)
    return TgBindTokenResponse(
        token=token,
        deep_link=deep_link(token),
        expires_in=settings.tg_bind_token_ttl_seconds,
    )


async def _send_reply_safe(chat_id: int, text: str) -> None:
    """后台发回执 · 失败仅记 log(不影响 webhook 已返回的 200)。"""
    try:
        await telegram.send(settings.tg_bot_token, str(chat_id), text)
    except Exception as e:  # noqa: BLE001
        logger.warning("[tg-webhook] 回执发送失败 chat_id=%s:%s", chat_id, e)


@router.post(
    "/webhook",
    summary="Telegram webhook 入站(secret_token 头校验 · 处理 /start 绑定)",
    include_in_schema=False,  # 内部端点 · 不进公开 OpenAPI
)
async def telegram_webhook(
    request: Request,
    db: DbDep,
    redis: RedisDep,
    background: BackgroundTasks,
) -> dict[str, bool]:
    # 1. secret_token 头校验(防伪造 update)· 常量时间比较
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(header, webhook_secret()):
        logger.warning("[tg-webhook] secret_token 校验失败 · 拒绝")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="invalid secret token",
        )

    # 2. 解析 update(失败 / 非 message → 回 200 忽略,避免 Telegram 重试风暴)
    try:
        update = await request.json()
    except (ValueError, UnicodeDecodeError):
        return {"ok": True}
    message = (update or {}).get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text")
    if chat_id is None:
        return {"ok": True}

    # 3. 处理 /start 绑定
    result = await handle_start(db, redis, chat_id=int(chat_id), text=text)

    # 4. 回执(后台异步发 · webhook 立即返回 200)
    if result.reply_text and settings.tg_bot_token:
        background.add_task(_send_reply_safe, int(chat_id), result.reply_text)

    return {"ok": True}
