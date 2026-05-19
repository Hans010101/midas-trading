"""增量更新 worker tasks。

由 Celery beat 按时调度,每个 demo 标的拉最近 ~10 根日 K,
依靠 `ClickHouseClient.insert_kline` 的去重逻辑确保只新增、不重复。

M0 范围:只 3 个 demo 标的;生产版会从 symbol_meta 列 is_active=1 全量。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import shared_task

from app.services.data_sources.exceptions import DataSourceError

# 复用 data_ingest 里的核心异步函数 _backfill_one(本质就是"拉 + 写"幂等操作)
from tasks.data_ingest import _backfill_one

logger = logging.getLogger(__name__)

_INCREMENTAL_LIMIT = 10  # 每次只拉最近 10 根,够覆盖任何短停机窗口


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
        return asyncio.run(_backfill_one("BTC/USDT", "crypto", "Bitcoin", "1d", _INCREMENTAL_LIMIT))
    except DataSourceError as exc:
        logger.warning("update_crypto_demo 失败,重试 %d/3:%s", self.request.retries + 1, exc)
        raise self.retry(exc=exc) from exc
