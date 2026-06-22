"""布林做T扫描器 M1(★影子模式)· Celery beat 每 15m bar 收盘后跑。

★影子模式:只把本该推送的【会话级文案】logger.info 打出来,【绝不】调 TG 发送 helper(M2 再翻真)。

🔴 三红线(机器证明钉死):
①绝不接真实下单(纯分析 · 全程无任何 order/trade/execute 调用);
②ClickHouse 只读(klines/tickers 只 select · 状态/冷却只进 Redis,绝不写 CH);
③推送文案经 boll_state.validate_shadow_push 门禁(末尾免责 + 买卖祈使黑名单一票否决)。

数据复用(全部现成,不另造):
- 15m kline:ClickHouseClient.select_kline(纯读 · DESC LIMIT N + reverse)
- 涨跌榜筛选池:clickhouse_crypto.select_latest_tickers(裸 client · change_pct_24h 排序)
- universe:crypto_metrics_ingest._all_usdt_perp_symbols(裸 client · 同 15m 采集口径 Top N)
- Redis 状态/冷却:复用 visit_stats 小时桶范式(set + ex TTL 自动清,不落 PG/CH)
"""

from __future__ import annotations

import asyncio
import logging
import os

from celery import shared_task
from redis import asyncio as aioredis

from app.services.ai.boll_state import build_session_message, classify, render_card
from app.services.clickhouse_client import ClickHouseClient
from app.services.clickhouse_crypto import select_latest_tickers
from tasks.crypto_metrics_ingest import _all_usdt_perp_symbols

logger = logging.getLogger(__name__)

_UNIVERSE_N = 150          # 扫描标的 = 成交额 Top 150 纯加密永续(同 15m 采集口径)
_POOL_N = 40               # 涨跌榜各取前 40(涨幅 + 跌幅)作推送筛选池(降噪)
_LOOKBACK_BARS = 30        # select_kline 取最近 30 根(布林 20 预热 + 斜率/带宽回看余量)
_STATE_TTL = 24 * 3600     # Redis 状态滚动窗口 ~24h(TTL 自动清)
_COOLDOWN_SEC = 4 * 3600   # 每标的推送冷却 4h(冷却窗口内再转换也不重复推)


def _state_key(sym: str) -> str:
    return f"boll:state:{sym}"


def _cooldown_key(sym: str) -> str:
    return f"boll:cooldown:{sym}"


async def _boll_scan_async() -> dict[str, int]:
    redis = aioredis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )
    ch = await ClickHouseClient.create()
    candidates: list[str] = []
    universe_n = 0
    transitions = 0
    try:
        # ★裸 client(有 .query)走 ch._client · 同 analysis.py 范式 · 不传 ClickHouseClient 封装类
        universe = (await _all_usdt_perp_symbols(ch._client))[:_UNIVERSE_N]  # noqa: SLF001
        universe_n = len(universe)
        gainers = await select_latest_tickers(
            ch._client, instrument="perp", sort_by="change_pct_24h", order="DESC", limit=_POOL_N,  # noqa: SLF001
        )
        losers = await select_latest_tickers(
            ch._client, instrument="perp", sort_by="change_pct_24h", order="ASC", limit=_POOL_N,  # noqa: SLF001
        )
        pool = {t.symbol.replace("/", "") for t in [*gainers, *losers]}

        for sym in universe:
            klines = await ch.select_kline(
                symbol=sym, market="crypto", period="15m", limit=_LOOKBACK_BARS, instrument="perp",
            )
            snap = classify(klines)
            if snap is None:
                continue
            prev = await redis.get(_state_key(sym))
            # 状态滚动窗口(Redis · 不写 CH)· 每轮刷新当前状态
            await redis.set(_state_key(sym), snap.state.value, ex=_STATE_TTL)
            # 边沿检测:仅【状态发生转换】进候选(无 prev = 冷启动基线,不推)
            if prev is None or prev == snap.state.value:
                continue
            transitions += 1
            if sym not in pool:                          # 降噪:只推涨跌榜前列
                continue
            if await redis.get(_cooldown_key(sym)):      # 每标的冷却
                continue
            candidates.append(render_card(sym, snap))
            await redis.set(_cooldown_key(sym), "1", ex=_COOLDOWN_SEC)

        if candidates:
            # ★build_session_message 内含 validate_shadow_push 门禁(免责 + 买卖黑名单)
            msg = build_session_message(candidates)
            # ★影子模式:只打日志,绝不调 TG 发送 helper(M2 接 telegram.send_event)
            logger.info(
                "[boll-scan-shadow] 本轮推送文案(影子·不真发 · %d 标的):\n%s",
                len(candidates), msg,
            )
        else:
            logger.info(
                "[boll-scan-shadow] 本轮无「转换∩涨跌榜∩非冷却」候选(转换 %d 个)· 不推送",
                transitions,
            )
        return {"universe": universe_n, "transitions": transitions, "candidates": len(candidates)}
    finally:
        await ch.close()
        await redis.aclose()


@shared_task(name="tasks.crypto.boll_scan", max_retries=0)
def boll_scan() -> dict[str, int]:
    """15m bar 收盘后跑 · ★影子模式只打日志不发 TG · 跑现有 midas-worker(concurrency=4 够)。"""
    return asyncio.run(_boll_scan_async())
