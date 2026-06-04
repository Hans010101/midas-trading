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

from app.services.data_sources.exceptions import DataSourceError
from app.services.hk_pool import HK_POOL_META, HK_POOL_SYMBOLS

# 复用 data_ingest 里的核心异步函数 _backfill_one(本质就是"拉 + 写"幂等操作)
from tasks.data_ingest import _backfill_one

logger = logging.getLogger(__name__)

_INCREMENTAL_LIMIT = 10  # 每次只拉最近 10 根,够覆盖任何短停机窗口
# 港股池每只采最近 300 根日 K(首次充足历史 · 后续 insert 去重幂等增量)
_HK_POOL_LIMIT = 300


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
