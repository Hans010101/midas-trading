"""Celery beat · 加密永续合约虚拟仓资金费结算(每 UTC 整点 · ADR-0020 Block 1 · M2-C.2.2)。

每个整点跑一次,对每个活仓按【其币各自结算周期】对齐判断(`hour % interval == 0`),
是则按方向 / 仓位 notional / 该币当时资金费率计费。计费走 perp_funding.settle_funding:
- E4=A:只扣虚拟现金 cash_balance(允许为负),不联动强平(强平仍只看价格,在 perp_liquidation)。
- E5:写 virtual_perp_funding 流水 + position.funding_paid 累加。
- 幂等:(position_id, funding_ts) 唯一 · 同整点重跑不重复扣。

价 / 费率 / 周期来源:crypto_premium_index 最新行(M2-C.2.1 premiumIndex 采集 ·
mark_price + last_funding_rate + funding_interval_hours)· 活仓 symbol 通常很少 → 逐 symbol
select_latest_premium_index 即可(复用 2.1,不新增 CH helper)。

🔴 红线:全程【虚拟资金】· 只读行情结算 · 绝不接真实资金费 / 转账 / 下单。
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import clickhouse_connect
from celery import shared_task
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.perp import VirtualPerpPosition
from app.services.clickhouse_crypto import select_latest_premium_index
from app.services.virtual_trading.perp_funding import PremiumSnapshot, settle_funding

logger = logging.getLogger(__name__)


async def _get_ch_client() -> Any:
    """raw clickhouse async client · UTC tz(0002 教训 · 跟采集 worker 一致)。"""
    return await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
        settings={"session_timezone": "UTC"},
    )


async def _settle_funding() -> dict[str, int]:
    engine = create_async_engine(
        os.environ["DATABASE_URL"], future=True, poolclass=NullPool,
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    ch: Any = None
    try:
        async with session_maker() as session:
            now = datetime.now(tz=UTC)
            # 活仓涉及的 symbol(去重)· 通常很少
            symbols = (
                await session.scalars(
                    select(distinct(VirtualPerpPosition.symbol)).where(
                        VirtualPerpPosition.closed_at.is_(None),
                    ),
                )
            ).all()
            if not symbols:
                return {"settled": 0, "skipped": 0}

            # 逐 symbol 取最新 premium(mark + rate + interval)· 复用 2.1 helper
            ch = await _get_ch_client()
            premium_by_symbol: dict[str, PremiumSnapshot] = {}
            for sym in symbols:
                pi = await select_latest_premium_index(ch, str(sym))
                if pi is None:
                    continue
                premium_by_symbol[str(sym)] = PremiumSnapshot(
                    mark_price=Decimal(str(pi.mark_price)),
                    funding_rate=Decimal(str(pi.last_funding_rate)),
                    funding_interval_hours=pi.funding_interval_hours,
                )

            result = await settle_funding(session, premium_by_symbol, now=now)
            await session.commit()
        return result
    finally:
        if ch is not None:
            await ch.close()
        await engine.dispose()


@shared_task(name="tasks.perp.settle_funding")
def settle_funding_task() -> dict[str, int]:
    """Celery 入口 · sync wrapper · 每 UTC 整点跑。"""
    result = asyncio.run(_settle_funding())
    if result["settled"]:
        logger.info(
            "[perp.funding] 本轮结算 %d 仓(跳过 %d)",
            result["settled"], result["skipped"],
        )
    return result
