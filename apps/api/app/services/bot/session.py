"""多步会话态(通道无关 · DP7)· 0025 M1-G G3 + ADR 0032 阶段三多通道。

把「点了行情按钮、正在等用户输代码」这类对话上下文存 Redis,短 TTL,不建 PG 表(零迁移)。
只用 get/setex/delete 三个原语(与现有 Redis 替身一致)。

ADR 0032:键按 (channel, uid) 命名。Telegram 前缀保持 `tg_session:{chat_id}`(零回归 ·
历史会话 / 测试键不变);其余通道用 channel 名本身(如 `feishu_session:{open_id}`)。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from redis.asyncio import Redis

_SESSION_TTL_SECONDS = 300  # 多步交互上下文 5min 足够 · 过期自动丢弃
# telegram 前缀保持 "tg"(键 = tg_session:{chat_id} 字节不变);其余通道用 channel 名。
_CHANNEL_PREFIX: dict[str, str] = {"telegram": "tg"}


def _key(channel: str, uid: str) -> str:
    prefix = _CHANNEL_PREFIX.get(channel, channel)
    return f"{prefix}_session:{uid}"


async def get_session(redis: Redis, channel: str, uid: str) -> dict[str, Any] | None:
    """读会话态;无 / 损坏 → None。"""
    raw: str | None = await redis.get(_key(channel, uid))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


async def set_session(
    redis: Redis, channel: str, uid: str, state: dict[str, Any],
) -> None:
    """写会话态(覆盖 · 刷新 TTL)。"""
    await redis.setex(_key(channel, uid), _SESSION_TTL_SECONDS, json.dumps(state))


async def clear_session(redis: Redis, channel: str, uid: str) -> None:
    """清会话态(一次交互完成 / 返回主菜单时调用)。"""
    await redis.delete(_key(channel, uid))
