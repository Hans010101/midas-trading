-- 点金 Midas · ClickHouse 初始化
-- 对应 04 文档 Task 2.3 · K 线 + symbol_meta 表
-- 容器首次启动时由 /docker-entrypoint-initdb.d/init.sql 自动执行

CREATE TABLE IF NOT EXISTS kline (
    symbol String,
    market Enum8('cn'=1, 'us'=2, 'crypto'=3),
    period Enum8('1m'=1, '5m'=2, '15m'=3, '30m'=4, '1h'=5, '1d'=6, '1w'=7),
    ts DateTime,
    open Float64,
    high Float64,
    low Float64,
    close Float64,
    volume Float64,
    amount Float64
) ENGINE = MergeTree
PARTITION BY (market, toYear(ts))
ORDER BY (symbol, period, ts)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS symbol_meta (
    symbol String,
    market Enum8('cn'=1, 'us'=2, 'crypto'=3),
    name String,
    name_en String,
    listed_date Date,
    is_active UInt8 DEFAULT 1,
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (market, symbol);
