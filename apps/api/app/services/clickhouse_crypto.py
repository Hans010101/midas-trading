"""ClickHouse 写入/查询 helpers · Crypto Pro 5 张新表(0017 ADR · M2-A)。

跟 clickhouse_client.py 互补 · 不污染原 ClickHouseClient 类。
将来 M2-E 性能优化时可考虑合并到 ClickHouseClient,目前独立模块更清晰。

时区铁律(继承 0002 教训):
- 写入前 ts 必须去 tz(变 naive UTC)
- 读出后 ts 必须补 UTC tz

ORDER BY DESC + Python reverse 模式(继承 0010 教训):
- 任何「取最新 N 条」语义必须 SQL 端 DESC LIMIT N · Python reverse 还原 ASC
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.schemas.crypto import (
    FearGreedPoint,
    FundingRate,
    LongShortRatio,
    MarketOverview,
    OpenInterest,
    Ticker24h,
)

if TYPE_CHECKING:
    from clickhouse_connect.driver.asyncclient import AsyncClient

logger = logging.getLogger(__name__)


# ============================================================================
# 列定义 · 跟 clickhouse-init.sql 严格对齐
# ============================================================================

_FUNDING_COLUMNS = ("symbol", "ts", "rate", "mark_price")
_OI_COLUMNS = ("symbol", "ts", "oi_coin", "oi_usd")
_LONG_SHORT_COLUMNS = (
    "symbol", "ts",
    "top_account_long", "top_account_short", "top_account_ratio",
    "top_position_long", "top_position_short", "top_position_ratio",
    "taker_buy_vol", "taker_sell_vol", "taker_ratio",
)
_TICKER_24H_COLUMNS = (
    "symbol", "instrument", "ts",
    "last_price", "change_pct_24h", "high_24h", "low_24h",
    "volume_24h", "quote_volume_24h", "count_24h",
)
_OVERVIEW_COLUMNS = (
    "ts",
    "total_market_cap_usd", "total_volume_24h_usd",
    "btc_dominance", "eth_dominance",
    "fear_greed_value", "fear_greed_classification",
    "derivatives_oi_usd", "derivatives_volume_24h_usd",
)


def _strip_tz(dt: datetime) -> datetime:
    """tz-aware UTC datetime → naive(去 tz)· 给 clickhouse-connect 写入用。"""
    if dt.tzinfo is None:
        return dt  # 已经是 naive · 兜底
    return dt.astimezone(UTC).replace(tzinfo=None)


def _attach_utc(dt: datetime) -> datetime:
    """naive datetime → tz-aware UTC · 给读出后补 tz 用。"""
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=UTC)


# ============================================================================
# 1 · Funding Rate
# ============================================================================


async def insert_funding_rates(
    client: AsyncClient, items: list[FundingRate],
) -> int:
    """批量写 · ReplacingMergeTree 自动按 (symbol, ts) 去重。"""
    if not items:
        return 0
    data = [
        [it.symbol, _strip_tz(it.ts), it.rate, it.mark_price]
        for it in items
    ]
    await client.insert("crypto_funding_rate", data, column_names=list(_FUNDING_COLUMNS))
    return len(items)


async def select_funding_rates(
    client: AsyncClient, symbol: str, *, limit: int = 100,
) -> list[FundingRate]:
    """取最新 N 条 · 返回 ASC 升序(0010 教训 · DESC LIMIT + reverse)。"""
    query = (
        "SELECT symbol, ts, rate, mark_price FROM crypto_funding_rate "
        "WHERE symbol = %(s)s ORDER BY ts DESC LIMIT %(n)s"
    )
    result = await client.query(query, parameters={"s": symbol, "n": limit})
    rows = list(result.result_rows)
    rows.reverse()  # → ASC
    return [
        FundingRate(
            symbol=r[0], ts=_attach_utc(r[1]), rate=float(r[2]), mark_price=float(r[3]),
        )
        for r in rows
    ]


# ============================================================================
# 2 · Open Interest
# ============================================================================


async def insert_open_interest(
    client: AsyncClient, items: list[OpenInterest],
) -> int:
    if not items:
        return 0
    data = [
        [it.symbol, _strip_tz(it.ts), it.oi_coin, it.oi_usd]
        for it in items
    ]
    await client.insert("crypto_open_interest", data, column_names=list(_OI_COLUMNS))
    return len(items)


async def select_open_interest(
    client: AsyncClient, symbol: str, *, limit: int = 288,
) -> list[OpenInterest]:
    query = (
        "SELECT symbol, ts, oi_coin, oi_usd FROM crypto_open_interest "
        "WHERE symbol = %(s)s ORDER BY ts DESC LIMIT %(n)s"
    )
    result = await client.query(query, parameters={"s": symbol, "n": limit})
    rows = list(result.result_rows)
    rows.reverse()
    return [
        OpenInterest(
            symbol=r[0], ts=_attach_utc(r[1]), oi_coin=float(r[2]), oi_usd=float(r[3]),
        )
        for r in rows
    ]


# ============================================================================
# 3 · Long/Short Ratio
# ============================================================================


async def insert_long_short(
    client: AsyncClient, items: list[LongShortRatio],
) -> int:
    if not items:
        return 0
    data = [
        [
            it.symbol, _strip_tz(it.ts),
            it.top_account_long, it.top_account_short, it.top_account_ratio,
            it.top_position_long, it.top_position_short, it.top_position_ratio,
            it.taker_buy_vol, it.taker_sell_vol, it.taker_ratio,
        ]
        for it in items
    ]
    await client.insert("crypto_long_short_ratio", data, column_names=list(_LONG_SHORT_COLUMNS))
    return len(items)


async def select_long_short(
    client: AsyncClient, symbol: str, *, limit: int = 288,
) -> list[LongShortRatio]:
    query = (
        "SELECT symbol, ts, "
        "top_account_long, top_account_short, top_account_ratio, "
        "top_position_long, top_position_short, top_position_ratio, "
        "taker_buy_vol, taker_sell_vol, taker_ratio "
        "FROM crypto_long_short_ratio "
        "WHERE symbol = %(s)s ORDER BY ts DESC LIMIT %(n)s"
    )
    result = await client.query(query, parameters={"s": symbol, "n": limit})
    rows = list(result.result_rows)
    rows.reverse()
    return [
        LongShortRatio(
            symbol=r[0], ts=_attach_utc(r[1]),
            top_account_long=float(r[2]), top_account_short=float(r[3]), top_account_ratio=float(r[4]),
            top_position_long=float(r[5]), top_position_short=float(r[6]), top_position_ratio=float(r[7]),
            taker_buy_vol=float(r[8]), taker_sell_vol=float(r[9]), taker_ratio=float(r[10]),
        )
        for r in rows
    ]


# ============================================================================
# 4 · 24h Ticker
# ============================================================================


async def insert_tickers_24h(
    client: AsyncClient, items: list[Ticker24h],
) -> int:
    if not items:
        return 0
    data = [
        [
            it.symbol, it.instrument, _strip_tz(it.ts),
            it.last_price, it.change_pct_24h, it.high_24h, it.low_24h,
            it.volume_24h, it.quote_volume_24h, it.count_24h,
        ]
        for it in items
    ]
    await client.insert("crypto_ticker_24h", data, column_names=list(_TICKER_24H_COLUMNS))
    return len(items)


async def select_latest_tickers(
    client: AsyncClient,
    *,
    instrument: str = "spot",
    sort_by: str = "change_pct_24h",
    order: str = "DESC",
    limit: int = 20,
) -> list[Ticker24h]:
    """取每个 symbol 的最新一行 ticker · 按 sort_by 排序 · 取 top N。

    使用 ReplacingMergeTree FINAL · 自动去重每个 (symbol, ts) 组的最新行。
    SQL injection 防御:sort_by 和 order 做白名单校验。
    """
    sort_by_safe = {
        "change_pct_24h", "quote_volume_24h", "last_price",
    }
    order_safe = {"DESC", "ASC"}
    if sort_by not in sort_by_safe:
        raise ValueError(f"sort_by must be one of {sort_by_safe} · got {sort_by}")
    order_upper = order.upper()
    if order_upper not in order_safe:
        raise ValueError(f"order must be DESC or ASC · got {order}")

    # 每个 symbol 取最新 ts 的一行 · 然后按 sort_by 排序
    query = f"""
        SELECT symbol, instrument, ts, last_price, change_pct_24h,
               high_24h, low_24h, volume_24h, quote_volume_24h, count_24h
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY ts DESC) AS rn
            FROM crypto_ticker_24h FINAL
            WHERE instrument = %(inst)s
        )
        WHERE rn = 1
        ORDER BY {sort_by} {order_upper}
        LIMIT %(n)s
    """
    result = await client.query(query, parameters={"inst": instrument, "n": limit})
    rows = list(result.result_rows)
    return [
        Ticker24h(
            symbol=r[0], instrument=r[1], ts=_attach_utc(r[2]),
            last_price=float(r[3]), change_pct_24h=float(r[4]),
            high_24h=float(r[5]), low_24h=float(r[6]),
            volume_24h=float(r[7]), quote_volume_24h=float(r[8]),
            count_24h=int(r[9]),
        )
        for r in rows
    ]


# ============================================================================
# 5 · Market Overview + Fear & Greed
# ============================================================================


async def insert_market_overview(
    client: AsyncClient, ov: MarketOverview,
) -> int:
    """单行写 · ReplacingMergeTree 按 ts 去重。"""
    data = [[
        _strip_tz(ov.ts),
        ov.total_market_cap_usd, ov.total_volume_24h_usd,
        ov.btc_dominance, ov.eth_dominance,
        ov.fear_greed_value, ov.fear_greed_classification,
        ov.derivatives_oi_usd, ov.derivatives_volume_24h_usd,
    ]]
    await client.insert("crypto_market_overview", data, column_names=list(_OVERVIEW_COLUMNS))
    return 1


async def select_latest_overview(client: AsyncClient) -> MarketOverview | None:
    """最新一行 overview · 不存在返 None。"""
    query = (
        "SELECT ts, total_market_cap_usd, total_volume_24h_usd, "
        "btc_dominance, eth_dominance, "
        "fear_greed_value, fear_greed_classification, "
        "derivatives_oi_usd, derivatives_volume_24h_usd "
        "FROM crypto_market_overview FINAL "
        "ORDER BY ts DESC LIMIT 1"
    )
    result = await client.query(query)
    rows = list(result.result_rows)
    if not rows:
        return None
    r = rows[0]
    return MarketOverview(
        ts=_attach_utc(r[0]),
        total_market_cap_usd=float(r[1]),
        total_volume_24h_usd=float(r[2]),
        btc_dominance=float(r[3]),
        eth_dominance=float(r[4]),
        fear_greed_value=int(r[5]),
        fear_greed_classification=str(r[6]),
        derivatives_oi_usd=float(r[7]),
        derivatives_volume_24h_usd=float(r[8]),
    )


async def select_fear_greed_series(
    client: AsyncClient, *, limit: int = 30,
) -> list[FearGreedPoint]:
    """FGI 时间序列 · 取最新 N 天 · 返 ASC。

    从 market_overview 表抽 (ts, fear_greed_value, classification) · 按天去重。
    """
    query = """
        SELECT toStartOfDay(ts) AS day_ts,
               argMax(fear_greed_value, ts) AS value,
               argMax(fear_greed_classification, ts) AS classification
        FROM crypto_market_overview
        WHERE fear_greed_value > 0
        GROUP BY day_ts
        ORDER BY day_ts DESC
        LIMIT %(n)s
    """
    result = await client.query(query, parameters={"n": limit})
    rows = list(result.result_rows)
    rows.reverse()
    return [
        FearGreedPoint(
            ts=_attach_utc(r[0]), value=int(r[1]), classification=str(r[2]),
        )
        for r in rows
    ]


async def merge_fear_greed_into_latest_overview(
    client: AsyncClient, *, fgi_value: int, fgi_classification: str,
) -> int:
    """alternative.me 拉到 FGI 后 · 更新最新 overview 行的 FGI 字段。

    策略:不修改 · 而是插入新行(同 ts 不同 ingested_at)·
    ReplacingMergeTree 按 ingested_at 取最大 · 自动覆盖。

    简化做法:直接 INSERT 一行新 overview · 其他字段从 select_latest_overview 继承。
    """
    latest = await select_latest_overview(client)
    if latest is None:
        # 没有任何 overview · 先 stub 一行
        stub = MarketOverview(
            ts=datetime.now(tz=UTC),
            total_market_cap_usd=0, total_volume_24h_usd=0,
            btc_dominance=0, eth_dominance=0,
            fear_greed_value=fgi_value,
            fear_greed_classification=fgi_classification,
        )
        return await insert_market_overview(client, stub)
    # 继承其他字段 · 更新 FGI
    updated = MarketOverview(
        ts=datetime.now(tz=UTC),
        total_market_cap_usd=latest.total_market_cap_usd,
        total_volume_24h_usd=latest.total_volume_24h_usd,
        btc_dominance=latest.btc_dominance,
        eth_dominance=latest.eth_dominance,
        fear_greed_value=fgi_value,
        fear_greed_classification=fgi_classification,
        derivatives_oi_usd=latest.derivatives_oi_usd,
        derivatives_volume_24h_usd=latest.derivatives_volume_24h_usd,
    )
    return await insert_market_overview(client, updated)
