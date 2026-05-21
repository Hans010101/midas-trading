"""Crypto Pro · 数据采集 Celery 任务(0017 ADR · M2-A-9)。

7 个任务 · 分层节奏:
- crypto.ticker_24h_scan         · 1 min   · 全 spot+perp · 600+ symbols
- crypto.funding_rate_refresh    · 8 h     · top 30 perp · 各 1 条最新
- crypto.open_interest_scan      · 5 min   · top 30 perp · 各 1 条最新
- crypto.long_short_scan         · 5 min   · top 30 perp · 各 1 条最新
- crypto.global_overview_refresh · 5 min   · CoinGecko /global
- crypto.fear_greed_refresh      · 1 day   · alternative.me · 合并到 overview
- crypto.perp_kline_incremental  · 跟周期   · top 30 perp × 4 周期

WIP(M2-A 阶段):
- top 30 perp 暂用 hard-code · M2-B 改成读 symbol_meta + watchlist 联动
- 错误处理:每标的 try/except 独立 · 一个失败不影响其他
- 写入 ClickHouse 走 clickhouse_crypto.py 的 insert_* helper

红线:本 worker 只 GET + INSERT ClickHouse 数据 · 永不调任何 trade endpoint。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import clickhouse_connect
from celery import shared_task

from app.core.config import settings
from app.services.clickhouse_crypto import (
    insert_funding_rates,
    insert_long_short,
    insert_market_overview,
    insert_open_interest,
    insert_tickers_24h,
    merge_fear_greed_into_latest_overview,
)
from app.services.data_sources.alternative_me_source import AlternativeMeSource
from app.services.data_sources.binance_futures_source import BinanceFuturesSource
from app.services.data_sources.coingecko_source import CoinGeckoSource

logger = logging.getLogger(__name__)


# Hard-coded top 30 perp symbols(Binance Futures 风格 · 无斜杠)
# M2-B 改成动态从 symbol_meta 表读 · 现在 hard-code 简单
_TOP_30_PERP: tuple[str, ...] = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "TRXUSDT", "LINKUSDT",
    "MATICUSDT", "DOTUSDT", "TONUSDT", "SHIBUSDT", "LTCUSDT",
    "UNIUSDT", "BCHUSDT", "ATOMUSDT", "ETCUSDT", "XLMUSDT",
    "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "FILUSDT",
    "INJUSDT", "SUIUSDT", "SEIUSDT", "TIAUSDT", "STXUSDT",
)


# ============================================================================
# CH async client helper · 每 task 自己建/关 · Celery 不共享 lifespan
# ============================================================================


async def _get_ch_client() -> Any:
    """建一个 ClickHouse async client · 调用方负责 close。"""
    return await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
    )


# ============================================================================
# 1 · 24h ticker scan · 1 min
# ============================================================================


@shared_task(name="tasks.crypto.ticker_24h_scan")
def ticker_24h_scan() -> dict[str, Any]:
    return asyncio.run(_ticker_24h_scan_async())


async def _ticker_24h_scan_async() -> dict[str, Any]:
    source = BinanceFuturesSource()
    ch = await _get_ch_client()
    try:
        # 拉 perp 全市场
        perp_tickers = await source.fetch_ticker_24h()
        # spot ticker 走现有 ccxt source(M2-A WIP · 暂只 perp · M2-B 加 spot)
        n = await insert_tickers_24h(ch, perp_tickers)
        logger.info("[crypto.ticker_24h_scan] perp tickers written=%d", n)
        return {"perp_count": n}
    finally:
        await source.close()
        await ch.close()


# ============================================================================
# 2 · funding rate refresh · 8h(整点触发)
# ============================================================================


@shared_task(name="tasks.crypto.funding_rate_refresh")
def funding_rate_refresh() -> dict[str, Any]:
    return asyncio.run(_funding_rate_refresh_async())


async def _funding_rate_refresh_async() -> dict[str, Any]:
    source = BinanceFuturesSource()
    ch = await _get_ch_client()
    total = 0
    ok = 0
    fail = 0
    try:
        for symbol in _TOP_30_PERP:
            try:
                items = await source.fetch_funding_rate(symbol, limit=1)
                n = await insert_funding_rates(ch, items)
                total += n
                ok += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("[crypto.funding] %s 失败:%s", symbol, exc)
                fail += 1
        logger.info("[crypto.funding_rate_refresh] written=%d ok=%d fail=%d", total, ok, fail)
        return {"written": total, "ok": ok, "fail": fail}
    finally:
        await source.close()
        await ch.close()


# ============================================================================
# 3 · open interest scan · 5 min
# ============================================================================


@shared_task(name="tasks.crypto.open_interest_scan")
def open_interest_scan() -> dict[str, Any]:
    return asyncio.run(_open_interest_scan_async())


async def _open_interest_scan_async() -> dict[str, Any]:
    source = BinanceFuturesSource()
    ch = await _get_ch_client()
    total = 0
    ok = 0
    fail = 0
    try:
        for symbol in _TOP_30_PERP:
            try:
                # 拉最近 1 条(5min 一次的 task · 每次只补一根新数据)
                items = await source.fetch_open_interest(symbol, limit=1)
                n = await insert_open_interest(ch, items)
                total += n
                ok += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("[crypto.oi] %s 失败:%s", symbol, exc)
                fail += 1
        logger.info("[crypto.open_interest_scan] written=%d ok=%d fail=%d", total, ok, fail)
        return {"written": total, "ok": ok, "fail": fail}
    finally:
        await source.close()
        await ch.close()


# ============================================================================
# 4 · long/short scan · 5 min
# ============================================================================


@shared_task(name="tasks.crypto.long_short_scan")
def long_short_scan() -> dict[str, Any]:
    return asyncio.run(_long_short_scan_async())


async def _long_short_scan_async() -> dict[str, Any]:
    source = BinanceFuturesSource()
    ch = await _get_ch_client()
    total = 0
    ok = 0
    fail = 0
    try:
        for symbol in _TOP_30_PERP:
            try:
                items = await source.fetch_long_short_ratio(symbol, limit=1)
                n = await insert_long_short(ch, items)
                total += n
                ok += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("[crypto.long_short] %s 失败:%s", symbol, exc)
                fail += 1
        logger.info("[crypto.long_short_scan] written=%d ok=%d fail=%d", total, ok, fail)
        return {"written": total, "ok": ok, "fail": fail}
    finally:
        await source.close()
        await ch.close()


# ============================================================================
# 5 · CoinGecko global overview refresh · 5 min
# ============================================================================


@shared_task(name="tasks.crypto.global_overview_refresh")
def global_overview_refresh() -> dict[str, Any]:
    return asyncio.run(_global_overview_refresh_async())


async def _global_overview_refresh_async() -> dict[str, Any]:
    source = CoinGeckoSource(api_key=getattr(settings, "coingecko_api_key", None))
    ch = await _get_ch_client()
    try:
        overview = await source.fetch_global_overview()
        # 注:此处只写 CoinGecko 字段 · FGI 字段为 0 · 由 fear_greed_refresh
        # task 通过 merge_fear_greed_into_latest_overview 合并
        n = await insert_market_overview(ch, overview)
        logger.info(
            "[crypto.global_overview_refresh] written=%d mc=%.2fT btc_dom=%.2f%%",
            n, overview.total_market_cap_usd / 1e12, overview.btc_dominance,
        )
        return {"written": n}
    finally:
        await source.close()
        await ch.close()


# ============================================================================
# 6 · Fear & Greed refresh · 1 day(UTC 00:30)
# ============================================================================


@shared_task(name="tasks.crypto.fear_greed_refresh")
def fear_greed_refresh() -> dict[str, Any]:
    return asyncio.run(_fear_greed_refresh_async())


async def _fear_greed_refresh_async() -> dict[str, Any]:
    source = AlternativeMeSource()
    ch = await _get_ch_client()
    try:
        # 拉最近 30 天 · 合并最新一条到 overview 表
        fgi_series = await source.fetch_fear_greed(limit=30)
        if not fgi_series:
            logger.warning("[crypto.fear_greed_refresh] alternative.me 没数据")
            return {"written": 0, "fgi_value": None}
        latest = fgi_series[-1]
        n = await merge_fear_greed_into_latest_overview(
            ch,
            fgi_value=latest.value,
            fgi_classification=latest.classification,
        )
        logger.info(
            "[crypto.fear_greed_refresh] written=%d FGI=%d (%s)",
            n, latest.value, latest.classification,
        )
        return {"written": n, "fgi_value": latest.value, "classification": latest.classification}
    finally:
        await source.close()
        await ch.close()


# ============================================================================
# 7 · Perp K 线增量 · 跟周期(M2-A 留 stub · M2-B 联调时实装)
# ============================================================================


@shared_task(name="tasks.crypto.perp_kline_incremental")
def perp_kline_incremental() -> dict[str, Any]:
    """top 30 perp × 4 周期(15m / 1h / 4h / 1d)各 1 根最新。

    M2-A 阶段先留 stub · M2-B 联调时:
    - 实际拉 perp K 线 · 写 kline 表 instrument='perp'
    - 这部分依赖现有 ClickHouseClient.insert_kline · 但要扩支持 instrument 列
    - 暂时直接绕过 ClickHouseClient · 用 raw SQL 写
    """
    logger.info("[crypto.perp_kline_incremental] WIP · M2-A 留 stub · M2-B 实装")
    return {"stub": True, "note": "M2-B 联调时实装"}


# ============================================================================
# Beat schedule(M2-A · 不进 celery_config.py · 给 M2-A 联调脚本用)
# ============================================================================
# 联调时把下面 dict 加到 apps/worker/config/celery_config.py 的 beat_schedule:
#
#   "crypto-ticker-24h-scan":         crontab(minute="*"),                # 1 min
#   "crypto-open-interest-scan":      crontab(minute="*/5"),              # 5 min
#   "crypto-long-short-scan":         crontab(minute="*/5"),              # 5 min
#   "crypto-global-overview-refresh": crontab(minute="*/5"),              # 5 min
#   "crypto-funding-rate-refresh":    crontab(minute="5", hour="*/8"),    # 8h · 错峰 5min
#   "crypto-fear-greed-refresh":      crontab(hour="0", minute="30"),     # daily UTC 00:30 · CN 08:30
#   "crypto-perp-kline-incremental":  crontab(minute="*/15"),             # 跟最小周期 15m
