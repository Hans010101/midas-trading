"""Bot 身份解析(核心层 · 平台无关)· 0025 M1-G G3。

唯一职责:把【已通过 webhook secret 校验的】Telegram chat_id 翻成 Midas user_id。

🔴 红线(0025 §7 · R1):bot 是下单/查询的唯一鉴权边界 —— user_id【只】能从这里
(即已验证 webhook update 的 chat.id)解析,【绝不】从用户消息文本里取。G3 只读查询
也走同一解析,确保「自选 / 持仓」永远只返回 chat 绑定账号自己的数据。
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from app.models.notification import NotificationConfig

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def resolve_user_id(db: AsyncSession, chat_id: int) -> UUID | None:
    """chat_id → 绑定的 user_id;未绑定返回 None(调用方提示去网页端绑定)。"""
    result: UUID | None = await db.scalar(
        select(NotificationConfig.user_id).where(
            NotificationConfig.tg_chat_id == str(chat_id),
        ),
    )
    return result
