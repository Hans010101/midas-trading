"""ClickHouse 写入/查询 helpers · Crypto Pro 5 张新表(0017 ADR · M2-A)。

跟 clickhouse_client.py 互补 · 不污染原 ClickHouseClient 类。
将来 M2-E 性能优化时可考虑合并到 ClickHouseClient,目前独立模块更清晰。

时区铁律(继承 0002 教训 · 跟能正常写的 kline 路径对齐):
- 写入前 ts 必须是 **tz-aware UTC**(_aware_utc)· 绝不传 naive
  (clickhouse-connect 对 naive 会按 OS 本地时区误转 · 8h 偏移)
- 读出后 ts 补 UTC tz(_attach_utc)
- 配套:用本模块 helper 的 client 必须设 session_timezone='UTC'
  (worker _get_ch_client / verify 临时 client 都已加)

ORDER BY DESC + Python reverse 模式(继承 0010 教训):
- 任何「取最新 N 条」语义必须 SQL 端 DESC LIMIT N · Python reverse 还原 ASC
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.schemas.crypto import (
    DEPTH_LEVELS,
    FearGreedPoint,
    FundingRate,
    LongShortRatio,
    MarketOverview,
    OpenInterest,
    OrderbookDepth,
    PremiumIndex,
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
    # 刀C · 全市场人数比(globalLongShortAccountRatio)· 0 = 未采哨兵
    "global_account_long", "global_account_short", "global_account_ratio",
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
_PREMIUM_INDEX_COLUMNS = (
    "symbol", "ts", "mark_price", "index_price",
    "last_funding_rate", "next_funding_time", "funding_interval_hours",
)


def _aware_utc(dt: datetime) -> datetime:
    """归一为 tz-aware UTC · 给 clickhouse-connect 写入用。

    跟 ClickHouseClient._to_aware_utc(能正常写的 kline 路径)一致。
    0002 教训第 3 条:**绝不传 naive datetime** 给 clickhouse-connect —
    它会用 OS 本地时区(Asia/Shanghai 等)做 astimezone(),naive 被当本地
    时间转 UTC,导致 8 小时偏移。M2-A 这几张表原先用 _strip_tz 传 naive,
    正好踩这个坑(funding ts 错位会直接污染 M2-C 资金费率结算)。
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


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
        [it.symbol, _aware_utc(it.ts), it.rate, it.mark_price]
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
        [it.symbol, _aware_utc(it.ts), it.oi_coin, it.oi_usd]
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
            it.symbol, _aware_utc(it.ts),
            it.top_account_long, it.top_account_short, it.top_account_ratio,
            it.top_position_long, it.top_position_short, it.top_position_ratio,
            it.taker_buy_vol, it.taker_sell_vol, it.taker_ratio,
            it.global_account_long, it.global_account_short, it.global_account_ratio,
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
        "taker_buy_vol, taker_sell_vol, taker_ratio, "
        "global_account_long, global_account_short, global_account_ratio "
        "FROM crypto_long_short_ratio "
        "WHERE symbol = %(s)s ORDER BY ts DESC LIMIT %(n)s"
    )
    result = await client.query(query, parameters={"s": symbol, "n": limit})
    rows = list(result.result_rows)
    rows.reverse()
    return [
        LongShortRatio(
            symbol=r[0], ts=_attach_utc(r[1]),
            top_account_long=float(r[2]), top_account_short=float(r[3]),
            top_account_ratio=float(r[4]),
            top_position_long=float(r[5]), top_position_short=float(r[6]),
            top_position_ratio=float(r[7]),
            taker_buy_vol=float(r[8]), taker_sell_vol=float(r[9]), taker_ratio=float(r[10]),
            global_account_long=float(r[11]), global_account_short=float(r[12]),
            global_account_ratio=float(r[13]),
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
            it.symbol, it.instrument, _aware_utc(it.ts),
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
        _aware_utc(ov.ts),
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

    # FGI 修复:global_overview_refresh(每 30min)写 overview 行时 FGI=0,会把
    # fear_greed_refresh(每 6h)合并进来的 FGI 覆盖掉 → 最新行 FGI 常为 0。
    # 这里独立取「最近一条 FGI>0」的值,不依赖最新行的 FGI,避免被周期性清零。
    fgi_value = int(r[5])
    fgi_classification = str(r[6])
    if fgi_value <= 0:
        fgi_q = await client.query(
            "SELECT fear_greed_value, fear_greed_classification "
            "FROM crypto_market_overview "
            "WHERE fear_greed_value > 0 ORDER BY ts DESC LIMIT 1"
        )
        fgi_rows = list(fgi_q.result_rows)
        if fgi_rows:
            fgi_value = int(fgi_rows[0][0])
            fgi_classification = str(fgi_rows[0][1])

    return MarketOverview(
        ts=_attach_utc(r[0]),
        total_market_cap_usd=float(r[1]),
        total_volume_24h_usd=float(r[2]),
        btc_dominance=float(r[3]),
        eth_dominance=float(r[4]),
        fear_greed_value=fgi_value,
        fear_greed_classification=fgi_classification,
        derivatives_oi_usd=float(r[7]),
        derivatives_volume_24h_usd=float(r[8]),
    )


async def select_tickers_by_symbols(
    client: AsyncClient, *, instrument: str, symbols: list[str],
) -> dict[str, Ticker24h]:
    """按 symbol 取最新 ticker(每 symbol 最新一行)· 返回 {symbol: Ticker24h}。

    给主页 BTC/ETH 价格卡用 —— 这两个不一定在「按涨跌幅 top100」榜单里,
    必须按 symbol 精确取,否则价格卡会因不在榜单而显示「—」(读取侧 bug)。
    """
    if not symbols:
        return {}
    query = """
        SELECT symbol, instrument, ts, last_price, change_pct_24h,
               high_24h, low_24h, volume_24h, quote_volume_24h, count_24h
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY ts DESC) AS rn
            FROM crypto_ticker_24h FINAL
            WHERE instrument = %(inst)s AND symbol IN %(syms)s
        )
        WHERE rn = 1
    """
    result = await client.query(
        query, parameters={"inst": instrument, "syms": symbols},
    )
    out: dict[str, Ticker24h] = {}
    for r in result.result_rows:
        out[str(r[0])] = Ticker24h(
            symbol=r[0], instrument=r[1], ts=_attach_utc(r[2]),
            last_price=float(r[3]), change_pct_24h=float(r[4]),
            high_24h=float(r[5]), low_24h=float(r[6]),
            volume_24h=float(r[7]), quote_volume_24h=float(r[8]),
            count_24h=int(r[9]),
        )
    return out


async def select_perp_total_quote_volume(client: AsyncClient) -> float:
    """USDT 永续最新 24H quote_volume 之和 = 合约总成交额(USDT 计价)。

    CoinGecko /global 的 derivatives_volume 在免费档拿不到(coingecko_source 里
    硬编码 0),所以主页「24H 合约总成交额」一直空。这里用我们已采集的 perp
    ticker 的 quote_volume_24h 求和 —— 全是真实数据,不伪造。

    刀B 口径修正(Hans 定量:USDT 永续 $47.24B/633 币 · USDC 永续 $6.42B/38 币 ·
    交割 $0.04B/4 币 · 下架残留=0):/fapi/v1/ticker/24hr 返回的是 USDT-M 全域,
    旧版全量求和把 USDC 永续 + 交割合约混进「永续口径」名不副实。现只算
    USDT 永续主力:endsWith 'USDT' 排除 USDC 永续;position(symbol,'_')=0 排除
    交割形态(BTCUSDT_250627 带下划线 · 比 LIKE '%\\_2%' 转义更稳的等价过滤)。
    """
    query = """
        SELECT sum(quote_volume_24h) FROM (
            SELECT quote_volume_24h,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY ts DESC) AS rn
            FROM crypto_ticker_24h FINAL
            WHERE instrument = 'perp'
              AND endsWith(symbol, 'USDT')
              AND position(symbol, '_') = 0
        )
        WHERE rn = 1
    """
    result = await client.query(query)
    rows = list(result.result_rows)
    if not rows or rows[0][0] is None:
        return 0.0
    return float(rows[0][0])


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


# ============================================================================
# 6 · 榜单级合约指标批量(M2-数据打磨·任务3)· 给列表页 3 列用
# ============================================================================


async def select_futures_metrics_batch(
    client: AsyncClient, *, symbols: list[str],
) -> dict[str, dict[str, float]]:
    """一次性取多个 symbol 的合约指标 · 给加密列表页「资金费率/账户多空比/OI 24H变化」3 列。

    symbol 用 Binance 风格(无斜杠 · 'BTCUSDT')· 跟 3 张合约表存储一致。
    返回 {symbol: {funding_rate, account_long_short_ratio, oi_change_pct_24h}}。
    不在采集名单(top100)里的 symbol 不会出现在结果里 → 前端显示「—」(不造假)。

    三张表分别 GROUP BY symbol 取最新值,Python 端合并。OI 24H 变化用近 24h 窗口的
    最新值 vs 最早值估算((now-then)/then)。
    """
    if not symbols:
        return {}
    out: dict[str, dict[str, float]] = {}

    # 1) 资金费率 · 每 symbol 最新 rate
    fr = await client.query(
        "SELECT symbol, argMax(rate, ts) FROM crypto_funding_rate FINAL "
        "WHERE symbol IN %(syms)s GROUP BY symbol",
        parameters={"syms": symbols},
    )
    for r in fr.result_rows:
        out.setdefault(str(r[0]), {})["funding_rate"] = float(r[1])

    # 2) 账户多空比 · 每 symbol 最新 top_account_ratio
    ls = await client.query(
        "SELECT symbol, argMax(top_account_ratio, ts) FROM crypto_long_short_ratio FINAL "
        "WHERE symbol IN %(syms)s GROUP BY symbol",
        parameters={"syms": symbols},
    )
    for r in ls.result_rows:
        out.setdefault(str(r[0]), {})["account_long_short_ratio"] = float(r[1])

    # 3) OI 24H 变化% · 近 24h 窗口内最新 vs 最早
    oi = await client.query(
        "SELECT symbol, argMax(oi_usd, ts) AS now_oi, argMin(oi_usd, ts) AS then_oi "
        "FROM crypto_open_interest FINAL "
        "WHERE symbol IN %(syms)s AND ts >= now() - INTERVAL 24 HOUR "
        "GROUP BY symbol",
        parameters={"syms": symbols},
    )
    for r in oi.result_rows:
        now_oi = float(r[1])
        then_oi = float(r[2])
        if then_oi > 0:
            out.setdefault(str(r[0]), {})["oi_change_pct_24h"] = (
                (now_oi - then_oi) / then_oi * 100
            )
    return out


# ============================================================================
# 7 · Premium Index(标记价/指数价/资金费)· M2-C.2.1 · ADR-0020
# ============================================================================


async def insert_premium_index(
    client: AsyncClient, items: list[PremiumIndex],
) -> int:
    """批量写 · ReplacingMergeTree 按 (symbol, ts) 去重。symbol Binance 风格无斜杠。"""
    if not items:
        return 0
    data = [
        [
            it.symbol, _aware_utc(it.ts), it.mark_price, it.index_price,
            it.last_funding_rate, _aware_utc(it.next_funding_time),
            it.funding_interval_hours,
        ]
        for it in items
    ]
    await client.insert(
        "crypto_premium_index", data, column_names=list(_PREMIUM_INDEX_COLUMNS),
    )
    return len(items)


# 盘口深度列(沙盘三期第二批 · flatten 10 档)· 与 ch_schema/init.sql 表列同序同名
_ORDERBOOK_DEPTH_COLUMNS: tuple[str, ...] = (
    "symbol", "ts",
    *(f"bid{i}_price" for i in range(1, DEPTH_LEVELS + 1)),
    *(f"bid{i}_qty" for i in range(1, DEPTH_LEVELS + 1)),
    *(f"ask{i}_price" for i in range(1, DEPTH_LEVELS + 1)),
    *(f"ask{i}_qty" for i in range(1, DEPTH_LEVELS + 1)),
)


async def insert_depth(client: AsyncClient, items: list[OrderbookDepth]) -> int:
    """批量写盘口深度 · ReplacingMergeTree 按 (symbol, ts) 去重 · flatten 10 档成列。

    每条 flatten 顺序:symbol, ts, bid1..10_price, bid1..10_qty, ask1..10_price, ask1..10_qty
    (与 _ORDERBOOK_DEPTH_COLUMNS 一致 · ClickHouse 按 column_names 名映射)。
    """
    if not items:
        return 0
    data = []
    for it in items:
        row: list[Any] = [it.symbol, _aware_utc(it.ts)]
        row.extend(price for price, _ in it.bids)
        row.extend(qty for _, qty in it.bids)
        row.extend(price for price, _ in it.asks)
        row.extend(qty for _, qty in it.asks)
        data.append(row)
    await client.insert(
        "crypto_orderbook_depth", data, column_names=list(_ORDERBOOK_DEPTH_COLUMNS),
    )
    return len(items)


async def select_premium_index_marks(
    client: AsyncClient, symbols: list[str],
) -> dict[str, Decimal]:
    """批量取多 symbol 最新 mark_price · 给撮合/强平价源用(注入式换源)。

    symbol 用 Binance 风格无斜杠 'BTCUSDT'(跟表存储一致 · **不转 ccxt**)。
    返回 {symbol: Decimal(mark_price)} · 只含 mark>0 的;无数据的 symbol 不出现
    (调用方据此兜底回 perp ticker · 保证撮合/强平零回归)。

    用 Decimal(str(float)) 转换:撮合/强平引擎全程 Decimal 计价,这里桥接
    CH 的 Float64 → Decimal,跟 perp ticker 价源路径(perp.py)一致。
    """
    if not symbols:
        return {}
    query = (
        "SELECT symbol, argMax(mark_price, ts) FROM crypto_premium_index FINAL "
        "WHERE symbol IN %(syms)s GROUP BY symbol"
    )
    result = await client.query(query, parameters={"syms": symbols})
    out: dict[str, Decimal] = {}
    for r in result.result_rows:
        mark = float(r[1])
        if mark > 0:
            out[str(r[0])] = Decimal(str(mark))
    return out


async def select_premium_index_series(
    client: AsyncClient, symbol: str, *, limit: int = 288,
) -> list[tuple[datetime, float, float]]:
    """某 symbol 最新 N 条 premium 时序 (ts, mark_price, index_price) · 返 ASC(0010 教训)。

    给详情页 ⑥ 基差图(M2-C.2.4)· 基差率 = (mark - index) / index 由调用方算。
    288 点 ≈ 24h @ 1min(premium_index_scan 每分钟一条)。
    """
    query = (
        "SELECT ts, mark_price, index_price FROM crypto_premium_index "
        "WHERE symbol = %(s)s ORDER BY ts DESC LIMIT %(n)s"
    )
    result = await client.query(query, parameters={"s": symbol, "n": limit})
    rows = list(result.result_rows)
    rows.reverse()  # → ASC
    return [(_attach_utc(r[0]), float(r[1]), float(r[2])) for r in rows]


async def select_latest_premium_index(
    client: AsyncClient, symbol: str,
) -> PremiumIndex | None:
    """单 symbol 最新一行 premiumIndex · 给 futures/info 用(真 nextFundingTime/index)。

    不存在(未采到该 symbol)返 None · 调用方兜底到 funding 表 +8h 估算。
    """
    query = (
        "SELECT symbol, ts, mark_price, index_price, "
        "last_funding_rate, next_funding_time, funding_interval_hours "
        "FROM crypto_premium_index FINAL "
        "WHERE symbol = %(s)s ORDER BY ts DESC LIMIT 1"
    )
    result = await client.query(query, parameters={"s": symbol})
    rows = list(result.result_rows)
    if not rows:
        return None
    r = rows[0]
    return PremiumIndex(
        symbol=str(r[0]), ts=_attach_utc(r[1]),
        mark_price=float(r[2]), index_price=float(r[3]),
        last_funding_rate=float(r[4]), next_funding_time=_attach_utc(r[5]),
        funding_interval_hours=int(r[6]),
    )
