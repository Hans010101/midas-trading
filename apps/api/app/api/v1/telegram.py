"""Telegram 统一 bot 路由 · /api/v1/telegram/* · 0024 v2 · M1-G G1。

- POST /telegram/bind-token · 登录态 · 生成一次性绑定 token + deep link
- POST /telegram/webhook    · Telegram 入站 · secret_token 头校验 · 处理 /start 绑定

纯新增 · 不碰旧 per-user bot / 飞书 / dispatcher / 下单 emit。
"""

from __future__ import annotations

import hmac
import logging
from typing import TYPE_CHECKING, Annotated, Any

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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, OptionalClickHouseDep
from app.core.config import settings
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.notification import NotificationConfig
from app.services.bot import router as bot_router
from app.services.notifications import telegram
from app.services.notifications.telegram_bind import (
    create_bind_token,
    deep_link,
    handle_start,
    webhook_secret,
)

if TYPE_CHECKING:
    from app.services.bot.renderers.telegram import BotReply
    from app.services.clickhouse_client import ClickHouseClient

logger = logging.getLogger(__name__)

# 常驻快捷键盘开启提示(reply-kb 单独发一条 · 不混 inline 卡)
_REPLY_KB_HINT = "⌨️ 快捷键盘已开启,点输入框上方按钮快速操作 ↓"

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


@router.post(
    "/unbind",
    summary="解绑当前账号的 Telegram(清空 tg_chat_id · 登录态)",
)
async def unbind_telegram(
    current_user: CurrentUserDep, db: DbDep,
) -> dict[str, bool]:
    """解绑 · 清空当前用户自己的 tg_chat_id(D7)· 幂等 · 不碰其它字段 / 无迁移。"""
    config = await db.scalar(
        select(NotificationConfig).where(
            NotificationConfig.user_id == current_user.id,
        ),
    )
    if config is not None and config.tg_chat_id is not None:
        config.tg_chat_id = None
        await db.commit()
    return {"unbound": True}


async def _send_reply_safe(
    chat_id: int, text: str, keyboard: dict[str, Any] | None = None,
) -> None:
    """后台发回执(可带 inline 键盘)· 失败仅记 log(不影响已返回的 200)。"""
    try:
        await telegram.send(
            settings.tg_bot_token, str(chat_id), text, reply_markup=keyboard,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[tg-webhook] 回执发送失败 chat_id=%s:%s", chat_id, e)


async def _send_photo_safe(
    chat_id: int, photo_url: str, caption: str, keyboard: dict[str, Any] | None = None,
) -> None:
    """后台发 K线图(sendPhoto · KLINE-001)· 失败【回退发文本网页链接】(数据不足 404 /
    TG 拉图失败都走这条 · 别让用户啥也收不到)。caption = 原文本(也作回退正文)。"""
    try:
        await telegram.send_photo(
            settings.tg_bot_token, str(chat_id), photo_url,
            caption=caption, reply_markup=keyboard,
        )
    except Exception as e:  # noqa: BLE001
        logger.info(
            "[tg-webhook] sendPhoto 失败 chat_id=%s · 回退文本链接:%s", chat_id, e,
        )
        await _send_reply_safe(chat_id, caption, keyboard)


async def _edit_reply_safe(
    chat_id: int, message_id: int, text: str, keyboard: dict[str, Any] | None = None,
) -> None:
    """后台原地编辑消息(按钮导航)· 失败仅记 log(内容未变等良性错误吞掉)。"""
    try:
        await telegram.edit_message_text(
            settings.tg_bot_token, str(chat_id), message_id, text,
            reply_markup=keyboard,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[tg-webhook] 编辑消息失败 chat_id=%s:%s", chat_id, e)


async def _answer_cb_safe(callback_query_id: str) -> None:
    """后台消除按钮 loading 态 · 失败仅记 log。"""
    try:
        await telegram.answer_callback_query(settings.tg_bot_token, callback_query_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("[tg-webhook] answerCallbackQuery 失败:%s", e)


@router.post(
    "/webhook",
    summary="Telegram webhook 入站(secret 校验 · /start 绑定 + G3 命令/按钮)",
    include_in_schema=False,  # 内部端点 · 不进公开 OpenAPI
)
async def telegram_webhook(
    request: Request,
    db: DbDep,
    redis: RedisDep,
    ch: OptionalClickHouseDep,
    background: BackgroundTasks,
) -> dict[str, bool]:
    # 1. secret_token 头校验(防伪造 update)· 常量时间比较 —— G1 逻辑不变
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(header, webhook_secret()):
        logger.warning("[tg-webhook] secret_token 校验失败 · 拒绝")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="invalid secret token",
        )

    # 2. 解析 update(失败 → 回 200 忽略,避免 Telegram 重试风暴)
    try:
        update = await request.json()
    except (ValueError, UnicodeDecodeError):
        return {"ok": True}
    update = update or {}

    # 2a. callback_query(inline 按钮回调)· G3 新增分支 —— 不碰 /start 绑定
    callback = update.get("callback_query")
    if callback:
        return await _handle_callback_update(db, redis, ch, background, callback)

    # 2b. message 文本
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text")
    if chat_id is None:
        return {"ok": True}
    chat_id = int(chat_id)

    # 3. /start 绑定(G1 原逻辑)
    result = await handle_start(db, redis, chat_id=chat_id, text=text)
    if result.kind != "ignored":
        # 是 /start 绑定尝试 → 发绑定回执后结束(G3 不介入)
        if result.reply_text and settings.tg_bot_token:
            # 时机A:绑定成功(bound)→ 欢迎消息同时设【常驻快捷键盘】;
            #        失败绑定(invalid_token/chat_taken · 未绑定)→ 纯文本不设键盘。
            kb = bot_router.REPLY_KB_MARKUP if result.kind == "bound" else None
            background.add_task(_send_reply_safe, chat_id, result.reply_text, kb)
        return {"ok": True}

    # 4. 非绑定文本 → G3 命令(/menu·/price·会话续输·裸代码扫库)· 需 CH(prod 必有)·
    #    裸字母代码命中多市场 → 多卡逐条发(加密在前);单命中 = 单条(零回归)。
    if ch is not None:
        bot_replies: list[BotReply] = await bot_router.handle_command_multi(
            db, redis, ch, chat_id, text,
        )
        if settings.tg_bot_token:
            for reply in bot_replies:
                if reply.photo_url:  # KLINE-001:K线 → sendPhoto(失败回退文本链接)
                    background.add_task(
                        _send_photo_safe, chat_id, reply.photo_url, reply.text, reply.keyboard,
                    )
                else:
                    background.add_task(
                        _send_reply_safe, chat_id, reply.text, reply.keyboard,
                    )

    # 时机B:裸 /start(kind=ignored · 主菜单 inline 已发)→ 追加一条设置常驻键盘 ·
    #        reply-kb 不能与 inline 同消息,故单独发;不每条都设,只 /start 重申(防用户手动收起)。
    txt = (text or "").strip()
    if (txt == "/start" or txt.startswith("/start@")) and settings.tg_bot_token:
        background.add_task(
            _send_reply_safe, chat_id, _REPLY_KB_HINT, bot_router.REPLY_KB_MARKUP,
        )
    return {"ok": True}


async def _handle_callback_update(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient | None,
    background: BackgroundTasks,
    callback: dict[str, Any],
) -> dict[str, bool]:
    """处理 inline 按钮回调:编排 → 原地编辑刷新 + 消除 loading 态。"""
    msg = callback.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    cq_id = callback.get("id")
    if chat_id is None or cq_id is None:
        return {"ok": True}
    chat_id = int(chat_id)

    if settings.tg_bot_token:
        background.add_task(_answer_cb_safe, str(cq_id))
    if ch is None:
        return {"ok": True}

    reply = await bot_router.handle_callback(db, redis, ch, chat_id, callback.get("data"))
    if settings.tg_bot_token:
        if reply.photo_url:  # KLINE-001:K线图发新消息(无法把文本编辑成图)· 失败回退文本
            background.add_task(
                _send_photo_safe, chat_id, reply.photo_url, reply.text, reply.keyboard,
            )
            return {"ok": True}
        message_id = msg.get("message_id")
        if message_id is not None:
            background.add_task(
                _edit_reply_safe, chat_id, int(message_id), reply.text, reply.keyboard,
            )
        else:
            background.add_task(
                _send_reply_safe, chat_id, reply.text, reply.keyboard,
            )
    return {"ok": True}
