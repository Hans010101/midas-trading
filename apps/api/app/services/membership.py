"""会员权益 + AI 额度系统(会员 Phase 1 刀1)。

🔴 红线:额度只挂 POST /structure/diagnose 与 POST /backtest 两端点
   (pytest 路由终扫断言钉死);交易链路 / 行情 / 决策卡永远零挂载。

设计(调研 P1-P5 + Hans 拍板):
- plan 解析:subscription 无行 / 非 active / 已过期 → 'free'(lazy 先例)
- 计数:Redis INCR quota:{user_id}:{feature}:{YYYYMMDD} · UTC+8 自然日切 ·
  EXPIRE 48h(跨日残键自然过期);ai_usage_log(user_id 列)做审计副本
- 扣减位置是灵魂:QuotaDep 只查(429 闸),INCR 由调用方放在
  「真实消耗」点 —— diagnose 缓存 miss 烧 LLM 后 / backtest 创建成功后
- Redis 故障语义:检查/扣减失败一律放行 + warning(可用性 > 计费精确,
  对齐 structure 缓存层降级先例;单次成本 <1 分钱,放行无伤)
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.subscription import Subscription
from app.models.user import User

logger = logging.getLogger(__name__)

QuotaFeature = Literal["diagnose", "backtest"]

# plan → feature → 每日次数(Hans 拍板:free 20·10 / pro 100·50)。
# Phase 1 代码常量起步;DB 配置表是运营需求出现后(Phase 2+)的事。
PLAN_QUOTAS: dict[str, dict[str, int]] = {
    "free": {"diagnose": 20, "backtest": 10},
    "pro": {"diagnose": 100, "backtest": 50},
}

# 额度按产品受众自然日切(UTC+8)· 不用 trading_day(额度是商业概念非行情概念)
_QUOTA_TZ = timezone(timedelta(hours=8))
_QUOTA_KEY_TTL_S = 48 * 3600


async def resolve_plan(db: AsyncSession, user_id: UUID) -> str:
    """订阅行 → plan;无行 / 非 active / 已过期 / 未知 plan → 'free'。"""
    sub = await db.scalar(select(Subscription).where(Subscription.user_id == user_id))
    if sub is None or sub.status != "active":
        return "free"
    if sub.expires_at is not None and sub.expires_at <= datetime.now(UTC):
        return "free"
    return sub.plan if sub.plan in PLAN_QUOTAS else "free"


def quota_key(user_id: UUID, feature: QuotaFeature) -> str:
    today = datetime.now(_QUOTA_TZ).strftime("%Y%m%d")
    return f"quota:{user_id}:{feature}:{today}"


def quota_reset_at() -> datetime:
    """下一个 UTC+8 零点(429 detail / quota/me 共用口径)。"""
    now = datetime.now(_QUOTA_TZ)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


async def get_quota_used(user_id: UUID, feature: QuotaFeature) -> int:
    redis = await get_redis()
    raw = await redis.get(quota_key(user_id, feature))
    return int(raw) if raw is not None else 0


async def consume_quota(user_id: UUID, feature: QuotaFeature) -> None:
    """真实消耗后 +1 · INCR 原子 · 首次创建键时设 48h TTL · 失败仅 warning 不阻塞。"""
    try:
        redis = await get_redis()
        key = quota_key(user_id, feature)
        n = await redis.incr(key)
        if n == 1:
            await redis.expire(key, _QUOTA_KEY_TTL_S)
    except Exception as e:  # noqa: BLE001 — 扣减失败不阻塞业务结果(用户已拿到诊断/回测)
        logger.warning("[quota.consume] failed user=%s feature=%s err=%s", user_id, feature, e)


def make_quota_consumer(
    user_id: UUID, feature: QuotaFeature,
) -> Callable[[], Awaitable[None]]:
    """打包成无参回调 · 给 workflow 的「真实消耗点」(diagnose 缓存 miss)调用。"""

    async def _consume() -> None:
        await consume_quota(user_id, feature)

    return _consume


def require_quota(feature: QuotaFeature) -> Callable[..., Awaitable[User]]:
    """额度闸依赖工厂(照 AdminDep 范式)· 只查不扣 · 超额 429。

    返回 User(替换原 CurrentUserDep 位置即同时完成鉴权)。
    Redis 故障 → 放行(可用性优先 · warning 留痕)。
    """

    async def _check(
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        plan = await resolve_plan(db, current_user.id)
        limit = PLAN_QUOTAS[plan][feature]
        try:
            used = await get_quota_used(current_user.id, feature)
        except Exception as e:  # noqa: BLE001 — Redis 故障放行
            logger.warning(
                "[quota.check] redis failed → 放行 user=%s feature=%s err=%s",
                current_user.id, feature, e,
            )
            return current_user
        if used >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "quota_exceeded",
                    "feature": feature,
                    "plan": plan,
                    "limit": limit,
                    "used": used,
                    "reset_at": quota_reset_at().isoformat(),
                },
            )
        return current_user

    return _check
