"""ClickHouse 写入/查询 helpers · A股/美股 市场首页(0023 阶段③ · 3.1)。

两张表(DDL 见 apps/worker/ch_schema.py + docker/clickhouse-init.sql · 双写一致):
- market_index_snapshot · 大盘指数快照(cn/us 共表 · market 列区分)
- market_trade_calendar  · 交易日历(目前仅 cn · AKShare 采)

跟 clickhouse_crypto.py 同款铁律:
- 写入前 ts 必须 tz-aware UTC(_aware_utc)· 读出补 UTC tz(_attach_utc)· 0002 教训
- client 必须设 session_timezone='UTC'(worker _get_ch_client / lifespan client 都已加)
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from app.schemas.market_home import IndexQuote, MarketKind

if TYPE_CHECKING:
    from clickhouse_connect.driver.asyncclient import AsyncClient

logger = logging.getLogger(__name__)

_INDEX_COLUMNS = (
    "market", "symbol", "name", "ts",
    "last_point", "prev_close", "change_point", "change_pct",
)
_CALENDAR_COLUMNS = ("market", "trade_date")


def _aware_utc(dt: datetime) -> datetime:
    """归一为 tz-aware UTC · 给 clickhouse-connect 写入用(0002 教训 · 绝不传 naive)。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _attach_utc(dt: datetime) -> datetime:
    """读出后给 naive datetime 补 UTC tz。"""
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=UTC)


# ============================================================================
# 1 · 大盘指数快照
# ============================================================================


async def insert_index_snapshots(client: AsyncClient, items: list[IndexQuote]) -> int:
    """批量写指数快照 · ReplacingMergeTree 按 (market, symbol, ts) 去重。"""
    if not items:
        return 0
    data = [
        [
            it.market, it.symbol, it.name, _aware_utc(it.ts),
            it.last_point, it.prev_close, it.change_point, it.change_pct,
        ]
        for it in items
    ]
    await client.insert(
        "market_index_snapshot", data, column_names=list(_INDEX_COLUMNS),
    )
    return len(items)


async def select_latest_indices(
    client: AsyncClient, *, market: MarketKind, order: tuple[str, ...],
) -> list[IndexQuote]:
    """取某市场每个指数的最新一行 · 按 `order`(展示顺序)重排 · 缺数据的指数略过。

    ReplacingMergeTree FINAL + ROW_NUMBER 取每 symbol 最新行(跟 crypto ticker 同款)。
    """
    query = """
        SELECT market, symbol, name, ts, last_point, prev_close, change_point, change_pct
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY ts DESC) AS rn
            FROM market_index_snapshot FINAL
            WHERE market = %(m)s
        )
        WHERE rn = 1
    """
    result = await client.query(query, parameters={"m": market})
    by_symbol: dict[str, IndexQuote] = {}
    for r in result.result_rows:
        last_point = float(r[4])
        if last_point <= 0:  # IndexQuote 要求 last_point > 0 · 异常行略过(不造假)
            continue
        by_symbol[str(r[1])] = IndexQuote(
            market=str(r[0]),
            symbol=str(r[1]),
            name=str(r[2]),
            ts=_attach_utc(r[3]),
            last_point=last_point,
            prev_close=float(r[5]),
            change_point=float(r[6]),
            change_pct=float(r[7]),
        )
    # 按展示顺序输出 · 不在 order 里或没数据的略过
    return [by_symbol[code] for code in order if code in by_symbol]


# ============================================================================
# 2 · 交易日历
# ============================================================================


async def insert_trade_calendar(
    client: AsyncClient, *, market: MarketKind, dates: list[date],
) -> int:
    """批量写交易日 · ReplacingMergeTree 按 (market, trade_date) 去重(幂等)。"""
    if not dates:
        return 0
    data = [[market, d] for d in dates]
    await client.insert(
        "market_trade_calendar", data, column_names=list(_CALENDAR_COLUMNS),
    )
    return len(dates)


async def select_trade_days(
    client: AsyncClient, *, market: MarketKind, since: date, until: date,
) -> frozenset[date]:
    """取某市场 [since, until] 窗口内的交易日集合 · 给状态机判「今天是不是交易日」。

    返回空集 = 日历未采到 · 调用方(market_calendar)据此回退周一至周五逻辑。
    """
    query = (
        "SELECT DISTINCT trade_date FROM market_trade_calendar FINAL "
        "WHERE market = %(m)s AND trade_date BETWEEN %(s)s AND %(u)s"
    )
    result = await client.query(
        query, parameters={"m": market, "s": since, "u": until},
    )
    out: set[date] = set()
    for r in result.result_rows:
        v = r[0]
        if isinstance(v, datetime):
            out.add(v.date())
        elif isinstance(v, date):
            out.add(v)
    return frozenset(out)
