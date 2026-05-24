"""ClickHouse 写入/查询 helpers · A股榜单 / 情绪 / 行业板块(0023 阶段③ · 3.2)。

三张表(DDL 见 ch_schema.py + clickhouse-init.sql · 双写一致):
- cn_spot_snapshot   · 全市场个股快照(每次扫描同一 ts 写全量 · 短 TTL)
- cn_market_breadth  · 情绪条单行(涨跌平家数 + 涨跌停估 + 总成交额)
- cn_sector_snapshot · 行业板块快照

时区铁律(继承 0002):写入前 ts tz-aware UTC,读出补 UTC tz。
「最新快照」= ts = max(ts) 的那批行(一次扫描所有行共享同一 ts)。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.schemas.cn_market import CnBreadth, CnSector, CnSpotRow

if TYPE_CHECKING:
    from clickhouse_connect.driver.asyncclient import AsyncClient

logger = logging.getLogger(__name__)

_SPOT_COLUMNS = (
    "symbol", "name", "ts",
    "last_price", "change_pct", "change_amount", "amount", "volume",
)
_BREADTH_COLUMNS = (
    "ts", "up_count", "down_count", "flat_count",
    "limit_up_count", "limit_down_count", "total_amount",
)
_SECTOR_COLUMNS = (
    "name", "ts", "change_pct", "stock_count",
    "total_amount", "leader_name", "leader_change_pct",
)

_SPOT_SORT_SAFE = {"change_pct", "amount"}
_ORDER_SAFE = {"DESC", "ASC"}


def _aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _attach_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


# ============================================================================
# 1 · 全市场 spot 快照
# ============================================================================


async def insert_spot_snapshot(
    client: AsyncClient, rows: list[CnSpotRow], *, ts: datetime,
) -> int:
    """整张全市场快照写入 · 所有行共享同一 ts(扫描时刻)。"""
    if not rows:
        return 0
    ts_aware = _aware_utc(ts)
    data = [
        [
            r.symbol, r.name, ts_aware,
            r.last_price, r.change_pct, r.change_amount, r.amount, r.volume,
        ]
        for r in rows
    ]
    await client.insert("cn_spot_snapshot", data, column_names=list(_SPOT_COLUMNS))
    return len(rows)


async def select_latest_spot(
    client: AsyncClient, *, sort_by: str, order: str, limit: int,
) -> list[CnSpotRow]:
    """最新快照(ts = max(ts))按 sort_by 排序取 top N · 白名单防注入。"""
    if sort_by not in _SPOT_SORT_SAFE:
        msg = f"sort_by must be one of {_SPOT_SORT_SAFE} · got {sort_by}"
        raise ValueError(msg)
    order_upper = order.upper()
    if order_upper not in _ORDER_SAFE:
        msg = f"order must be DESC/ASC · got {order}"
        raise ValueError(msg)
    query = f"""
        SELECT symbol, name, last_price, change_pct, change_amount, amount, volume
        FROM cn_spot_snapshot
        WHERE ts = (SELECT max(ts) FROM cn_spot_snapshot)
        ORDER BY {sort_by} {order_upper}
        LIMIT %(n)s
    """
    result = await client.query(query, parameters={"n": limit})
    return [
        CnSpotRow(
            symbol=str(r[0]), name=str(r[1]), last_price=float(r[2]),
            change_pct=float(r[3]), change_amount=float(r[4]),
            amount=float(r[5]), volume=float(r[6]),
        )
        for r in result.result_rows
    ]


# ============================================================================
# 2 · 情绪条
# ============================================================================


async def insert_breadth(client: AsyncClient, breadth: CnBreadth) -> int:
    data = [[
        _aware_utc(breadth.ts),
        breadth.up_count, breadth.down_count, breadth.flat_count,
        breadth.limit_up_count, breadth.limit_down_count, breadth.total_amount,
    ]]
    await client.insert("cn_market_breadth", data, column_names=list(_BREADTH_COLUMNS))
    return 1


async def select_latest_breadth(client: AsyncClient) -> CnBreadth | None:
    query = (
        "SELECT ts, up_count, down_count, flat_count, "
        "limit_up_count, limit_down_count, total_amount "
        "FROM cn_market_breadth FINAL ORDER BY ts DESC LIMIT 1"
    )
    result = await client.query(query)
    rows = list(result.result_rows)
    if not rows:
        return None
    r = rows[0]
    return CnBreadth(
        ts=_attach_utc(r[0]),
        up_count=int(r[1]), down_count=int(r[2]), flat_count=int(r[3]),
        limit_up_count=int(r[4]), limit_down_count=int(r[5]),
        total_amount=float(r[6]),
    )


# ============================================================================
# 3 · 行业板块
# ============================================================================


async def insert_sectors(
    client: AsyncClient, sectors: list[CnSector], *, ts: datetime,
) -> int:
    if not sectors:
        return 0
    ts_aware = _aware_utc(ts)
    data = [
        [
            s.name, ts_aware, s.change_pct, s.stock_count,
            s.total_amount, s.leader_name, s.leader_change_pct,
        ]
        for s in sectors
    ]
    await client.insert("cn_sector_snapshot", data, column_names=list(_SECTOR_COLUMNS))
    return len(sectors)


async def select_latest_sectors(
    client: AsyncClient, *, limit: int = 60,
) -> list[CnSector]:
    """最新一批行业板块 · 按涨跌幅降序。"""
    query = """
        SELECT name, change_pct, stock_count, total_amount, leader_name, leader_change_pct
        FROM cn_sector_snapshot
        WHERE ts = (SELECT max(ts) FROM cn_sector_snapshot)
        ORDER BY change_pct DESC
        LIMIT %(n)s
    """
    result = await client.query(query, parameters={"n": limit})
    return [
        CnSector(
            name=str(r[0]), change_pct=float(r[1]), stock_count=int(r[2]),
            total_amount=float(r[3]), leader_name=str(r[4]),
            leader_change_pct=float(r[5]),
        )
        for r in result.result_rows
    ]
