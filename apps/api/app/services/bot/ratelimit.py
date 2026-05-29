"""bot 限流(DP11)· 0025 M1-G G4 + ADR 0032 阶段三多通道。

per-(channel,uid) 固定窗口计数(Redis INCR + EXPIRE):
- 命令(含按钮回调)≤ 20 / 分钟
- 下单 ≤ 10 / 分钟

ADR 0032:键按 (channel, uid) 命名。Telegram 前缀保持 `tg_rl:{kind}:{chat_id}`(零回归);
其余通道用 channel 名(如 `feishu_rl:cmd:{open_id}`)。

fail-open:Redis 异常时放行(限流是防滥用护栏,不该因 Redis 抖动把正常用户挡在外面;
下单本身还有引擎的保证金/余额校验兜底,绝不会因放行造成真实损失 —— 全程虚拟)。
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
# telegram 前缀保持 "tg"(键 = tg_rl:{kind}:{chat_id} 字节不变);其余通道用 channel 名。
_CHANNEL_PREFIX: dict[str, str] = {"telegram": "tg"}


async def allow(redis: Redis, kind: str, channel: str, uid: str, limit: int) -> bool:
    """固定 60s 窗口:本窗口内第 ≤limit 次返回 True,超出 False。Redis 异常 → True。"""
    prefix = _CHANNEL_PREFIX.get(channel, channel)
    key = f"{prefix}_rl:{kind}:{uid}"
    try:
        n = await redis.incr(key)
        if n == 1:
            await redis.expire(key, _WINDOW_SECONDS)
        return int(n) <= limit
    except Exception as e:  # noqa: BLE001 · fail-open
        logger.warning(
            "[bot-ratelimit] Redis 异常 · 放行 channel=%s uid=%s kind=%s:%s",
            channel, uid, kind, e,
        )
        return True


async def allow_command(redis: Redis, channel: str, uid: str) -> bool:
    return await allow(redis, "cmd", channel, uid, CMD_LIMIT_PER_MIN)


async def allow_order(redis: Redis, channel: str, uid: str) -> bool:
    return await allow(redis, "ord", channel, uid, ORDER_LIMIT_PER_MIN)
