"""智能交易 · 技术信号生产(智能交易 PR-1)· Celery beat 每 15m 算 150 币 → Redis 快照。

仿 boll_scan 结构(asyncio.run + ClickHouseClient.create + aioredis · 只读 CH)。
方向分用 indicators.compute_*(PR-0 §1·B · 当前值不是信号点)· 布林方向分 PR-3 另读
boll:snapshot:latest 的 bias(权重 2.0 · 零重算)。存 intelligent:signals:latest(TTL 30min)·
供 PR-3 打分引擎读。
🔴 信号生产层 · ★绝不下单(下单是 PR-4)· 不碰引擎 / 托管 / boll_scan。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from celery import shared_task
from redis import asyncio as aioredis

from app.services.ai.extreme_signals import compute_extreme_signals
from app.services.ai.intelligent_signals import (
    MIN_BARS,
    compute_indicator_directions,
    extreme_direction,
)
from app.services.clickhouse_client import ClickHouseClient
from app.services.clickhouse_crypto import select_latest_tickers
from tasks.crypto_metrics_ingest import _all_usdt_perp_symbols

logger = logging.getLogger(__name__)

_UNIVERSE_N = 150          # 同 boll_scan / 15m 采集口径(成交额 Top 150 纯加密永续)
_LOOKBACK_BARS = 50        # ≥ MIN_BARS(26)· 取 50 冗余(各指标预热足)
_SIGNALS_KEY = "intelligent:signals:latest"  # ★PR-3 打分引擎读 · 独立 key
_SIGNALS_TTL = 30 * 60     # 30min 防陈旧(每 15min 刷 · 留两轮余量)


async def _intelligent_signals_async() -> dict[str, int]:
    redis = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )
    ch = await ClickHouseClient.create()
    rows: list[dict[str, Any]] = []
    universe_n = 0
    try:
        # ★裸 client(.query)走 ch._client · 同 boll_scan 范式
        universe = (await _all_usdt_perp_symbols(ch._client))[:_UNIVERSE_N]  # noqa: SLF001
        universe_n = len(universe)
        try:
            tickers = await select_latest_tickers(
                ch._client, instrument="perp", sort_by="quote_volume_24h",  # noqa: SLF001
                order="DESC", limit=_UNIVERSE_N,
            )
            change_map = {t.symbol.replace("/", ""): t.change_pct_24h for t in tickers}
        except Exception as exc:  # noqa: BLE001 · 单点降级不放大
            logger.warning("[intelligent-signals] 24h 涨跌读失败 · 降级 None: %s", exc)
            change_map = {}

        for sym in universe:
            try:
                klines = await ch.select_kline(
                    symbol=sym, market="crypto", period="15m",
                    limit=_LOOKBACK_BARS, instrument="perp",
                )
                if len(klines) < MIN_BARS:
                    continue
                dirs = compute_indicator_directions(klines)
                extreme = await compute_extreme_signals(  # noqa: SLF001
                    ch._client, sym, "crypto", "perp", klines,
                )
                rows.append({
                    "symbol": sym,
                    **dirs,
                    "extreme_dir": extreme_direction(extreme),
                    "change_pct_24h": change_map.get(sym),
                })
            except Exception:  # noqa: BLE001 · 单币失败隔离,不中断本轮
                logger.exception("[intelligent-signals] %s 扫描失败", sym)

        # ★落快照供 PR-3 读 · 写失败不影响主流程(吸取 ticker 教训:单点不放大)
        try:
            payload = json.dumps(
                {"as_of": datetime.now(tz=UTC).isoformat(), "items": rows},
                ensure_ascii=False,
            )
            await redis.set(_SIGNALS_KEY, payload, ex=_SIGNALS_TTL)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[intelligent-signals] 落快照失败(不影响主流程): %s", exc)

        logger.info("[intelligent-signals] universe=%d · 快照 %d 行", universe_n, len(rows))
        return {"universe": universe_n, "snapshot": len(rows)}
    finally:
        await ch.close()
        await redis.aclose()


@shared_task(name="tasks.crypto.intelligent_signals_scan", max_retries=0)
def intelligent_signals_scan() -> dict[str, int]:
    """每 15m 算 150 币技术信号方向分 → intelligent:signals:latest(★信号生产 · 不下单)。"""
    return asyncio.run(_intelligent_signals_async())
