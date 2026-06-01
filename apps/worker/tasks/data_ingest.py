"""演示数据回填 worker tasks。

M0 阶段只回填 3 个 demo 标的(贵州茅台 / NVDA / BTC/USDT)各 ~2000 根日 K,
不做全市场。全市场回填是 04 文档 Task 2.4 的完整版,放在 M0 之后。

调用方式:
- Celery 调度:`backfill_kline.delay("600519", "cn", "贵州茅台")` —— 由 broker 派发
- 命令行直跑:`python -m tasks.data_ingest` —— 同步跑 3 个 demo 标的
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import ccxt.async_support as ccxt_async
from celery import shared_task

from app.core.logging import configure_logging
from app.schemas.market import Market, Period, SymbolMeta
from app.services.clickhouse_client import ClickHouseClient
from app.services.data_sources.cn_source import AKShareCnSource
from app.services.data_sources.crypto_source import CcxtBinanceCryptoSource
from app.services.data_sources.exceptions import DataSourceError
from app.services.data_sources.hk_source import AKShareHkSource
from app.services.data_sources.us_source import YFinanceUsSource

logger = logging.getLogger(__name__)

# M0 demo:3 标的(symbol, market, 中文名)
DEMO_SYMBOLS: list[tuple[str, Market, str]] = [
    ("600519", "cn", "贵州茅台"),
    ("NVDA", "us", "NVIDIA Corporation"),
    ("BTC/USDT", "crypto", "Bitcoin"),
]


async def _backfill_one(
    symbol: str,
    market: Market,
    name: str,
    period: Period,
    limit: int,
) -> dict[str, Any]:
    """单标的回填:fetch upstream → 写 CH kline → upsert symbol_meta。

    ccxt async exchange 在本函数内创建并 close —— Celery 任务的事件循环是
    一次性的(asyncio.run 每次新建 loop),不能复用 FastAPI lifespan 的单例。
    """
    ch = await ClickHouseClient.create()
    exchange: ccxt_async.binance | None = None
    try:
        if market == "cn":
            source: (
                AKShareCnSource | YFinanceUsSource | AKShareHkSource | CcxtBinanceCryptoSource
            )
            source = AKShareCnSource()
        elif market == "us":
            source = YFinanceUsSource()
        elif market == "hk":
            source = AKShareHkSource()  # 港股(akshare)· ADR 0034a P1-3
        elif market == "crypto":
            exchange = ccxt_async.binance({"enableRateLimit": True, "timeout": 30_000})
            source = CcxtBinanceCryptoSource(exchange=exchange)
        else:
            msg = f"unknown market: {market}"
            raise ValueError(msg)

        rows = await source.fetch_kline(symbol, period, limit=limit)
        written = await ch.insert_kline(
            rows, symbol=symbol, market=market, period=period,
        )
        await ch.upsert_symbol_meta(
            [
                SymbolMeta(
                    symbol=symbol,
                    market=market,
                    name=name,
                    updated_at=datetime.now(tz=UTC),
                ),
            ],
        )
        return {
            "symbol": symbol,
            "market": market,
            "fetched_rows": len(rows),
            "ch_new_rows": written,
        }
    finally:
        if exchange is not None:
            await exchange.close()
        await ch.close()


@shared_task(
    bind=True,
    name="tasks.data_ingest.backfill_kline",
    max_retries=3,
    default_retry_delay=60,
)
def backfill_kline(
    self: Any,
    symbol: str,
    market: Market,
    name: str,
    period: Period = "1d",
    limit: int = 2000,
) -> dict[str, Any]:
    """Celery 任务:回填指定标的的 K 线 + upsert symbol_meta。失败自动重试 3 次。"""
    try:
        return asyncio.run(_backfill_one(symbol, market, name, period, limit))
    except DataSourceError as exc:
        logger.warning(
            "backfill_kline %s/%s 失败,重试 %d/3:%s",
            symbol, market, self.request.retries + 1, exc,
            exc_info=True,
        )
        raise self.retry(exc=exc) from exc


def demo_backfill_sync() -> list[dict[str, Any]]:
    """同步跑 3 个 demo 标的的日 K(不经过 broker),用于 F5 演示和验证。"""
    configure_logging()
    results: list[dict[str, Any]] = []
    for symbol, market, name in DEMO_SYMBOLS:
        try:
            r = asyncio.run(_backfill_one(symbol, market, name, "1d", 2000))
        except DataSourceError as e:
            logger.exception("演示回填失败 %s/%s", symbol, market)
            r = {"symbol": symbol, "market": market, "error": str(e)}
        results.append(r)
        logger.info("演示回填结果:%s", r)
    return results


# Task 3 启动前的数据预热:3 标的 × 4 周期 × 各 500 根
# 保证 KLineChart 周期切换器 4 档(15m / 1h / 1d / 1w)切过去都有数据
_PRE_TASK3_PERIODS: list[tuple[Period, int]] = [
    ("15m", 500),
    ("1h", 500),
    ("1d", 500),
    ("1w", 500),
]


def demo_backfill_all_periods() -> list[dict[str, Any]]:
    """3 标的 × 4 周期 × 各 500 根。Task 3 启动前的演示数据预热。

    AKShare 分钟 K 走 EM(目前不稳,可能失败);Sina 走日/周(稳定)。
    失败的不阻塞后续,记到 results 里。
    """
    configure_logging()
    results: list[dict[str, Any]] = []
    for symbol, market, name in DEMO_SYMBOLS:
        for period, limit in _PRE_TASK3_PERIODS:
            try:
                r = asyncio.run(_backfill_one(symbol, market, name, period, limit))
            except DataSourceError as e:
                logger.exception("预热失败 %s/%s @%s", symbol, market, period)
                r = {
                    "symbol": symbol,
                    "market": market,
                    "period": period,
                    "error": str(e),
                }
            results.append(r)
            logger.info("预热进度:%s", r)
    return results


if __name__ == "__main__":
    import sys

    if "--all-periods" in sys.argv:
        print(demo_backfill_all_periods())
    else:
        print(demo_backfill_sync())
