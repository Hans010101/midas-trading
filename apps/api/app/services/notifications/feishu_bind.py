"""飞书绑定编排 · ADR 0032 阶段三(对称 telegram_bind 的 bind-token 机制)。

职责:
- 一次性绑定 token:存 Redis `feishu_bind:{token}→user_id`,短 TTL(复用 tg_bind_token_ttl)。
  注:按通道各自前缀(feishu_bind: / tg_bind:),不共享单一 token —— 飞书绑定码只在飞书生效,
  且 TG 侧 telegram_bind 零改动。
- 入站绑定:用户在飞书发绑定码(支持 `/bind <token>` / `绑定 <token>` 显式,或直接粘贴码)→
  校验 token → 写 notification_config.feishu_open_id → 「一 open_id 一账号」应用层校验
  (对称 TG handle_start;DB partial 唯一索引兜底,阶段二迁移已建)。

🔴 红线:open_id 只由【已验签事件】传入(webhook 构造点),本模块只接收 open_id 入参,
绝不从文本解析身份;凭证不进日志。
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.models.notification import NotificationConfig

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_BIND_KEY_PREFIX = "feishu_bind:"
_DISCLAIMER = "仅供参考,不构成投资建议。"
# 显式绑定意图前缀(去掉后即 token);其余单词(无空格)按隐式粘贴码尝试。
_EXPLICIT_PREFIXES = ("/bind ", "/绑定 ", "绑定 ", "/start ")


def _bind_key(token: str) -> str:
    return f"{_BIND_KEY_PREFIX}{token}"


async def create_bind_token(redis: Redis, user_id: UUID) -> str:
    """生成一次性绑定 token 并存 Redis(TTL=settings.tg_bind_token_ttl_seconds 复用)。"""
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
    await redis.delete(_bind_key(token))


def _extract_token(text: str | None) -> tuple[str | None, bool]:
    """从文本解析绑定 token · 返回 (token候选, 是否显式绑定意图)。

    - 显式:`/bind <tok>` / `绑定 <tok>` / `/start <tok>` → (tok, True)
    - 隐式:单个词(无空格,粘贴的码)→ (tok, False);多词/空 → (None, False)
    """
    t = (text or "").strip()
    if not t:
        return (None, False)
    for prefix in _EXPLICIT_PREFIXES:
        if t.startswith(prefix):
            return (t[len(prefix):].strip() or None, True)
    if t in ("/bind", "/绑定", "绑定"):
        return (None, True)  # 显式意图但漏了 token
    if " " in t:
        return (None, False)  # 多词 → 不是裸 token → 当普通消息
    return (t, False)  # 单词 → 可能是粘贴的码


@dataclass(frozen=True)
class FeishuBindResult:
    """绑定处理结果 · webhook 据此决定回执 / 是否转 handle_inbound。"""

    kind: Literal["bound", "invalid_token", "open_id_taken", "ignored"]
    reply_text: str | None = None
    user_id: UUID | None = None


async def handle_feishu_bind(
    db: AsyncSession,
    redis: Redis,
    *,
    open_id: str,
    text: str | None,
) -> FeishuBindResult:
    """处理飞书绑定:校验 token → 写 feishu_open_id → 返回结果。

    🔴 open_id 来自【已验签事件】(webhook 唯一注入点)· 绝不从 text 取身份。
    kind=ignored 表示"这不是绑定(没匹配到有效 token)"→ webhook 转 handle_inbound。
    """
    token, explicit = _extract_token(text)
    if token is None:
        if explicit:  # 显式意图但漏 token
            return FeishuBindResult(
                kind="invalid_token",
                reply_text=f"请在绑定指令后带上绑定码,例如「/bind 你的码」。\n{_DISCLAIMER}",
            )
        return FeishuBindResult(kind="ignored")

    user_id_str = await peek_bind_token(redis, token)
    if user_id_str is None:
        # 显式意图但码无效 → 报错;隐式(随手单词)→ 当普通消息转 handle_inbound
        if explicit:
            return FeishuBindResult(
                kind="invalid_token",
                reply_text=f"绑定码无效或已过期,请回设置页重新生成。\n{_DISCLAIMER}",
            )
        return FeishuBindResult(kind="ignored")

    user_id = UUID(user_id_str)

    # 「一 open_id 一账号」应用层校验(DB partial 唯一索引兜底)
    other = await db.scalar(
        select(NotificationConfig).where(
            NotificationConfig.feishu_open_id == open_id,
            NotificationConfig.user_id != user_id,
        ),
    )
    if other is not None:
        return FeishuBindResult(
            kind="open_id_taken",
            reply_text=f"该飞书已绑定其他账号,请先在原账号解绑。\n{_DISCLAIMER}",
        )

    config = await db.scalar(
        select(NotificationConfig).where(NotificationConfig.user_id == user_id),
    )
    if config is None:
        config = NotificationConfig(user_id=user_id)
        db.add(config)
    config.feishu_open_id = open_id
    await db.commit()
    await consume_bind_token(redis, token)

    logger.info("[feishu-bind] user_id=%s 绑定 open_id 成功", user_id)
    return FeishuBindResult(
        kind="bound",
        user_id=user_id,
        reply_text=(
            "✅ 绑定成功 · 点金 Midas\n\n"
            f"以后成交 / 价格异动提醒会推送到这里,也可发 /menu 打开功能菜单。\n{_DISCLAIMER}"
        ),
    )
