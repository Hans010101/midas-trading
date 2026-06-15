"""ClickHouse 写入/查询 helpers · 港股榜单 / 情绪(港股首页全市场)。

两张表(DDL 见 apps/worker/ch_schema.py + docker/clickhouse-init.sql · 双写一致):
- hk_spot_snapshot   · 全市场个股快照(新浪 stock_hk_spot ~2764 只 · 每次扫描同一 ts · 短 TTL)
- hk_market_breadth  · 情绪条单行(涨跌平家数 + 总成交额 · ★港股无涨跌停)

时区铁律(继承 0002):写入前 ts tz-aware UTC,读出补 UTC tz。
「最新快照」= ts = max(ts) 的那批行(一次扫描所有行共享同一 ts)。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.schemas.hk_market import HkBreadth, HkSpotRow

if TYPE_CHECKING:
    from clickhouse_connect.driver.asyncclient import AsyncClient

logger = logging.getLogger(__name__)

_SPOT_COLUMNS = (
    "symbol", "name", "ts",
    "last_price", "change_pct", "change_amount", "amount", "volume",
)
_BREADTH_COLUMNS = ("ts", "up_count", "down_count", "flat_count", "total_amount")

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
    client: AsyncClient, rows: list[HkSpotRow], *, ts: datetime,
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
    await client.insert("hk_spot_snapshot", data, column_names=list(_SPOT_COLUMNS))
    return len(rows)


async def select_latest_spot(
    client: AsyncClient, *, sort_by: str, order: str, limit: int,
) -> list[HkSpotRow]:
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
        FROM hk_spot_snapshot
        WHERE ts = (SELECT max(ts) FROM hk_spot_snapshot)
        ORDER BY {sort_by} {order_upper}
        LIMIT %(n)s
    """
    result = await client.query(query, parameters={"n": limit})
    return [
        HkSpotRow(
            symbol=str(r[0]), name=str(r[1]), last_price=float(r[2]),
            change_pct=float(r[3]), change_amount=float(r[4]),
            amount=float(r[5]), volume=float(r[6]),
        )
        for r in result.result_rows
    ]


async def select_hk_spot_search(
    client: AsyncClient, *, query: str, limit: int = 8,
) -> list[HkSpotRow]:
    """港股全市场搜索(最新快照 · symbol / name 子串命中 · 成交额降序)· 镜像 cn select_spot_search。

    positionCaseInsensitive 子串匹配(非 LIKE → 无 % / _ 通配注入风险)· 中文名同样适用。
    """
    sql = """
        SELECT symbol, name, last_price, change_pct, change_amount, amount, volume
        FROM hk_spot_snapshot
        WHERE ts = (SELECT max(ts) FROM hk_spot_snapshot)
          AND (positionCaseInsensitive(symbol, %(q)s) > 0
               OR positionCaseInsensitive(name, %(q)s) > 0)
        ORDER BY amount DESC
        LIMIT %(n)s
    """
    result = await client.query(sql, parameters={"q": query, "n": limit})
    return [
        HkSpotRow(
            symbol=str(r[0]), name=str(r[1]), last_price=float(r[2]),
            change_pct=float(r[3]), change_amount=float(r[4]),
            amount=float(r[5]), volume=float(r[6]),
        )
        for r in result.result_rows
    ]


# ============================================================================
# 2 · 情绪条(港股无涨跌停 → 只涨跌平 + 总成交额)
# ============================================================================


async def insert_breadth(client: AsyncClient, breadth: HkBreadth) -> int:
    data = [[
        _aware_utc(breadth.ts),
        breadth.up_count, breadth.down_count, breadth.flat_count,
        breadth.total_amount,
    ]]
    await client.insert("hk_market_breadth", data, column_names=list(_BREADTH_COLUMNS))
    return 1


async def select_latest_breadth(client: AsyncClient) -> HkBreadth | None:
    query = (
        "SELECT ts, up_count, down_count, flat_count, total_amount "
        "FROM hk_market_breadth FINAL ORDER BY ts DESC LIMIT 1"
    )
    result = await client.query(query)
    rows = list(result.result_rows)
    if not rows:
        return None
    r = rows[0]
    return HkBreadth(
        ts=_attach_utc(r[0]),
        up_count=int(r[1]), down_count=int(r[2]), flat_count=int(r[3]),
        total_amount=float(r[4]),
    )
