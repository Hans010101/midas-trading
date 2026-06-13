"""Worker 启动时确保 ClickHouse 表存在(幂等 · 自包含)· M2-C.2.1。

为什么需要本模块:
    update.sh(部署脚本)只跑 alembic(PostgreSQL 迁移),**没有 ClickHouse 建表
    步骤**。docker/clickhouse-init.sql 只在 CH 容器【首次启动 / 全新数据卷】时由
    /docker-entrypoint-initdb.d 执行;对已存在的 CH 实例,新增表不会自动建。
    每次部署都会 rebuild worker → worker 进程起来时触发 worker_ready 信号 →
    本模块跑 CREATE TABLE IF NOT EXISTS(幂等),零手动步骤,对所有未来 CH 表通用。

红线:只 DDL · 不写业务数据 · 不调任何上游/交易接口。

⚠️ 这里的 DDL 必须与 docker/clickhouse-init.sql 中对应表保持一致(双写不可避免:
   一个给 docker-entrypoint 全新装,一个给 worker 启动幂等 ensure)。
"""

from __future__ import annotations

import logging

import clickhouse_connect

from app.core.config import settings

logger = logging.getLogger(__name__)


# crypto_premium_index · 与 docker/clickhouse-init.sql 保持一致(M2-C.2.1)
_CREATE_PREMIUM_INDEX = """
CREATE TABLE IF NOT EXISTS crypto_premium_index (
    symbol String,
    ts DateTime,
    mark_price Float64,
    index_price Float64,
    last_funding_rate Float64,
    next_funding_time DateTime,
    funding_interval_hours UInt8 DEFAULT 8,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
TTL ingested_at + INTERVAL 7 DAY
SETTINGS index_granularity = 8192
"""

# crypto_orderbook_depth · 盘口深度 top-10 档(沙盘三期第二批 · 刀1)· 与 init.sql 一致
# flatten 10 档成列(bid/ask × price/qty)· ReplacingMergeTree 按 (symbol, ts) 去重 · 7d TTL(磁盘纪律)
_CREATE_ORDERBOOK_DEPTH = """
CREATE TABLE IF NOT EXISTS crypto_orderbook_depth (
    symbol String,
    ts DateTime,
    bid1_price Float64, bid2_price Float64, bid3_price Float64, bid4_price Float64,
    bid5_price Float64, bid6_price Float64, bid7_price Float64, bid8_price Float64,
    bid9_price Float64, bid10_price Float64,
    bid1_qty Float64, bid2_qty Float64, bid3_qty Float64, bid4_qty Float64,
    bid5_qty Float64, bid6_qty Float64, bid7_qty Float64, bid8_qty Float64,
    bid9_qty Float64, bid10_qty Float64,
    ask1_price Float64, ask2_price Float64, ask3_price Float64, ask4_price Float64,
    ask5_price Float64, ask6_price Float64, ask7_price Float64, ask8_price Float64,
    ask9_price Float64, ask10_price Float64,
    ask1_qty Float64, ask2_qty Float64, ask3_qty Float64, ask4_qty Float64,
    ask5_qty Float64, ask6_qty Float64, ask7_qty Float64, ask8_qty Float64,
    ask9_qty Float64, ask10_qty Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
TTL ingested_at + INTERVAL 7 DAY
SETTINGS index_granularity = 8192
"""

# market_index_snapshot · 大盘指数快照(0023 阶段③ · 3.1)· cn/us 共表 · 与 init.sql 一致
_CREATE_MARKET_INDEX_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS market_index_snapshot (
    market String,
    symbol String,
    name String,
    ts DateTime,
    last_point Float64,
    prev_close Float64,
    change_point Float64,
    change_pct Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (market, symbol, ts)
TTL ingested_at + INTERVAL 7 DAY
SETTINGS index_granularity = 8192
"""

# market_trade_calendar · 交易日历(0023 阶段③ · 3.1)· 目前仅 cn · 与 init.sql 一致
_CREATE_MARKET_TRADE_CALENDAR = """
CREATE TABLE IF NOT EXISTS market_trade_calendar (
    market String,
    trade_date Date,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (market, trade_date)
SETTINGS index_granularity = 8192
"""

# cn_spot_snapshot · A股全市场个股快照(0023 阶段③ · 3.2)· 与 init.sql 一致
_CREATE_CN_SPOT_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS cn_spot_snapshot (
    symbol String,
    name String,
    ts DateTime,
    last_price Float64,
    change_pct Float64,
    change_amount Float64,
    amount Float64,
    volume Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toDate(ts)
ORDER BY (ts, symbol)
TTL ingested_at + INTERVAL 2 DAY
SETTINGS index_granularity = 8192
"""

# cn_market_breadth · A股情绪条单行(0023 阶段③ · 3.2)· 与 init.sql 一致
_CREATE_CN_MARKET_BREADTH = """
CREATE TABLE IF NOT EXISTS cn_market_breadth (
    ts DateTime,
    up_count UInt32,
    down_count UInt32,
    flat_count UInt32,
    limit_up_count UInt32,
    limit_down_count UInt32,
    total_amount Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY ts
TTL ingested_at + INTERVAL 30 DAY
SETTINGS index_granularity = 8192
"""

# cn_sector_snapshot · A股行业板块快照(0023 阶段③ · 3.2)· 与 init.sql 一致
_CREATE_CN_SECTOR_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS cn_sector_snapshot (
    name String,
    ts DateTime,
    change_pct Float64,
    stock_count UInt32,
    total_amount Float64,
    leader_name String,
    leader_change_pct Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (ts, name)
TTL ingested_at + INTERVAL 2 DAY
SETTINGS index_granularity = 8192
"""

# us_spot_snapshot · 美股策展池个股快照(0023 阶段③ · 3.3)· 与 init.sql 一致
_CREATE_US_SPOT_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS us_spot_snapshot (
    symbol String,
    name String,
    sector String,
    ts DateTime,
    last_price Float64,
    change_pct Float64,
    amount Float64,
    volume Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (ts, symbol)
TTL ingested_at + INTERVAL 2 DAY
SETTINGS index_granularity = 8192
"""

# us_sector_snapshot · 美股板块聚合(行业 + 中概股)(0023 阶段③ · 3.3)· 与 init.sql 一致
_CREATE_US_SECTOR_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS us_sector_snapshot (
    name String,
    ts DateTime,
    change_pct Float64,
    stock_count UInt32,
    total_amount Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (ts, name)
TTL ingested_at + INTERVAL 2 DAY
SETTINGS index_granularity = 8192
"""

# hk_spot_snapshot · 港股全市场个股快照 · 新浪 stock_hk_spot ~2764 只 · 与 init.sql 一致
_CREATE_HK_SPOT_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS hk_spot_snapshot (
    symbol String,
    name String,
    ts DateTime,
    last_price Float64,
    change_pct Float64,
    change_amount Float64,
    amount Float64,
    volume Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toDate(ts)
ORDER BY (ts, symbol)
TTL ingested_at + INTERVAL 2 DAY
SETTINGS index_granularity = 8192
"""

# hk_market_breadth · 港股情绪条单行 · ★港股无涨跌停 → 无 limit 列 · 与 init.sql 一致
_CREATE_HK_MARKET_BREADTH = """
CREATE TABLE IF NOT EXISTS hk_market_breadth (
    ts DateTime,
    up_count UInt32,
    down_count UInt32,
    flat_count UInt32,
    total_amount Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY ts
TTL ingested_at + INTERVAL 30 DAY
SETTINGS index_granularity = 8192
"""

# ADR 0035 阶段 A · market_index_snapshot 幂等加列(复用本表装全球指标概览 · 零迁移 · 非破坏)·
#   与 docker/clickhouse-init.sql 保持一致 · 老库靠 ALTER IF NOT EXISTS,新库靠 init.sql
_ALTER_OVERVIEW_CATEGORY = (
    "ALTER TABLE market_index_snapshot ADD COLUMN IF NOT EXISTS category String DEFAULT ''"
)
_ALTER_OVERVIEW_UNIT = (
    "ALTER TABLE market_index_snapshot ADD COLUMN IF NOT EXISTS unit String DEFAULT 'point'"
)

# 刀C · crypto_long_short_ratio 幂等加列(globalLongShortAccountRatio 全市场人数比)·
#   与 docker/clickhouse-init.sql 保持一致 · 老库靠 ALTER IF NOT EXISTS,新库靠 init.sql ·
#   ADD COLUMN 是元数据级操作(瞬时 · 不重写数据)· DEFAULT 0 = 老行「未采」哨兵
_ALTER_LS_GLOBAL_LONG = (
    "ALTER TABLE crypto_long_short_ratio"
    " ADD COLUMN IF NOT EXISTS global_account_long Float64 DEFAULT 0"
)
_ALTER_LS_GLOBAL_SHORT = (
    "ALTER TABLE crypto_long_short_ratio"
    " ADD COLUMN IF NOT EXISTS global_account_short Float64 DEFAULT 0"
)
_ALTER_LS_GLOBAL_RATIO = (
    "ALTER TABLE crypto_long_short_ratio"
    " ADD COLUMN IF NOT EXISTS global_account_ratio Float64 DEFAULT 0"
)

# 未来新增 CH 表 → 往这个 list 里加一条幂等 DDL 即可
_DDL_STATEMENTS: tuple[str, ...] = (
    _CREATE_PREMIUM_INDEX,
    _CREATE_ORDERBOOK_DEPTH,
    _CREATE_MARKET_INDEX_SNAPSHOT,
    _ALTER_OVERVIEW_CATEGORY,
    _ALTER_OVERVIEW_UNIT,
    _ALTER_LS_GLOBAL_LONG,
    _ALTER_LS_GLOBAL_SHORT,
    _ALTER_LS_GLOBAL_RATIO,
    _CREATE_MARKET_TRADE_CALENDAR,
    _CREATE_CN_SPOT_SNAPSHOT,
    _CREATE_CN_MARKET_BREADTH,
    _CREATE_CN_SECTOR_SNAPSHOT,
    _CREATE_US_SPOT_SNAPSHOT,
    _CREATE_US_SECTOR_SNAPSHOT,
    _CREATE_HK_SPOT_SNAPSHOT,
    _CREATE_HK_MARKET_BREADTH,
)


def ensure_crypto_ch_tables() -> None:
    """worker 启动时幂等建表 · 失败只告警不阻断 worker 启动(行情采集仍可跑)。"""
    try:
        client = clickhouse_connect.get_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
            database=settings.clickhouse_database,
            settings={"session_timezone": "UTC"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ch_schema] 连 ClickHouse 失败 · 跳过建表:%s", exc)
        return
    try:
        for ddl in _DDL_STATEMENTS:
            client.command(ddl)
        logger.info("[ch_schema] CH 表 ensure 完成(%d 条 DDL)", len(_DDL_STATEMENTS))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ch_schema] 建表 DDL 执行失败:%s", exc)
    finally:
        client.close()
