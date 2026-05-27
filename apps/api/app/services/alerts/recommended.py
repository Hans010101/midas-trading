"""推荐告警规则集 + 一键应用 · 0026 G5 · DP-G5-2/DP-G5-3。

RECOMMENDED_ALERT_RULES 是【单一事实源】· 网页「一键应用」与 bot「一键推荐」共用。
新用户面对 20 个指标会发懵 → 给一套开箱即用的推荐(Tier1 全局情绪/宽度 + Tier2 demo
自选 RSI 超买超卖)。

🔴 安全:apply_recommended_rules 的 user_id 由【调用方注入】(网页=登录用户 / bot=已验证
chat 解析),推荐集本身【不含 user_id】—— 绝不从输入参数取身份。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from app.models.alert_rule import AlertRule
from app.services.alerts.engine import MAX_RULES_PER_USER
from app.services.alerts.registry import get_indicator

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class RecommendedRule:
    market: str
    symbol: str | None  # None = 市场级 / 全局(无需 symbol)
    indicator: str
    operator: str  # gt / gte / lt / lte
    threshold: float
    timeframe: str | None = None


# 9 条(0026 §4.2)· Tier1 全局 3 + Tier2 per-symbol(绑 3 个 demo 自选)6
RECOMMENDED_ALERT_RULES: tuple[RecommendedRule, ...] = (
    # Tier1 · 全局 / 市场级(无需 symbol)
    RecommendedRule("crypto", None, "fear_greed", "lt", 20),       # 极度恐慌
    RecommendedRule("crypto", None, "fear_greed", "gt", 80),       # 极度贪婪
    RecommendedRule("cn", None, "cn_breadth_up_ratio", "lt", 30),  # A股普跌
    # Tier2 · per-symbol RSI 超买超卖(绑 demo 自选)
    RecommendedRule("us", "NVDA", "rsi_14", "gt", 70, "1d"),
    RecommendedRule("us", "NVDA", "rsi_14", "lt", 30, "1d"),
    RecommendedRule("cn", "600519", "rsi_14", "gt", 70, "1d"),
    RecommendedRule("cn", "600519", "rsi_14", "lt", 30, "1d"),
    RecommendedRule("crypto", "BTC/USDT", "rsi_14", "gt", 75, "1d"),
    RecommendedRule("crypto", "BTC/USDT", "rsi_14", "lt", 25, "1d"),
)


async def apply_recommended_rules(
    db: AsyncSession, user_id: UUID,
) -> tuple[int, int]:
    """给 user_id 批量建推荐规则;跳过已存在 / 超 DP6 上限。返回 (created, skipped)。

    🔴 user_id 是入参(调用方从登录态 / 已验证 chat 注入),不取自推荐集。幂等:重复
    调用不会重复建(按 指标+市场+symbol+算子+阈值 去重)。
    """
    existing = list(
        await db.scalars(select(AlertRule).where(AlertRule.user_id == user_id)),
    )
    existing_keys = {
        (r.indicator, r.market, r.symbol, r.operator, float(r.threshold))
        for r in existing
    }
    total = len(existing)
    created = 0
    skipped = 0

    for rec in RECOMMENDED_ALERT_RULES:
        indicator = get_indicator(rec.indicator)
        # 防御:指标须存在且市场适用(推荐集应都合法 · 不合法则跳过不报错)
        if indicator is None or rec.market not in indicator.markets:
            skipped += 1
            continue
        symbol = rec.symbol if indicator.requires_symbol else None
        key = (rec.indicator, rec.market, symbol, rec.operator, float(rec.threshold))
        if key in existing_keys or total >= MAX_RULES_PER_USER:
            skipped += 1
            continue
        db.add(
            AlertRule(
                user_id=user_id,
                market=rec.market,
                symbol=symbol,
                indicator=rec.indicator,
                operator=rec.operator,
                threshold=Decimal(str(rec.threshold)),
                timeframe=rec.timeframe if indicator.needs_timeframe else None,
            ),
        )
        existing_keys.add(key)
        total += 1
        created += 1

    await db.commit()
    return created, skipped
