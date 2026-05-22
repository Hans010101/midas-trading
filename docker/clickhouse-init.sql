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

-- ============================================================================
-- M2-A · Crypto Pro 数据层(0017 ADR · 仅 crypto-preview 详情页所需的 5 张新表)
-- ============================================================================
-- 说明:这 5 张表全部 crypto_ 前缀全新表名 · 全部 CREATE TABLE IF NOT EXISTS ·
--      不碰现有 kline / symbol_meta 表(M2-B 的 kline.instrument 列改动不在本次范围)。

-- Crypto Pro · funding rate 资金费率时间序列(perp 专属 · symbol = "BTCUSDT" 无斜杠)
CREATE TABLE IF NOT EXISTS crypto_funding_rate (
    symbol String,
    ts DateTime,                            -- 资金费率结算时间(UTC · 8h 整点)
    rate Float64,                           -- decimal · 0.0001 = 0.01%
    mark_price Float64,                     -- 结算时标记价
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
SETTINGS index_granularity = 8192;

-- Crypto Pro · open interest 未平仓量时间序列(5min 栅格)
CREATE TABLE IF NOT EXISTS crypto_open_interest (
    symbol String,
    ts DateTime,                            -- 5min 采样栅格
    oi_coin Float64,                        -- OI in base coin (BTC)
    oi_usd Float64,                         -- OI in USD
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
SETTINGS index_granularity = 8192;

-- Crypto Pro · long/short 多空比时间序列(三套指标同表:账户/持仓/taker)
CREATE TABLE IF NOT EXISTS crypto_long_short_ratio (
    symbol String,
    ts DateTime,
    -- top trader 账户多空比
    top_account_long Float64,               -- 多账户占比(0..1)
    top_account_short Float64,
    top_account_ratio Float64,              -- long / short
    -- top trader 持仓多空比
    top_position_long Float64,
    top_position_short Float64,
    top_position_ratio Float64,
    -- taker buy/sell 量比
    taker_buy_vol Float64,
    taker_sell_vol Float64,
    taker_ratio Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
SETTINGS index_granularity = 8192;

-- Crypto Pro · 24h ticker 全币种行情快照(symbol = "BTC/USDT" ccxt 风格 · TTL 30 天)
CREATE TABLE IF NOT EXISTS crypto_ticker_24h (
    symbol String,                          -- "BTC/USDT" ccxt 风格
    instrument Enum8('spot'=1, 'perp'=2),
    ts DateTime,
    last_price Float64,
    change_pct_24h Float64,                 -- 24h 涨跌(% · 已乘 100)
    high_24h Float64,
    low_24h Float64,
    volume_24h Float64,                     -- base 币种
    quote_volume_24h Float64,               -- USDT 计
    count_24h UInt64 DEFAULT 0,             -- 24h 笔数(spot 才有)
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (instrument, symbol, ts)
TTL ingested_at + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;

-- Crypto Pro · 全市场 overview + Fear & Greed Index(全市场单点快照)
CREATE TABLE IF NOT EXISTS crypto_market_overview (
    ts DateTime,
    -- CoinGecko /global
    total_market_cap_usd Float64,
    total_volume_24h_usd Float64,
    btc_dominance Float64,                  -- 0..100
    eth_dominance Float64,
    -- alternative.me Fear & Greed
    fear_greed_value UInt8 DEFAULT 0,       -- 0..100
    fear_greed_classification String DEFAULT '',
    -- CoinGecko derivatives
    derivatives_oi_usd Float64 DEFAULT 0,
    derivatives_volume_24h_usd Float64 DEFAULT 0,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY ts
SETTINGS index_granularity = 8192;
