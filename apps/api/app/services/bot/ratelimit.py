"""bot 限流(DP11)· 0025 M1-G G4。

per-chat 固定窗口计数(Redis INCR + EXPIRE):
- 命令(含按钮回调)≤ 20 / 分钟
- 下单 ≤ 10 / 分钟

fail-open:Redis 异常时放行(限流是防滥用的护栏,不该因 Redis 抖动把正常用户挡在外面;
下单本身还有引擎的保证金/余额校验兜底,绝不会因为放行就造成真实损失 —— 全程虚拟)。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

CMD_LIMIT_PER_MIN = 20   # 命令 / 按钮回调
ORDER_LIMIT_PER_MIN = 10  # 下单(确认执行)
_WINDOW_SECONDS = 60


async def allow(redis: Redis, kind: str, chat_id: int, limit: int) -> bool:
    """固定 60s 窗口:本窗口内第 ≤limit 次返回 True,超出 False。Redis 异常 → True。"""
    key = f"tg_rl:{kind}:{chat_id}"
    try:
        n = await redis.incr(key)
        if n == 1:
            await redis.expire(key, _WINDOW_SECONDS)
        return int(n) <= limit
    except Exception as e:  # noqa: BLE001 · fail-open
        logger.warning("[tg-ratelimit] Redis 异常 · 放行 chat=%s kind=%s:%s", chat_id, kind, e)
        return True


async def allow_command(redis: Redis, chat_id: int) -> bool:
    return await allow(redis, "cmd", chat_id, CMD_LIMIT_PER_MIN)


async def allow_order(redis: Redis, chat_id: int) -> bool:
    return await allow(redis, "ord", chat_id, ORDER_LIMIT_PER_MIN)
