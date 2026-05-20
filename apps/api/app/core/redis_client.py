"""共享异步 Redis 客户端 · 0012 AI 决策卡缓存层依赖。

为什么单独一个模块:
  - 0009 推送 / 0012 决策卡缓存都要用 Redis
  - 之前没有共享客户端 · emit.py 走 Celery broker(不算 Redis 直连)
  - 这次第一次需要直连 Redis · 单例 + lazy 创建

用法:
  client = await get_redis()
  await client.get(key) / await client.setex(key, ttl, value)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from redis.asyncio import Redis, from_url

from app.core.config import settings

if TYPE_CHECKING:
    from redis.asyncio import Redis as RedisType  # noqa: F401

_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """获取或创建共享 Redis 客户端 · lazy + 单例。

    pool 默认 max_connections=10 · 对 100-1000 用户场景够用。
    decode_responses=True · 写入读出都是 str(JSON 序列化由调用方负责)。
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=20,
        )
    return _redis_client


async def close_redis() -> None:
    """关闭 Redis 连接 · 给 lifespan shutdown 用。"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
