"""K 线新鲜度读取(刀A2-1)· 端点与撮合 fetcher 共用的 cache-aside helper。

治本对象(诊断已坐实):/kline 端点「行数 ≥ limit 即命中、零新鲜度」→ crypto
多周期永久 stale(H/USDT 15m 停 6/1=0.63 · 1h 停 5/30=0.34,行数 ≥500 后连
穿透刷新都失效);撮合 fetcher 直连 select_kline 同吃 stale。

规则:
  · 行数 < limit          → 回源(所有市场 · 现状行为保留,cn/us/hk 首访回填不变)
  · 行数够但末根 stale     → 回源(★仅 market='crypto':spot 三市场有采集任务保
    新鲜,且避免周末「末根=周五」每请求无谓打上游)
  · stale 阈值 = 1×period 秒:1d 当日 bar(ts=00:00)永远在 86400s 内 → 盘中不
    反复回源,缺今日 bar(末根=昨日)才回源,语义正好。
  · 整窗回源(不加 startTime):同样 1 个上游请求(币安 klines limit≤500 权重 2),
    insert_kline 已「已存在 ts 跳过」只落新行 —— 增量参数收益≈0,不加。
  · 回源失败降级:缓存非空 → 返回缓存(不比现状差);缓存空 → 异常透传
    (端点照旧映射 404/503/502)。

🔴 红线:本模块只做 kline 读路径(读缓存 + 回源 + persist),
   不含任何撮合/滑点/手续费/持仓逻辑;engine/perp_dispatcher 零碰。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.services.data_sources.exceptions import DataSourceError

if TYPE_CHECKING:
    from app.schemas.market import Kline, Market, Period
    from app.services.clickhouse_client import ClickHouseClient
    from app.services.data_sources.base import BaseDataSource

logger = logging.getLogger(__name__)

# Period 7 档全覆盖(schemas/market.py Literal)
_PERIOD_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "1d": 86400,
    "1w": 604800,
}


def is_stale(last_ts: datetime, period: Period, now: datetime | None = None) -> bool:
    """末根 bar 是否过期:now − last_ts > 1×period(纯函数 · 可单测)。"""
    ref = now if now is not None else datetime.now(tz=UTC)
    last = last_ts if last_ts.tzinfo is not None else last_ts.replace(tzinfo=UTC)
    return (ref - last).total_seconds() > _PERIOD_SECONDS[period]


async def get_fresh_kline(
    ch: ClickHouseClient,
    *,
    symbol: str,
    market: Market,
    period: Period,
    limit: int = 500,
    instrument: str = "spot",
    source: BaseDataSource | None = None,
    now: datetime | None = None,
) -> list[Kline]:
    """读最近 limit 根 K 线(ts 升序)· 不足或(crypto)末根过期则整窗回源 persist。

    source=None 时退化为纯读缓存(= 改造前行为 · 测试环境/无 lifespan 场景零破坏)。
    """
    cached = await ch.select_kline(
        symbol=symbol, market=market, period=period, limit=limit, instrument=instrument,
    )

    need_refresh = len(cached) < limit or (
        market == "crypto" and bool(cached) and is_stale(cached[-1].ts, period, now)
    )
    if not need_refresh or source is None:
        return cached

    # 整窗回源 · perp 上游用 Binance 风格无斜杠(BTC/USDT → BTCUSDT)
    fetch_symbol = symbol.replace("/", "") if instrument == "perp" else symbol
    try:
        upstream = await source.fetch_kline(fetch_symbol, period, limit=limit)
    except DataSourceError:
        if cached:
            logger.warning(
                "[kline_freshness] 回源失败 · 降级返回缓存 symbol=%s market=%s period=%s rows=%d",
                symbol, market, period, len(cached),
            )
            return cached
        raise  # 缓存全空:让调用方照旧映射错误(404/503/502)

    written = await ch.insert_kline(
        upstream, symbol=symbol, market=market, period=period, instrument=instrument,
    )
    logger.info(
        "[kline_freshness] refresh · symbol=%s market=%s instrument=%s period=%s"
        " upstream=%d ch_new=%d (cached=%d)",
        symbol, market, instrument, period, len(upstream), written, len(cached),
    )
    return upstream[-limit:]
