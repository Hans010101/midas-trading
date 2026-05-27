"""多步会话态(Telegram 适配层 · DP7)· 0025 M1-G G3。

把「点了行情按钮、正在等用户输代码」这类对话上下文存 Redis(`tg_session:{chat_id}`,
短 TTL),不建 PG 表(零迁移)。只用 get/setex/delete 三个原语(与现有 Redis 替身一致)。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from redis.asyncio import Redis

_SESSION_PREFIX = "tg_session:"
_SESSION_TTL_SECONDS = 300  # 多步交互上下文 5min 足够 · 过期自动丢弃


def _key(chat_id: int) -> str:
    return f"{_SESSION_PREFIX}{chat_id}"


async def get_session(redis: Redis, chat_id: int) -> dict[str, Any] | None:
    """读会话态;无 / 损坏 → None。"""
    raw: str | None = await redis.get(_key(chat_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


async def set_session(redis: Redis, chat_id: int, state: dict[str, Any]) -> None:
    """写会话态(覆盖 · 刷新 TTL)。"""
    await redis.setex(_key(chat_id), _SESSION_TTL_SECONDS, json.dumps(state))


async def clear_session(redis: Redis, chat_id: int) -> None:
    """清会话态(一次交互完成 / 返回主菜单时调用)。"""
    await redis.delete(_key(chat_id))
