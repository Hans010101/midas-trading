"""Bot 身份解析(核心层 · 平台无关)· 0025 M1-G G3 + ADR 0032 多通道。

唯一职责:把【已验签事件的】通道用户标识(channel_uid)翻成 Midas user_id ——
telegram=chat_id,飞书=open_id(P2 加 feishu_open_id 列后实现)。

🔴 红线(0025 §7 · R1):bot 是下单/查询的唯一鉴权边界 —— user_id【只】能从这里
(即已验签事件的 channel_uid)解析,【绝不】从用户消息文本里取。只读查询也走同一解析,
确保「自选 / 持仓」永远只返回绑定账号自己的数据。channel_uid 由各通道 webhook 验签后注入。
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from app.models.notification import NotificationConfig

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def resolve_user_id(
    db: AsyncSession, channel: str, channel_uid: str,
) -> UUID | None:
    """(channel, channel_uid) → 绑定的 user_id;未绑定 / 通道未支持返回 None。"""
    if channel == "telegram":
        where = NotificationConfig.tg_chat_id == channel_uid
    else:
        # 飞书 / 钉钉:P2 加列后接入(feishu_open_id 等)· 在此之前一律视为未绑定
        return None
    result: UUID | None = await db.scalar(
        select(NotificationConfig.user_id).where(where),
    )
    return result
