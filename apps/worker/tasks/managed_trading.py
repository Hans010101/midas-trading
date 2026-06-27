"""托管交易 worker(托管交易 PR-2 开仓 + PR-3 平仓)· 🔴纯虚拟绝不真单。

- open_scan(beat):守卫(开关 OFF→skip)→ 选偏多 transition → 去重/≤5 → route_open_perp → 标 managed。
- close_scan(beat):★【不被开关拦】监控所有 managed 活仓 → TP/信号/超时 → route_close_perp + 记原因。
  关开关只停新开仓,已有仓仍被平(否则禁强平+不监控=永不平)。无活仓时空转。
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
from app.services.virtual_trading.managed.close import run_managed_close
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


def _make_mark_price(raw_ch: Any) -> Any:
    """get_mark_price 闭包 · 真标记价(premium_index)优先 + perp ticker 兜底(照 conditional)。"""
    async def get_mark_price(symbol: str) -> Decimal | None:
        marks = await select_premium_index_marks(raw_ch, [symbol])
        m = marks.get(symbol)
        if m is not None and m > 0:
            return m
        tickers = await select_tickers_by_symbols(
            raw_ch, instrument="perp", symbols=[_to_ccxt(symbol)],
        )
        t = tickers.get(_to_ccxt(symbol))
        return Decimal(str(t.last_price)) if t and t.last_price > 0 else None

    return get_mark_price


async def _run(which: str) -> dict[str, Any]:
    """共用环境(redis/pg/ch + fetcher)· which='open' 走开仓,'close' 走平仓监控。"""
    redis = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True,
    )
    engine = create_async_engine(os.environ["DATABASE_URL"], future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    raw_ch = await _get_raw_ch()
    fetcher = _make_mark_price(raw_ch)
    try:
        async with session_maker() as session:
            if which == "open":
                return await run_managed_open(session, redis, fetcher)
            return await run_managed_close(session, redis, fetcher)
    finally:
        await redis.aclose()
        await engine.dispose()
        await raw_ch.close()


@shared_task(name="tasks.managed.open_scan", max_retries=0)
def managed_open_scan() -> dict[str, Any]:
    """托管开仓入口(beat)· 守卫不过立刻 skip · 选偏多 transition → 开仓 → 标 managed。"""
    result = asyncio.run(_run("open"))
    logger.info("[managed] open_scan · %s", result)
    return result


@shared_task(name="tasks.managed.close_scan", max_retries=0)
def managed_close_scan() -> dict[str, Any]:
    """托管平仓监控(beat)· ★不被开关拦 · 监控所有 managed 活仓 → TP/信号/超时 → 平仓 + 记原因。"""
    result = asyncio.run(_run("close"))
    logger.info("[managed] close_scan · %s", result)
    return result
