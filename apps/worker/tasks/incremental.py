"""增量更新 worker tasks。

由 Celery beat 按时调度,每个 demo 标的拉最近 ~10 根日 K,
依靠 `ClickHouseClient.insert_kline` 的去重逻辑确保只新增、不重复。

M0 范围:只 3 个 demo 标的;生产版会从 symbol_meta 列 is_active=1 全量。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from celery import shared_task

from app.services.clickhouse_client import ClickHouseClient
from app.services.data_sources.exceptions import DataSourceError
from app.services.hk_pool import HK_POOL_META, HK_POOL_SYMBOLS

# 复用 data_ingest 的核心异步函数:_backfill_one(单标的)/ _backfill_many(批量·复用单一客户端)·
# _all_usdt_perp_symbols 取全市场 USDT 永续(已按 quote_volume_24h 降序)→ 切片即成交额 Top N。
from tasks.crypto_metrics_ingest import _all_usdt_perp_symbols
from tasks.data_ingest import _backfill_many, _backfill_one

logger = logging.getLogger(__name__)

_INCREMENTAL_LIMIT = 10  # 每次只拉最近 10 根,够覆盖任何短停机窗口
# 港股池每只采最近 300 根日 K(首次充足历史 · 后续 insert 去重幂等增量)
_HK_POOL_LIMIT = 300

# KLINE-001 性能 B:预热热门标的(bot「K线」常查 → 命中缓存秒出图 · 免冷拉等待)。
# 拉够画图根数(≥ chart 的 150)· crypto=perp(对齐主体)· us/cn=spot · 范围适度(~11 只,别 big batch)。
_WARM_LIMIT = 200
_WARM_CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
# 加密 15m 已收盘 K线 Top-N 采集:
#   _CRYPTO_15M_TOPN = 成交额 Top N 永续(_all_usdt_perp_symbols 已按 quote_volume_24h 降序,切片即得)
#   _CRYPTO_15M_LIMIT = 每币 100 根(★fapi klines limit≤100 权重=1)· 15m×100≈25h · 幂等去重 ·
#     新币随每 5min 滚动窗口逐步补足图深(漏跑/新上榜自愈)。
_CRYPTO_15M_TOPN = 150
_CRYPTO_15M_LIMIT = 100
_WARM_US = [("AAPL", "Apple"), ("NVDA", "NVIDIA"), ("TSLA", "Tesla")]
_WARM_CN = [("600519", "贵州茅台"), ("000001", "平安银行"), ("300750", "宁德时代")]


@shared_task(
    bind=True,
    name="tasks.incremental.update_cn_demo",
    max_retries=3,
    default_retry_delay=60,
)
def update_cn_demo(self: Any) -> dict[str, Any]:
    """A 股 demo · 每交易日 15:30 CN 收盘后跑。"""
    try:
        return asyncio.run(_backfill_one("600519", "cn", "贵州茅台", "1d", _INCREMENTAL_LIMIT))
    except DataSourceError as exc:
        logger.warning("update_cn_demo 失败,重试 %d/3:%s", self.request.retries + 1, exc)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="tasks.incremental.update_us_demo",
    max_retries=3,
    default_retry_delay=60,
)
def update_us_demo(self: Any) -> dict[str, Any]:
    """美股 demo · 每交易日 05:30 CN(= 美东收盘后约半小时)跑。"""
    try:
        return asyncio.run(
            _backfill_one("NVDA", "us", "NVIDIA Corporation", "1d", _INCREMENTAL_LIMIT),
        )
    except DataSourceError as exc:
        logger.warning("update_us_demo 失败,重试 %d/3:%s", self.request.retries + 1, exc)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="tasks.incremental.update_crypto_demo",
    max_retries=3,
    default_retry_delay=60,
)
def update_crypto_demo(self: Any) -> dict[str, Any]:
    """加密 demo · 每 5 分钟跑。

    TODO(Task 4.3): 升级为 WebSocket 实时推送 + 1 分钟 K 落库混合方案。
    M0 用 5 分钟轮询足够 demo 验收(BTCUSDT 日 K 一天才 1 根,5 分钟轮询冗余覆盖)。
    """
    try:
        # KLINE-001:加密以 perp 为主体(详情页/chart/AI 全 perp)· demo 预采改 perp(BTCUSDT 无斜杠)·
        # 写库 instrument=perp,和读取侧对齐(原 BT/USDT spot 回填没人读 = 孤儿)。
        return asyncio.run(
            _backfill_one(
                "BTCUSDT", "crypto", "Bitcoin", "1d", _INCREMENTAL_LIMIT, instrument="perp",
            ),
        )
    except DataSourceError as exc:
        logger.warning("update_crypto_demo 失败,重试 %d/3:%s", self.request.retries + 1, exc)
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="tasks.incremental.update_hk_pool",
    max_retries=2,
    default_retry_delay=120,
)
def update_hk_pool(self: Any) -> dict[str, int]:  # noqa: ARG001
    """港股策展池日 K 采集 · 每交易日港股收盘后(16:30 HKT)· ADR 0034a P1-3。

    循环策展 ~18 只 · 每只走 _backfill_one(market='hk' · 新浪 stock_hk_daily 主源 + yfinance 备用)·
    sleep 错峰防限流。单只失败不中断整池(记 warning + 计数),整体不 retry
    (日 K 一天一根 · 漏的下一交易日补;单只异常吞掉不连累其它)。
    """
    ok = 0
    fail = 0
    for sym in HK_POOL_SYMBOLS:
        name = HK_POOL_META.get(sym, (sym, ""))[0]
        try:
            asyncio.run(_backfill_one(sym, "hk", name, "1d", _HK_POOL_LIMIT))
            ok += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("update_hk_pool %s(%s)采集失败:%s", sym, name, exc)
            fail += 1
        time.sleep(0.5)  # 错峰防限流
    logger.info("[hk-pool] 港股池采集完成 ok=%d fail=%d", ok, fail)
    return {"ok": ok, "fail": fail}


@shared_task(
    bind=True,
    name="tasks.incremental.warm_popular_klines",
    max_retries=1,
    default_retry_delay=120,
)
def warm_popular_klines(self: Any) -> dict[str, int]:  # noqa: ARG001
    """预热热门标的 1d K线进 CH(KLINE-001 性能 B)· bot「K线」常查命中缓存即秒出图,免冷拉等待。

    crypto=perp(对齐主体)· us/cn=spot · 拉 _WARM_LIMIT 根(≥ chart 150)· 单只失败不中断(记
    warning + 计数)· sleep 错峰 · 整体不 retry(下个 beat 补)。范围适度 ~11 只,别拖 worker。
    """
    ok = 0
    fail = 0
    jobs: list[tuple[str, str, str, str]] = (
        [(s, "crypto", s, "perp") for s in _WARM_CRYPTO]
        + [(s, "us", n, "spot") for s, n in _WARM_US]
        + [(s, "cn", n, "spot") for s, n in _WARM_CN]
    )
    for sym, market, name, instrument in jobs:
        try:
            asyncio.run(
                _backfill_one(sym, market, name, "1d", _WARM_LIMIT, instrument=instrument),  # type: ignore[arg-type]
            )
            ok += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("warm_popular_klines %s/%s 失败:%s", market, sym, exc)
            fail += 1
        time.sleep(0.5)  # 错峰防限流
    logger.info("[warm_popular_klines] ok=%d fail=%d", ok, fail)
    return {"ok": ok, "fail": fail}


@shared_task(
    bind=True,
    name="tasks.incremental.update_crypto_15m",
    max_retries=0,
)
def update_crypto_15m(self: Any) -> dict[str, int]:  # noqa: ARG001
    """加密【成交额 Top N】永续 15m 已收盘 K线采集 · 每 5 分钟跑(15m 根 15min 收一次 · 冗余覆盖)。

    名单 = _all_usdt_perp_symbols()(已按 quote_volume_24h 降序)取前 _CRYPTO_15M_TOPN → 走批量
    _backfill_many(单一 source+CH 复用)· 只写已收盘根(drop_unclosed=True)· insert_kline 同 ts
    跳过、永不重写,绕开普通 MergeTree 无法重写当前根的拦路虎。当前实时价由行情卡的 perp ticker
    承载(非本任务)· 本任务只给 K线图提供已定盘的 15m 形态。
    单币失败不中断整批(_backfill_many 内记 warning + 收集失败名单)· 整体不 retry(下个 beat 补)。
    ★warm_popular_klines 仍用原 5 币清单(缓存预热),与本任务解耦,本刀不扩它。
    """
    async def _run() -> tuple[int, list[str]]:
        ch = await ClickHouseClient.create()
        try:
            symbols = (await _all_usdt_perp_symbols(ch))[:_CRYPTO_15M_TOPN]
        finally:
            await ch.close()
        return await _backfill_many(
            symbols, "crypto", "15m",
            limit=_CRYPTO_15M_LIMIT, instrument="perp", drop_unclosed=True,
        )

    written, failed = asyncio.run(_run())
    logger.info(
        "[crypto-15m] topn=%d written=%d failed=%d", _CRYPTO_15M_TOPN, written, len(failed),
    )
    if failed:
        logger.warning("[crypto-15m] 失败 %d 币:%s", len(failed), ", ".join(failed[:20]))
    return {"written": written, "failed": len(failed)}
