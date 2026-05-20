"""ai_usage_log 写入 helper · 0012 ADR § 监控。

每次真实 LLM 调用后写一行 · mock 模式不写(避免污染统计)。
失败仅 log · 不阻塞主链路(用户已经看到决策卡了)。
"""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.models.ai_usage import AIUsageLog
from app.schemas.market import Market, Period

logger = logging.getLogger(__name__)

# DeepSeek-V4-Flash 单价(0012 § 当前定价)· USD/M tokens
_PRICE_INPUT_MISS_USD_PER_M = 0.14
_PRICE_OUTPUT_USD_PER_M = 0.28
_USD_TO_CNY = 7.2  # 估算汇率


def estimate_cost_cny(prompt_tokens: int, completion_tokens: int) -> Decimal:
    """简化成本估算 · 不考虑 prefix cache(M2+ 接入 cache hit/miss 区分)。"""
    cost_usd = (
        prompt_tokens / 1_000_000 * _PRICE_INPUT_MISS_USD_PER_M
        + completion_tokens / 1_000_000 * _PRICE_OUTPUT_USD_PER_M
    )
    return Decimal(str(cost_usd * _USD_TO_CNY)).quantize(Decimal("0.000001"))


async def log_usage(
    *,
    market: Market,
    symbol: str,
    period: Period,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    node: str,
    status: str,
) -> None:
    """写一行 ai_usage_log · 失败仅 log。"""
    try:
        cost = estimate_cost_cny(prompt_tokens, completion_tokens)
        session: AsyncSession
        async with async_session_factory() as session:
            session.add(
                AIUsageLog(
                    market=market,
                    symbol=symbol,
                    period=period,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    cost_cny=cost,
                    node=node,
                    status=status,
                ),
            )
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("[ai.usage] log failed err=%s", e)
