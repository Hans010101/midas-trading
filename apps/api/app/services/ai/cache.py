"""应用层结果缓存 · 0012 ADR § 应用层结果缓存。

key 设计:ai:decision:{market}:{symbol}:{period}:{trading_day}

TTL 策略:
  - A 股 / 美股:4h(收盘后下一交易日 9:25 前自然过期)
  - 加密:1h + 6 小时分桶(24/7 高频)

预期命中率:
  - 100 用户 top 20 标的 → 2,400 LLM 调用/月(详见 0012 § 成本验证)

主动 invalidate(M2+,M1 二波不做):
  - 价格异动 trigger / 财报事件 → 主动删 cache
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

from app.core.redis_client import get_redis
from app.schemas.ai_decision import DecisionCardResponse
from app.schemas.market import Market, Period

logger = logging.getLogger(__name__)


# TTL 配置(秒)· 0012 § 应用层结果缓存
_TTL_BY_MARKET: dict[Market, int] = {
    "cn": 4 * 3600,
    "us": 4 * 3600,
    "crypto": 1 * 3600,
    "hk": 4 * 3600,  # 港股日线 · 同 cn/us(decision-card?market=hk 缓存 TTL · 否则 KeyError)
}


def compute_trading_day(market: Market, now: datetime | None = None) -> str:
    """计算缓存 key 用的「交易日」标识。

    A 股 / 美股:`YYYY-MM-DD`(用 UTC 日期 · M2+ 接齐交易日历再校准)
    加密:`YYYY-MM-DD-HH` 6 小时分桶(取整到 0/6/12/18 时)
    """
    now = now or datetime.now(UTC)
    if market == "crypto":
        bucket_hour = (now.hour // 6) * 6
        return f"{now:%Y-%m-%d}-{bucket_hour:02d}"
    return f"{now:%Y-%m-%d}"


def make_cache_key(
    market: Market, symbol: str, period: Period, trading_day: str,
) -> str:
    """生成 Redis cache key · 详见 0012 § Cache Key 设计。"""
    # symbol 里可能有 / 之类的字符,Redis 接受但 url 不友好 · 这里保留原样
    # (Redis 不要 url 化,key 字符集随意)
    return f"ai:decision:{market}:{symbol}:{period}:{trading_day}"


async def get_cached_card(
    market: Market, symbol: str, period: Period,
) -> DecisionCardResponse | None:
    """命中返回 DecisionCardResponse(cached=True),未命中返回 None。"""
    trading_day = compute_trading_day(market)
    key = make_cache_key(market, symbol, period, trading_day)
    try:
        redis = await get_redis()
        raw = await redis.get(key)
    except Exception as e:  # noqa: BLE001
        logger.warning("[ai.cache] get failed key=%s err=%s", key, e)
        return None

    if raw is None:
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("[ai.cache] corrupt cache key=%s err=%s", key, e)
        return None

    # cached 字段从 False 翻成 True
    data["cached"] = True
    return DecisionCardResponse.model_validate(data)


async def set_cached_card(card: DecisionCardResponse) -> None:
    """写 Redis · TTL 按市场配置。"""
    trading_day = compute_trading_day(card.market)
    key = make_cache_key(card.market, card.symbol, card.period, trading_day)
    ttl = _TTL_BY_MARKET[card.market]

    # cached 字段写入时强制 False · 命中读出时 get_cached_card 翻 True
    payload = card.model_dump(mode="json")
    payload["cached"] = False

    try:
        redis = await get_redis()
        await redis.setex(key, ttl, json.dumps(payload, ensure_ascii=False))
        logger.info("[ai.cache] set key=%s ttl=%ds", key, ttl)
    except Exception as e:  # noqa: BLE001
        # 缓存失败不阻塞主链路 · 用户已经看到卡片了
        logger.warning("[ai.cache] set failed key=%s err=%s", key, e)


async def delete_cached_card(
    market: Market, symbol: str, period: Period,
) -> int:
    """主动失效 cache · M2+ 用 · 当前未挂调用方。"""
    trading_day = compute_trading_day(market)
    key = make_cache_key(market, symbol, period, trading_day)
    try:
        redis = await get_redis()
        return await redis.delete(key)
    except Exception as e:  # noqa: BLE001
        logger.warning("[ai.cache] delete failed key=%s err=%s", key, e)
        return 0


# ===== 辅助 · M1 二波 SLA 估算 =====


def estimate_next_invalidation_at(market: Market) -> datetime:
    """估算下一次缓存失效时间 · UI 展示「上次更新 X 分钟前(缓存)」用。

    M1 二波简化:基于 TTL 直接算,不考虑交易日历精度。
    """
    return datetime.now(UTC) + timedelta(seconds=_TTL_BY_MARKET[market])
