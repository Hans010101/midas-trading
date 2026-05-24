"""ClickHouse 写入/查询 helpers · 美股榜单 / 行业·中概板块(0023 阶段③ · 3.3)。

两张表(DDL 见 ch_schema.py + clickhouse-init.sql · 双写一致):
- us_spot_snapshot   · 策展池个股快照(每次扫描同一 ts 写全池)
- us_sector_snapshot · 板块聚合快照(行业 + 中概股)

时区铁律(继承 0002):写入前 ts tz-aware UTC,读出补 UTC tz。
「最新快照」= ts = max(ts) 的那批行。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.schemas.us_market import UsSector, UsSpotRow

if TYPE_CHECKING:
    from clickhouse_connect.driver.asyncclient import AsyncClient

logger = logging.getLogger(__name__)

_SPOT_COLUMNS = (
    "symbol", "name", "sector", "ts",
    "last_price", "change_pct", "amount", "volume",
)
_SECTOR_COLUMNS = ("name", "ts", "change_pct", "stock_count", "total_amount")

_SPOT_SORT_SAFE = {"change_pct", "amount"}
_ORDER_SAFE = {"DESC", "ASC"}


def _aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _attach_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


# ============================================================================
# 1 · 策展池个股快照
# ============================================================================


async def insert_us_spot(
    client: AsyncClient, rows: list[UsSpotRow], *, ts: datetime,
) -> int:
    if not rows:
        return 0
    ts_aware = _aware_utc(ts)
    data = [
        [r.symbol, r.name, r.sector, ts_aware, r.last_price, r.change_pct, r.amount, r.volume]
        for r in rows
    ]
    await client.insert("us_spot_snapshot", data, column_names=list(_SPOT_COLUMNS))
    return len(rows)


async def select_latest_us_spot(
    client: AsyncClient, *, sort_by: str, order: str, limit: int,
) -> list[UsSpotRow]:
    if sort_by not in _SPOT_SORT_SAFE:
        msg = f"sort_by must be one of {_SPOT_SORT_SAFE} · got {sort_by}"
        raise ValueError(msg)
    order_upper = order.upper()
    if order_upper not in _ORDER_SAFE:
        msg = f"order must be DESC/ASC · got {order}"
        raise ValueError(msg)
    query = f"""
        SELECT symbol, name, sector, last_price, change_pct, amount, volume
        FROM us_spot_snapshot
        WHERE ts = (SELECT max(ts) FROM us_spot_snapshot)
        ORDER BY {sort_by} {order_upper}
        LIMIT %(n)s
    """
    result = await client.query(query, parameters={"n": limit})
    return [
        UsSpotRow(
            symbol=str(r[0]), name=str(r[1]), sector=str(r[2]), last_price=float(r[3]),
            change_pct=float(r[4]), amount=float(r[5]), volume=float(r[6]),
        )
        for r in result.result_rows
    ]


async def select_us_pool_size(client: AsyncClient) -> int:
    """最新快照里实际有数据的股票数。"""
    query = "SELECT count() FROM us_spot_snapshot WHERE ts = (SELECT max(ts) FROM us_spot_snapshot)"
    result = await client.query(query)
    rows = list(result.result_rows)
    return int(rows[0][0]) if rows else 0


async def select_latest_us_spot_ts(client: AsyncClient) -> datetime | None:
    result = await client.query("SELECT max(ts) FROM us_spot_snapshot")
    rows = list(result.result_rows)
    if not rows or rows[0][0] is None:
        return None
    ts = rows[0][0]
    # max(ts) over 空表可能回 1970-01-01;视作无数据
    return _attach_utc(ts) if ts.year > 1970 else None  # noqa: PLR2004


# ============================================================================
# 2 · 板块聚合快照
# ============================================================================


async def insert_us_sectors(
    client: AsyncClient, sectors: list[UsSector], *, ts: datetime,
) -> int:
    if not sectors:
        return 0
    ts_aware = _aware_utc(ts)
    data = [
        [s.name, ts_aware, s.change_pct, s.stock_count, s.total_amount]
        for s in sectors
    ]
    await client.insert("us_sector_snapshot", data, column_names=list(_SECTOR_COLUMNS))
    return len(sectors)


async def select_latest_us_sectors(client: AsyncClient) -> list[UsSector]:
    query = """
        SELECT name, change_pct, stock_count, total_amount
        FROM us_sector_snapshot
        WHERE ts = (SELECT max(ts) FROM us_sector_snapshot)
        ORDER BY change_pct DESC
    """
    result = await client.query(query)
    return [
        UsSector(
            name=str(r[0]), change_pct=float(r[1]),
            stock_count=int(r[2]), total_amount=float(r[3]),
        )
        for r in result.result_rows
    ]
