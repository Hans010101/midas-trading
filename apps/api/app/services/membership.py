"""会员权益 + AI 额度系统(会员 Phase 1 刀1)。

🔴 红线:额度只挂 POST /structure/diagnose 与 POST /backtest 两端点
   (pytest 路由终扫断言钉死);交易链路 / 行情 / 决策卡永远零挂载。

设计(调研 P1-P5 + Hans 拍板):
- plan 解析:subscription 无行 / 非 active / 已过期 → 'free'(lazy 先例)
- 计数:Redis INCR quota:{user_id}:{feature}:{YYYYMM} · UTC+8 自然月切 ·
  EXPIRE 35天(跨月残键自然过期 · ≥31天+缓冲,防月内提前过期误重置);ai_usage_log 做审计副本
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

# plan → feature → 每月次数(Hans 拍板:free 5·3 / pro 300·150 · 变现强化)。
# Phase 1 代码常量起步;DB 配置表是运营需求出现后(Phase 2+)的事。
PLAN_QUOTAS: dict[str, dict[str, int]] = {
    "free": {"diagnose": 5, "backtest": 3},
    "pro": {"diagnose": 300, "backtest": 150},
}

# 会员周期 → 天数(单一事实源 · 兑换码 / 未来 USDT 支付 / 续费共用,防各处散落漂移)。
# month/quarter/year 与支付周期同口径(Phase2a 支付直接复用本表)。
PERIOD_DAYS: dict[str, int] = {"month": 30, "quarter": 90, "year": 365}

# 额度按产品受众自然月切(UTC+8)· 不用 trading_day(额度是商业概念非行情概念)
_QUOTA_TZ = timezone(timedelta(hours=8))
# TTL 35 天:≥ 最长月 31 天 + 缓冲,确保整月不提前过期(否则月内 key 过期 → 配额误重置)
_QUOTA_KEY_TTL_S = 35 * 24 * 3600


async def resolve_plan(db: AsyncSession, user_id: UUID) -> str:
    """订阅行 → plan;无行 / 非 active / 已过期 / 未知 plan → 'free'。

    ★铂金标记(多账户 PR-1):is_platinum=true → 直接 'pro'(superadmin 手动设·独立于订阅)。
    这是全库 pro 权益单一事实源 —— 一处判断 → 决策卡/策略信号/配额/做T通知/做T推送/用户详情/
    quota_me 全部自动生效,前端 /quota/me 返 'pro' → 前端零改(ProLock 自动不显示)。
    """
    is_platinum = await db.scalar(select(User.is_platinum).where(User.id == user_id))
    if is_platinum:
        return "pro"
    sub = await db.scalar(select(Subscription).where(Subscription.user_id == user_id))
    if sub is None or sub.status != "active":
        return "free"
    if sub.expires_at is not None and sub.expires_at <= datetime.now(UTC):
        return "free"
    return sub.plan if sub.plan in PLAN_QUOTAS else "free"


def quota_key(user_id: UUID, feature: QuotaFeature) -> str:
    month = datetime.now(_QUOTA_TZ).strftime("%Y%m")  # 当月 YYYYMM(按月计数)
    return f"quota:{user_id}:{feature}:{month}"


def quota_reset_at(now: datetime | None = None) -> datetime:
    """下个自然月 1 号 0 点(UTC+8)· 配额按月切(429 detail / quota/me 共用口径)。

    跨年:12 月 → 次年 1 月。day=1 一次性 replace 避开月末非法日(如 3/31 → 4/1)。
    now 可选(默认当前 UTC+8)· 仅测试注入用,生产调用不传。
    """
    now = now or datetime.now(_QUOTA_TZ)
    year, month = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)  # noqa: PLR2004
    return now.replace(
        year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0,
    )


async def get_quota_used(user_id: UUID, feature: QuotaFeature) -> int:
    redis = await get_redis()
    raw = await redis.get(quota_key(user_id, feature))
    return int(raw) if raw is not None else 0


async def consume_quota(user_id: UUID, feature: QuotaFeature) -> None:
    """真实消耗后 +1 · INCR 原子 · 首次创建键时设 35 天 TTL · 失败仅 warning 不阻塞。"""
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
