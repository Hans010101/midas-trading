"""托管交易 worker(托管交易 PR-2 开仓 · PR-3 加平仓)· 🔴纯虚拟绝不真单。

open_scan(beat):守卫 → 选偏多 transition → 去重/≤5 → route_open_perp(LONG/100U/5x)→ 标 managed。
★开关默认 OFF · run_managed_open 内守卫,关着时立刻 skip(零下单)。
★mark 价源照 conditional_orders / perp_liquidation:真标记价(premium_index)优先 + perp ticker 兜底。
"""

from __future__ import annotations

import asyncio
import logging
import os
from decimal import Decimal
from typing import Any

import clickhouse_connect
from celery import shared_task
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.services.clickhouse_crypto import (
    select_premium_index_marks,
    select_tickers_by_symbols,
)
from app.services.virtual_trading.managed.open import run_managed_open

logger = logging.getLogger(__name__)

_QUOTES = ("USDT", "USDC", "BUSD", "FDUSD")


def _to_ccxt(binance_symbol: str) -> str:
    for q in _QUOTES:
        if binance_symbol.endswith(q) and len(binance_symbol) > len(q):
            return f"{binance_symbol[: -len(q)]}/{q}"
    return binance_symbol


async def _get_raw_ch() -> Any:
    return await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
        settings={"session_timezone": "UTC"},
    )


async def _open() -> dict[str, Any]:
    redis = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True,
    )
    engine = create_async_engine(os.environ["DATABASE_URL"], future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    raw_ch = await _get_raw_ch()

    async def get_mark_price(symbol: str) -> Decimal | None:
        # 真标记价(premium_index)优先 + perp ticker 兜底(照 conditional_orders / perp_liquidation)
        marks = await select_premium_index_marks(raw_ch, [symbol])
        m = marks.get(symbol)
        if m is not None and m > 0:
            return m
        tickers = await select_tickers_by_symbols(
            raw_ch, instrument="perp", symbols=[_to_ccxt(symbol)],
        )
        t = tickers.get(_to_ccxt(symbol))
        return Decimal(str(t.last_price)) if t and t.last_price > 0 else None

    try:
        async with session_maker() as session:
            return await run_managed_open(session, redis, get_mark_price)
    finally:
        await redis.aclose()
        await engine.dispose()
        await raw_ch.close()


@shared_task(name="tasks.managed.open_scan", max_retries=0)
def managed_open_scan() -> dict[str, Any]:
    """托管开仓入口(beat)· 守卫不过立刻 skip · 选偏多 transition → 开仓 → 标 managed。"""
    result = asyncio.run(_open())
    logger.info("[managed] open_scan · %s", result)
    return result
