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


# 冷启动种子名单(Binance Futures 风格 · 无斜杠)。
# M2-数据打磨·任务2 起,常态用 _top_perp_symbols() 从 crypto_ticker_24h 动态取 top100;
# 仅当 ticker 表还空(首轮 ticker_24h_scan 未跑)时回退到本种子,保证名单永不为空。
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
        # 跟 ClickHouseClient.create()(能正常写的 kline 路径)对齐 ·
        # 否则 tz 写读按 server 本地时区误转 · 0002 教训
        settings={"session_timezone": "UTC"},
    )


# 采集名单上限(M2-数据打磨·任务2:top30 → top100)
_TOP_N_PERP = 100


async def _top_perp_symbols(ch: Any, *, limit: int = _TOP_N_PERP) -> list[str]:
    """动态取「按 24H 成交额降序」前 N 个 perp 合约 · 返回 Binance 风格(无斜杠)。

    数据来自 ticker_24h_scan 已落库的 crypto_ticker_24h(全市场 ~600 perp)·
    不再硬编码 _TOP_30_PERP。冷启动(ticker 表还空)时回退到 _TOP_30_PERP 种子,
    保证名单永不为空。crypto_ticker_24h 里 symbol 是 ccxt 风格 'BTC/USDT',
    这里转成 Binance 风格 'BTCUSDT'(futures 端点要求)。
    """
    try:
        result = await ch.query(
            """
            SELECT symbol FROM (
                SELECT symbol, quote_volume_24h,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY ts DESC) AS rn
                FROM crypto_ticker_24h FINAL
                WHERE instrument = 'perp'
            )
            WHERE rn = 1
            ORDER BY quote_volume_24h DESC
            LIMIT %(n)s
            """,
            parameters={"n": limit},
        )
        symbols = [str(r[0]).replace("/", "") for r in result.result_rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("[crypto] 动态取 top%d 名单失败 · 回退 _TOP_30_PERP:%s", limit, exc)
        return list(_TOP_30_PERP)
    if not symbols:
        logger.info("[crypto] ticker 表暂空 · 采集名单回退 _TOP_30_PERP 种子")
        return list(_TOP_30_PERP)
    return symbols


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
        symbols = await _top_perp_symbols(ch)
        for symbol in symbols:
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
        symbols = await _top_perp_symbols(ch)
        for symbol in symbols:
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
        symbols = await _top_perp_symbols(ch)
        for symbol in symbols:
            try:
                # limit 必须 >1:fetch_long_short_ratio 把 3 个上游 endpoint
                # (account / position / taker)按 timestamp **交集** 合并;limit=1 时
                # 三者各自最新的 5min 桶 ts 常常错位 → 交集为空 → 合并出 0 行
                # → ok+1 但 written+0(数据拉到了没落库)。拉一段窗口保证有重叠 ts,
                # 同时一次把详情页要展示的窗口(96 点 ≈ 8h)灌满。
                items = await source.fetch_long_short_ratio(symbol, limit=96)
                n = await insert_long_short(ch, items)
                if n == 0:
                    # 合并后仍 0 行 = 三个上游 ts 完全无交集(异常)· 显式记日志,
                    # 不再让 written=0 静默(本次 written=0 排查就卡在这)。
                    logger.warning(
                        "[crypto.long_short] %s 合并后 0 行 · 三上游 ts 无交集", symbol,
                    )
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
# 7 · Perp K 线增量(M2-B-4 实装 · 替换 M2-A stub)
# ============================================================================


# top 30 perp × 3 周期 · 每周期取最近 N 根 · 覆盖任何短停机窗口
# 4h 周期暂不发(Period Literal 不含)· M2-D 改 Period 加 4h 时一起加
_PERP_PERIODS_M2B: tuple[tuple[str, int], ...] = (
    ("15m", 5),
    ("1h", 5),
    ("1d", 3),
)


@shared_task(name="tasks.crypto.perp_kline_incremental")
def perp_kline_incremental() -> dict[str, Any]:
    """top 30 perp × 3 周期(15m / 1h / 1d)各最近几根 · M2-B-4 实装。

    走 BinanceFuturesSource → ClickHouseClient.insert_kline(instrument='perp')。
    幂等 · 重复 ts 自动 skip(ClickHouseClient 内部去重)。
    """
    return asyncio.run(_perp_kline_incremental_async())


async def _perp_kline_incremental_async() -> dict[str, Any]:
    # 延迟 import · 避免 worker 启动时把整个 app.services 都拉起来
    from app.services.clickhouse_client import ClickHouseClient
    from app.services.data_sources.binance_futures_source import (
        BinanceFuturesSource,
        _to_ccxt_symbol,
    )

    source = BinanceFuturesSource()
    ch = await ClickHouseClient.create()
    total_written = 0
    ok_count = 0
    fail_count = 0
    try:
        for symbol in _TOP_30_PERP:
            # symbol 在 CH 用 ccxt 风格 BTC/USDT(跟 spot 表对齐 · 0017 ADR § 2)
            ccxt_symbol = _to_ccxt_symbol(symbol)
            for period, limit in _PERP_PERIODS_M2B:
                try:
                    klines = await source.fetch_kline(symbol, period, limit=limit)  # type: ignore[arg-type]
                    if not klines:
                        continue
                    n = await ch.insert_kline(
                        klines,
                        symbol=ccxt_symbol,
                        market="crypto",
                        period=period,  # type: ignore[arg-type]
                        instrument="perp",
                    )
                    total_written += n
                    ok_count += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[crypto.perp_kline] %s/%s 失败: %s", symbol, period, exc,
                    )
                    fail_count += 1
        logger.info(
            "[crypto.perp_kline_incremental] written=%d ok=%d fail=%d",
            total_written, ok_count, fail_count,
        )
        return {"written": total_written, "ok": ok_count, "fail": fail_count}
    finally:
        await source.close()
        await ch.close()


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
