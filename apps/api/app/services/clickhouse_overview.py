"""全球指标概览 · ClickHouse 读写(ADR 0035 阶段 A)。

- 写:yfinance 概览行 → `market_index_snapshot`(复用表 · category/unit 列区分 · 零迁移)。
- 读:① yfinance 概览 = `market_index_snapshot` 的 category != '' 行(避开 cn/us 首页旧行)
       ② 加密 = 复用 `crypto_ticker_24h`(ccxt 已采)读 BTC/ETH 最新。
时区铁律:写入 tz-aware UTC(0002 教训)· 读出补 UTC。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.schemas.overview import OverviewQuote
from app.services.global_overview_config import CRYPTO_NAME

if TYPE_CHECKING:
    from clickhouse_connect.driver.asyncclient import AsyncClient

logger = logging.getLogger(__name__)

_OVERVIEW_COLUMNS = (
    "market", "symbol", "name", "category", "unit", "ts",
    "last_point", "prev_close", "change_point", "change_pct",
)


def _aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _attach_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def insert_overview_quotes(client: AsyncClient, items: list[OverviewQuote]) -> int:
    """批量写全球指标快照 → market_index_snapshot(category/unit 区分)。"""
    if not items:
        return 0
    data = [
        [
            it.market, it.symbol, it.name, it.category, it.unit, _aware_utc(it.ts),
            it.last_point, it.prev_close, it.change_point, it.change_pct,
        ]
        for it in items
    ]
    await client.insert(
        "market_index_snapshot", data, column_names=list(_OVERVIEW_COLUMNS),
    )
    return len(items)


async def select_latest_overview(client: AsyncClient) -> list[OverviewQuote]:
    """读 yfinance 概览(category != '')· 每 symbol 最新一行 · 异常行(last<=0)略过不造假。"""
    query = """
        SELECT market, symbol, name, category, unit, ts,
               last_point, prev_close, change_point, change_pct
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY ts DESC) AS rn
            FROM market_index_snapshot FINAL
            WHERE category != ''
        )
        WHERE rn = 1
    """
    result = await client.query(query)
    out: list[OverviewQuote] = []
    for r in result.result_rows:
        last_point = float(r[6])
        if last_point <= 0:
            continue
        out.append(
            OverviewQuote(
                market=str(r[0]), symbol=str(r[1]), name=str(r[2]),
                category=str(r[3]), unit=str(r[4]), ts=_attach_utc(r[5]),
                last_point=last_point, prev_close=float(r[7]),
                change_point=float(r[8]), change_pct=float(r[9]),
            ),
        )
    return out


async def select_crypto_overview(
    client: AsyncClient, symbols: tuple[str, ...],
) -> list[OverviewQuote]:
    """读加密概览 · 复用 `crypto_ticker_24h`(ccxt 已采)· spot · 每 symbol 最新一行。

    crypto_ticker_24h 只有 last_price + change_pct_24h → 反推 prev_close / change_point。
    """
    if not symbols:
        return []
    query = """
        SELECT symbol, last_price, change_pct_24h, ts
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY ts DESC) AS rn
            FROM crypto_ticker_24h FINAL
            WHERE instrument = 'spot' AND symbol IN %(syms)s
        )
        WHERE rn = 1
    """
    result = await client.query(query, parameters={"syms": list(symbols)})
    out: list[OverviewQuote] = []
    for r in result.result_rows:
        symbol = str(r[0])
        last = float(r[1])
        pct = float(r[2])
        if last <= 0:
            continue
        prev = last / (1 + pct / 100) if pct != -100 else last  # noqa: PLR2004
        out.append(
            OverviewQuote(
                market="crypto", symbol=symbol, name=CRYPTO_NAME.get(symbol, symbol),
                category="crypto", unit="price", ts=_attach_utc(r[3]),
                last_point=last, prev_close=prev,
                change_point=last - prev, change_pct=pct,
            ),
        )
    return out
