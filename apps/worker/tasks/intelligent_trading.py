"""智能交易 worker(智能交易 PR-4 开仓 · PR-5 平仓)· 🔴纯虚拟绝不真单。

- open_scan(beat):★守卫第一行(开关 OFF→skip · 空转零副作用)→ 打分共振决策 → route_open_perp
  做多做空 → 标 intelligent + 记止损/止盈/共振。
★mark 价源照 managed_trading / conditional:真标记价(premium_index)优先 + perp ticker 兜底。
★平仓 close_scan = PR-5(本文件后续加)。
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
from app.services.virtual_trading.intelligent.open import run_intelligent_open

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
    """get_mark_price 闭包 · 真标记价(premium_index)优先 + perp ticker 兜底(照 managed)。"""
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


async def _run_open() -> dict[str, Any]:
    redis = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True,
    )
    engine = create_async_engine(os.environ["DATABASE_URL"], future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    raw_ch = await _get_raw_ch()
    fetcher = _make_mark_price(raw_ch)
    try:
        async with session_maker() as session:
            return await run_intelligent_open(session, redis, fetcher)
    finally:
        await redis.aclose()
        await engine.dispose()
        await raw_ch.close()


@shared_task(name="tasks.intelligent.open_scan", max_retries=0)
def intelligent_open_scan() -> dict[str, Any]:
    """智能交易开仓入口(beat)· ★守卫不过立刻 skip(空转零副作用)· 打分共振 → 做多做空。"""
    result = asyncio.run(_run_open())
    logger.info("[intelligent] open_scan · %s", result)
    return result
