"""采集新鲜度监控(刀D 还债)· 丙方案:纯读各表 max(ts) 判 stale · 零侵入采集任务。

还债目标:数据 stale 能被一眼/脚本发现,防「BTC 价错 11 天无人发现」再演。
监控的职责是【发现】,不区分 stale 原因(任务没调度 / 跑了失败 / 写空 / 上游断)——
发现后看 worker 容器日志定位。

阈值口径 = max(数据栅格, 任务频率) × 3 缓冲(容忍偶发一轮失败不误报)。两个特例:
  · funding_rate:任务 15min 跑,但数据是 8h 结算栅格 → 阈值按 8h×3=24h(按任务
    频率配会天天误报)。
  · kline 脉搏(BTCUSDT perp 1d · update_crypto_demo 唯一持续采集):日线 bar
    ts=当日 00:00,正常 age 峰值 ~24h(午夜前夕)→ 阈值 48h =「超过 1 天没今日 bar」。
股票三市场表 v1 只裸报 latest_ts + age 不判 stale(交易时段语义:周末 max(ts)=周五
是正常的,准判定要接交易日历,超出还债范围)。

🔴 红线:纯只读(maxOrNull 聚合)· 不碰采集任务 / engine / 触发器 / 任何写路径。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from clickhouse_connect.driver.asyncclient import AsyncClient

    from app.schemas.crypto import EconJobStatus, EquityIngestStatus, IngestSourceStatus


class SourceSpec(NamedTuple):
    """一个被监控的采集源:表 + 可选过滤 + stale 阈值(秒)。"""

    source: str
    table: str
    where: str  # 空串 = 全表
    expected_max_age_seconds: int


# ── 加密 7 源(7×24 无歧义 · 判 stale)· 阈值 = max(数据栅格, 任务频率) × 3 ──────
CRYPTO_SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec("ticker_24h", "crypto_ticker_24h", "", 1800),          # 10min 任务 ×3
    SourceSpec("premium_index", "crypto_premium_index", "", 180),     # 1min ×3
    SourceSpec("open_interest", "crypto_open_interest", "", 900),     # 5min ×3
    SourceSpec("long_short", "crypto_long_short_ratio", "", 2700),  # max(栅格,15min任务)×3
    # ★ 特例:数据是 8h 结算栅格(任务 15min 只是刷)→ 8h×3=24h,按任务频率配会天天误报
    SourceSpec("funding_rate", "crypto_funding_rate", "", 86400),
    SourceSpec("market_overview", "crypto_market_overview", "", 5400),  # 30min ×3
    # ★ 特例:日线 bar ts=当日 00:00 · 正常 age 峰值 ~24h → 48h =「超过 1 天没今日 bar」
    SourceSpec(
        "kline_btc_perp_1d", "kline",
        "WHERE symbol = 'BTCUSDT' AND market = 'crypto'"
        " AND instrument = 'perp' AND period = '1d'",
        172800,
    ),
)

# ── 股票三市场 + 指数(v1 裸报 · 不判 stale:周末滞后是交易时段语义,非故障)────
EQUITY_SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec("cn_spot_snapshot", "cn_spot_snapshot", "", 0),
    SourceSpec("us_spot_snapshot", "us_spot_snapshot", "", 0),
    SourceSpec("hk_spot_snapshot", "hk_spot_snapshot", "", 0),
    SourceSpec("market_index_snapshot", "market_index_snapshot", "", 0),
)


def is_stale(
    latest_ts: datetime | None, expected_max_age_seconds: int, now: datetime,
) -> bool:
    """新鲜度判定纯函数:从未采(None)= stale;age > 阈值 = stale(恰好等于不算)。"""
    if latest_ts is None:
        return True
    last = latest_ts if latest_ts.tzinfo is not None else latest_ts.replace(tzinfo=UTC)
    return (now - last).total_seconds() > expected_max_age_seconds


async def select_ingest_freshness(client: AsyncClient) -> dict[str, datetime | None]:
    """单请求 UNION ALL 扫全部被监控表的 maxOrNull(ts)(空表 → None = 从未采)。"""
    parts = [
        f"SELECT '{s.source}' AS source, maxOrNull(ts) AS latest FROM {s.table} {s.where}"
        for s in (*CRYPTO_SOURCES, *EQUITY_SOURCES)
    ]
    result = await client.query(" UNION ALL ".join(parts))
    out: dict[str, datetime | None] = {}
    for source, latest in result.result_rows:
        if latest is None:
            out[source] = None
        else:
            out[source] = latest if latest.tzinfo is not None else latest.replace(tzinfo=UTC)
    return out


def build_ingest_status(
    latest_map: dict[str, datetime | None], now: datetime,
) -> tuple[list[IngestSourceStatus], list[EquityIngestStatus], bool]:
    """组装端点响应(纯函数 · 可单测)· 返回 (加密源, 股票源, any_stale)。"""
    from app.schemas.crypto import EquityIngestStatus, IngestSourceStatus

    def _age(ts: datetime | None) -> float | None:
        if ts is None:
            return None
        last = ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
        return (now - last).total_seconds()

    crypto_items = [
        IngestSourceStatus(
            source=s.source,
            table=s.table,
            latest_ts=latest_map.get(s.source),
            age_seconds=_age(latest_map.get(s.source)),
            expected_max_age_seconds=s.expected_max_age_seconds,
            stale=is_stale(latest_map.get(s.source), s.expected_max_age_seconds, now),
        )
        for s in CRYPTO_SOURCES
    ]
    equity_items = [
        EquityIngestStatus(
            source=s.source,
            table=s.table,
            latest_ts=latest_map.get(s.source),
            age_seconds=_age(latest_map.get(s.source)),
        )
        for s in EQUITY_SOURCES
    ]
    any_stale = any(item.stale for item in crypto_items)
    return crypto_items, equity_items, any_stale


# ── 事件日程层 P0 · job last-run 新鲜度(★与上面「表 max(ts)」口径本质不同)──────────
#   事件 scheduled_at 在【未来】,max(ts) 永远"新鲜"=假新鲜 → 只能按「采集任务上次成功
#   时间」判(Redis econ:cal:last_success:{source} · worker 每源成功后写)。
#   阈值 3 天(任务日更 ×3 缓冲);★stale ≠ 数据不可用:日程失效模式良性,存量未来日程
#   源断后 30 天内仍有效(30 天硬阈在 econ_calendar.store.events_usable,决策卡侧生效)。
ECON_JOB_STALE_SECONDS = 3 * 24 * 3600


def build_econ_job_status(
    freshness: dict[str, datetime | None], now: datetime,
) -> tuple[list[EconJobStatus], bool]:
    """组装事件日程 job 新鲜度(纯函数 · 可单测)· 返回 (items, any_stale)。"""
    from app.schemas.crypto import EconJobStatus

    items = []
    for source, ts in freshness.items():
        age = None
        if ts is not None:
            last = ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
            age = max(0.0, (now - last).total_seconds())
        items.append(EconJobStatus(
            source=source,
            last_success=ts,
            age_seconds=age,
            stale=age is None or age > ECON_JOB_STALE_SECONDS,
        ))
    return items, any(i.stale for i in items)
