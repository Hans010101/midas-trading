"""Telegram 统一 bot · /start 绑定编排(0024 v2 · M1-G G1)。

职责(纯新增 · 不碰旧 per-user bot / 飞书 / dispatcher):
- webhook secret 由 SECRET_KEY 派生(不新增第二个 secret)· setWebhook 与入站校验同源。
- 一次性绑定 token:存 Redis `tg_bind:{token}→user_id`,短 TTL(默认 10min)。
- 入站 `/start <token>`:校验 token → 写 notification_config.tg_chat_id → 回执文案。
  · 「一 chat 一账号」应用层校验(G2 会加 DB 唯一索引)。
- 启动后台自动 setWebhook(配了 token + https 公网 URL 才跑 · fail-soft)。

红线:只虚拟交易。
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.models.notification import NotificationConfig
from app.services.notifications import telegram

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_BIND_KEY_PREFIX = "tg_bind:"

# G5 DP-G5-5:bot 命令菜单(启动期 setMyCommands · 随代码同步)
_BOT_COMMANDS: list[dict[str, str]] = [
    {"command": "menu", "description": "功能菜单(行情/自选/持仓/下单/告警)"},
    {"command": "price", "description": "查行情 · 用法 /price <代码>"},
    {"command": "start", "description": "绑定 / 开始"},
]


# ── secret / url 派生 ────────────────────────────────────────────────


def webhook_secret() -> str:
    """Telegram webhook secret_token · 由 SECRET_KEY 派生(HMAC-SHA256)。

    Telegram 限制 secret_token 为 1-256 字符 [A-Za-z0-9_-];hex 摘要满足。
    setWebhook 注册与入站头校验用同一个值,不新增独立 secret。
    """
    digest = hmac.new(
        settings.secret_key.encode("utf-8"),
        b"midas-tg-webhook-v1",
        hashlib.sha256,
    ).hexdigest()
    return digest[:48]


def webhook_url() -> str:
    """公网 webhook 地址 · Telegram 把 update POST 到这里。"""
    base = settings.public_api_base_url.rstrip("/")
    return f"{base}/api/v1/telegram/webhook"


def deep_link(token: str) -> str | None:
    """t.me deep link · 点开即向 bot 发 `/start <token>`。

    bot 用户名(D9)未配 → 返回 None(前端 G3 再补),不阻塞 G1。
    """
    username = settings.tg_bot_username.strip()
    if not username:
        return None
    return f"https://t.me/{username}?start={token}"


# ── 一次性绑定 token(Redis)─────────────────────────────────────────


def _bind_key(token: str) -> str:
    return f"{_BIND_KEY_PREFIX}{token}"


async def create_bind_token(redis: Redis, user_id: UUID) -> str:
    """生成一次性绑定 token 并存 Redis(TTL=settings.tg_bind_token_ttl_seconds)。"""
    token = secrets.token_urlsafe(24)
    await redis.setex(
        _bind_key(token), settings.tg_bind_token_ttl_seconds, str(user_id),
    )
    return token


async def peek_bind_token(redis: Redis, token: str) -> str | None:
    """查 token 对应的 user_id(不删 · 成功绑定后才 consume)。"""
    user_id: str | None = await redis.get(_bind_key(token))
    return user_id


async def consume_bind_token(redis: Redis, token: str) -> None:
    """删除已用 token(一次性)。"""
    await redis.delete(_bind_key(token))


# ── /start 入站绑定 ──────────────────────────────────────────────────


def parse_start_command(text: str | None) -> str | None:
    """从消息文本解析 `/start <token>` 的 token;非该格式返回 None。

    兼容群里 `/start@BotName <token>`(虽然我们只做私聊)。
    """
    if not text:
        return None
    parts = text.strip().split()
    if not parts:
        return None
    head = parts[0]
    is_start = head == "/start" or head.startswith("/start@")
    if not is_start or len(parts) < 2:  # noqa: PLR2004
        return None
    return parts[1]


@dataclass(frozen=True)
class StartResult:
    """/start 处理结果 · 路由据此决定回执文案(后台异步发送)。"""

    kind: Literal["bound", "invalid_token", "chat_taken", "ignored"]
    reply_text: str | None = None
    user_id: UUID | None = None


async def handle_start(
    db: AsyncSession,
    redis: Redis,
    *,
    chat_id: int,
    text: str | None,
) -> StartResult:
    """处理入站 `/start <token>`:校验 token → 写 tg_chat_id → 返回回执。

    纯新增写入 notification_config.tg_chat_id(lazy create);不动飞书 / 旧 token。
    """
    token = parse_start_command(text)
    if token is None:
        return StartResult(kind="ignored")

    user_id_str = await peek_bind_token(redis, token)
    if user_id_str is None:
        return StartResult(
            kind="invalid_token",
            reply_text="绑定链接无效或已过期,请回设置页重新生成。",
        )
    user_id = UUID(user_id_str)
    chat_id_str = str(chat_id)

    # 「一 chat 一账号」应用层校验(G2 会加 DB 唯一索引兜底)
    other = await db.scalar(
        select(NotificationConfig).where(
            NotificationConfig.tg_chat_id == chat_id_str,
            NotificationConfig.user_id != user_id,
        ),
    )
    if other is not None:
        return StartResult(
            kind="chat_taken",
            reply_text="该 Telegram 已绑定其他账号,请先在原账号解绑。",
        )

    config = await db.scalar(
        select(NotificationConfig).where(NotificationConfig.user_id == user_id),
    )
    if config is None:
        config = NotificationConfig(user_id=user_id)
        db.add(config)
    config.tg_chat_id = chat_id_str
    await db.commit()
    await consume_bind_token(redis, token)

    logger.info("[tg-bind] user_id=%s 绑定 chat_id=%s 成功", user_id, chat_id_str)
    return StartResult(
        kind="bound",
        user_id=user_id,
        reply_text=(
            "✅ 绑定成功 · 点金 Midas\n\n"
            "以后成交 / 价格异动提醒会推送到这里。"
        ),
    )


# ── 启动期自动注册 webhook(后台 · fail-soft)─────────────────────────


async def register_webhook_if_configured() -> None:
    """配了 tg_bot_token + https 公网 URL 才注册 webhook · 失败不致命。

    由 API lifespan 后台触发(create_task)· 不阻塞启动 / /health。
    幂等:Telegram setWebhook 可重复调用。
    """
    if not settings.tg_bot_token:
        logger.info("[tg-bind] 未配 TG_BOT_TOKEN · 跳过 webhook 注册(统一 bot 未启用)")
        return
    url = webhook_url()
    if not url.startswith("https://"):
        logger.warning(
            "[tg-bind] public_api_base_url 非 https(%s)· Telegram 要求 https · 跳过 webhook 注册",
            url,
        )
        return
    try:
        await telegram.set_webhook(settings.tg_bot_token, url, webhook_secret())
    except Exception as e:  # noqa: BLE001 · 注册失败不致命:可重新部署重试
        logger.warning("[tg-bind] setWebhook 失败(可重新部署重试):%s", e)
        return
    logger.info("[tg-bind] webhook 已注册 → %s", url)

    # G5 DP-G5-5:命令菜单随代码同步(失败不致命,与 webhook 注册解耦)
    try:
        await telegram.set_my_commands(settings.tg_bot_token, _BOT_COMMANDS)
    except Exception as e:  # noqa: BLE001
        logger.warning("[tg-bind] setMyCommands 失败(不致命):%s", e)
    else:
        logger.info("[tg-bind] 命令菜单已同步(%d 条)", len(_BOT_COMMANDS))
