"""Celery beat · 条件单触发扫描(ADR 0041 刀2 · 照 perp_liquidation 母版)。

每 60s 扫 ACTIVE 条件单(beat 注册见 config/celery_config.py):
  价格源 —— spot 用 CH 日K最新 close(与手动下单 make_price_fetcher 同源);
  perp 用真标记价 premiumIndex 优先 + perp ticker 兜底(照强平)。
  股票市场(cn/us/hk)非交易时段整组跳过(compute_market_status · cn 接真交易日历);
  crypto 7×24 恒扫。触发判断与成交在内核 process_active_conditionals(api 包 · 依赖注入)。

🔴 红线:成交只走唯一入口(内核里 place_market_order / route_close_perp)· 本壳只做装配:
  engine/session、CH client、日历、注入函数、commit、perp 通知 emit。
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import clickhouse_connect
from celery import shared_task
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.conditional_order import ConditionalOrder, ConditionalStatus
from app.services.clickhouse_client import ClickHouseClient
from app.services.clickhouse_crypto import (
    select_premium_index_marks,
    select_tickers_by_symbols,
)
from app.services.clickhouse_market_home import select_trade_days
from app.services.market_calendar import compute_market_status
from app.services.notifications.emit import emit_perp_order
from app.services.virtual_trading.conditional_trigger import (
    process_active_conditionals,
)

logger = logging.getLogger(__name__)

_QUOTES = ("USDT", "USDC", "BUSD", "FDUSD")


def _to_ccxt(binance_symbol: str) -> str:
    """'BTCUSDT' → 'BTC/USDT'(perp ticker 表 ccxt 风格 · 照 perp_liquidation)。"""
    for q in _QUOTES:
        if binance_symbol.endswith(q) and len(binance_symbol) > len(q):
            return f"{binance_symbol[: -len(q)]}/{q}"
    return binance_symbol


async def _get_raw_ch() -> Any:
    """raw clickhouse async client(UTC tz · 0002 教训 · 照 perp_liquidation)。"""
    return await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
        settings={"session_timezone": "UTC"},
    )


async def _scan_once() -> dict[str, int]:
    engine = create_async_engine(
        os.environ["DATABASE_URL"], future=True, poolclass=NullPool,
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    raw_ch: Any = None
    app_ch: ClickHouseClient | None = None
    try:
        async with session_maker() as session:
            # 早退:无 ACTIVE 单不建 CH 连接(beat 每分钟跑 · 空转零成本)
            active_count = await session.scalar(
                select(func.count()).select_from(ConditionalOrder).where(
                    ConditionalOrder.status == ConditionalStatus.ACTIVE,
                ),
            )
            if not active_count:
                return {"active": 0}

            raw_ch = await _get_raw_ch()
            app_ch = await ClickHouseClient.create()

            # 股票开市判定:cn 接真交易日历(空集自动回退周一至五 · market_calendar 约定)
            now = datetime.now(UTC)
            today = now.date()
            cn_days = await select_trade_days(
                raw_ch, market="cn", since=today - timedelta(days=7),
                until=today + timedelta(days=1),
            )

            def is_market_open(market: str) -> bool:
                if market == "crypto":
                    return True  # 7×24
                info = compute_market_status(
                    market,  # type: ignore[arg-type]
                    now_utc=now,
                    cn_trading_days=cn_days if market == "cn" else None,
                )
                return info.is_trading_now

            async def get_spot_price(symbol: str, market: str) -> Decimal | None:
                # 与手动下单 make_price_fetcher 同源:CH 日K最新 close(判价=成交价源 · 自洽)
                assert app_ch is not None  # noqa: S101 — 闭包窄化
                rows = await app_ch.select_kline(
                    symbol=symbol, market=market,  # type: ignore[arg-type]
                    period="1d", limit=1,
                )
                return Decimal(str(rows[-1].close)) if rows else None

            async def get_perp_mark(symbol: str) -> Decimal | None:
                # 真标记价优先 + perp ticker 兜底(照 perp_liquidation)
                marks = await select_premium_index_marks(raw_ch, [symbol])
                m = marks.get(symbol)
                if m is not None and m > 0:
                    return m
                tickers = await select_tickers_by_symbols(
                    raw_ch, instrument="perp", symbols=[_to_ccxt(symbol)],
                )
                t = tickers.get(_to_ccxt(symbol))
                return Decimal(str(t.last_price)) if t and t.last_price > 0 else None

            stats, perp_filled_ids = await process_active_conditionals(
                session,
                get_spot_price=get_spot_price,
                get_perp_mark=get_perp_mark,
                is_market_open=is_market_open,
            )
            await session.commit()  # 成交 + TRIGGERED/EXPIRED 同事务原子落库

        # commit 之后才 emit(照 perp.py #296:避免「通知发了但事务回滚」)
        for oid in perp_filled_ids:
            emit_perp_order(oid)

        if stats.get("triggered") or stats.get("expired"):
            logger.info("[conditional] 扫描结果 %s", stats)
        return {"active": int(active_count), **stats}
    finally:
        if raw_ch is not None:
            await raw_ch.close()
        if app_ch is not None:
            await app_ch.close()
        await engine.dispose()


@shared_task(name="tasks.conditional.scan_triggers", max_retries=0)
def scan_conditional_triggers() -> dict[str, int]:
    """beat 60s · 失败不重试(下一轮再扫 · 照强平 expires 不堆任务)。"""
    return asyncio.run(_scan_once())
