"""Crypto Pro · 数据采集 Celery 任务(0017 ADR · M2-A-9)。

6 个采集任务 · 分层节奏(ADR-0018 起合约维度全量覆盖 USDT 永续 ~527):
- crypto.ticker_24h_scan         · 全 perp · 单请求拉全市场
- crypto.funding_rate_refresh    · 全量 USDT 永续 · 各 1 条最新
- crypto.open_interest_scan      · 全量 USDT 永续 · 各 1 条最新
- crypto.long_short_scan         · 全量 USDT 永续 · 各取最近 4 点(覆盖 15min 轮间隔)
- crypto.global_overview_refresh · CoinGecko /global
- crypto.fear_greed_refresh      · alternative.me · 合并到 overview

注:M2-B 的 perp K 线增量任务(crypto.perp_kline_incremental)不在本文件 ·
留在 feature/m2-crypto-pro 分支 · A1 纯实时回源,暂不接入。

采集名单:_all_usdt_perp_symbols() 从 crypto_ticker_24h 全量取 USDT 永续(不截断);
冷启动回退 _TOP_30_PERP 种子。
- 错误处理:每标的 try/except 独立 · 一个失败不影响其他
- 写入 ClickHouse 走 clickhouse_crypto.py 的 insert_* helper

红线:本 worker 只 GET + INSERT ClickHouse 数据 · 永不调任何 trade endpoint。
"""

from __future__ import annotations

import asyncio
import logging
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
# ADR-0018 起,常态用 _all_usdt_perp_symbols() 从 crypto_ticker_24h 全量取 USDT 永续;
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


async def _all_usdt_perp_symbols(ch: Any) -> list[str]:
    """全量取 Binance USDT 本位永续合约 · 返回 Binance 风格(无斜杠)。

    ADR-0018:采集层全量覆盖(~527 个 USDT 永续),展示层任意排序/筛选解耦——
    不再用「成交额 top100」截断(否则跌幅榜 / 按资金费率·OI 排序时,需要的币
    不在 top100 里 → 无数据)。

    数据来自 ticker_24h_scan 已落库的 crypto_ticker_24h(全市场 perp,~600+)·
    只取 quote=USDT(ccxt 风格以 '/USDT' 结尾)· 仍按成交额降序返回(只影响采集
    顺序、不截断,热门币先采)。冷启动(ticker 表还空)时回退 _TOP_30_PERP 种子,
    名单永不为空。crypto_ticker_24h 里 symbol 是 ccxt 风格 'BTC/USDT',这里转成
    Binance 风格 'BTCUSDT'(futures 端点要求)。
    """
    try:
        result = await ch.query(
            """
            SELECT symbol FROM (
                SELECT symbol, quote_volume_24h,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY ts DESC) AS rn
                FROM crypto_ticker_24h FINAL
                WHERE instrument = 'perp' AND endsWith(symbol, '/USDT')
            )
            WHERE rn = 1
            ORDER BY quote_volume_24h DESC
            """,
        )
        symbols = [str(r[0]).replace("/", "") for r in result.result_rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("[crypto] 全量取 USDT 永续名单失败 · 回退 _TOP_30_PERP 种子:%s", exc)
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
        symbols = await _all_usdt_perp_symbols(ch)
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
        symbols = await _all_usdt_perp_symbols(ch)
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
        symbols = await _all_usdt_perp_symbols(ch)
        for symbol in symbols:
            try:
                # limit 必须 >1:fetch_long_short_ratio 把 3 个上游 endpoint
                # (account / position / taker)按 timestamp **交集** 合并;limit=1 时
                # 三者各自最新的 5min 桶 ts 常常错位 → 交集为空 → 合并出 0 行。
                # ADR-0018 配套①:96 → 4。多空比 5min 栅格、本 task 15min 一轮,只需补
                # ~3 个新点;limit=4 已覆盖 20min 窗口、保证三上游有重叠 ts。砍掉 ~24×
                # 写放大(全量 ~527 币 × 96 行 = 巨量 insert + CH merge 压力)+ 大幅缩短
                # 单轮耗时(消除超 expires 风险)。详情页历史窗口由 CH 累积提供,不靠单轮灌满。
                items = await source.fetch_long_short_ratio(symbol, limit=4)
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
# Beat schedule(M2-A · 不进 celery_config.py · 合入 main 后任务不自动跑)
# ============================================================================
# 本文件 6 个 M2-A 采集任务【没有】接 celery_config.py 的 beat_schedule ·
# 合入 main 后不会被定时调度 · 首轮数据靠手动 docker exec 触发(见 M2-D 部署说明)。
# M2-A 正式验收后,若要常驻定时,再把下面 dict 加到 beat_schedule:
#
#   "crypto-ticker-24h-scan":         crontab(minute="*"),                # 1 min
#   "crypto-open-interest-scan":      crontab(minute="*/5"),              # 5 min
#   "crypto-long-short-scan":         crontab(minute="*/5"),              # 5 min
#   "crypto-global-overview-refresh": crontab(minute="*/5"),              # 5 min
#   "crypto-funding-rate-refresh":    crontab(minute="5", hour="*/8"),    # 8h · 错峰 5min
#   "crypto-fear-greed-refresh":      crontab(hour="0", minute="30"),     # daily UTC 00:30 · CN 08:30
