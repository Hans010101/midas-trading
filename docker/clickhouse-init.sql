-- 点金 Midas · ClickHouse 初始化
-- 对应 04 文档 Task 2.3 · K 线 + symbol_meta 表
-- 容器首次启动时由 /docker-entrypoint-initdb.d/init.sql 自动执行

CREATE TABLE IF NOT EXISTS kline (
    symbol String,
    market Enum8('cn'=1, 'us'=2, 'crypto'=3, 'hk'=4),
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
    market Enum8('cn'=1, 'us'=2, 'crypto'=3, 'hk'=4),
    name String,
    name_en String,
    listed_date Date,
    is_active UInt8 DEFAULT 1,
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (market, symbol);

-- ============================================================================
-- M2-A · Crypto Pro 数据层(0017 ADR)
-- ============================================================================
-- kline 表加 instrument 列 · 用于区分 spot / perp 合约 K 线
-- 老数据默认 'spot' · 无需 backfill
-- 注意:容器初次启动时执行此 init.sql · ALTER 用 IF NOT EXISTS column 守卫
--      (ClickHouse 24+ 支持 ADD COLUMN IF NOT EXISTS)

ALTER TABLE kline
    ADD COLUMN IF NOT EXISTS instrument Enum8('spot'=1, 'perp'=2) DEFAULT 'spot'
    AFTER market;

-- ============================================================================
-- Crypto Pro · funding rate 资金费率时间序列
-- ============================================================================
-- symbol 用 Binance Futures 风格 "BTCUSDT"(无斜杠)· 因 funding 是 perp 专属概念
-- rate 是 decimal · 0.0001 = 0.01% · 不要乘 100 存
-- 上游 Binance fapi/v1/fundingRate · 8h 结算一次

CREATE TABLE IF NOT EXISTS crypto_funding_rate (
    symbol String,
    ts DateTime,                            -- 资金费率结算时间(UTC · 8h 整点)
    rate Float64,                           -- decimal · 0.0001 = 0.01%
    mark_price Float64,                     -- 结算时标记价
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
-- ADR-0018:全量采集后无限累积 · 留 60 天滚动窗口(对齐 ticker 表的 TTL 思路;
--          合约维度图算 OI 24H/历史趋势够用)· 超期数据后台 merge 自动清,磁盘稳态封顶。
TTL ingested_at + INTERVAL 60 DAY
SETTINGS index_granularity = 8192;

-- ============================================================================
-- Crypto Pro · open interest 未平仓量时间序列
-- ============================================================================
-- 上游 Binance futures/data/openInterestHist · 默认 period=5m
-- oi_coin = 折算到币(BTC etc.)· oi_usd = 折算到美元

CREATE TABLE IF NOT EXISTS crypto_open_interest (
    symbol String,
    ts DateTime,                            -- 5min 采样栅格
    oi_coin Float64,                        -- OI in base coin (BTC)
    oi_usd Float64,                         -- OI in USD
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
-- ADR-0018:全量采集后无限累积 · 留 60 天滚动窗口(对齐 ticker 表的 TTL 思路;
--          合约维度图算 OI 24H/历史趋势够用)· 超期数据后台 merge 自动清,磁盘稳态封顶。
TTL ingested_at + INTERVAL 60 DAY
SETTINGS index_granularity = 8192;

-- ============================================================================
-- Crypto Pro · long/short 多空比时间序列
-- ============================================================================
-- 三套指标同表:top trader 账户多空比 + top trader 持仓多空比 + taker buy/sell
-- 上游 Binance:
--   /futures/data/topLongShortAccountRatio
--   /futures/data/topLongShortPositionRatio
--   /futures/data/takerlongshortRatio
-- 一次 Celery 任务并发拉 3 个上游 · 合并写入

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
-- ADR-0018:全量采集后无限累积 · 留 60 天滚动窗口(对齐 ticker 表的 TTL 思路;
--          合约维度图算 OI 24H/历史趋势够用)· 超期数据后台 merge 自动清,磁盘稳态封顶。
TTL ingested_at + INTERVAL 60 DAY
SETTINGS index_granularity = 8192;

-- ============================================================================
-- Crypto Pro · 24h ticker 全币种行情快照
-- ============================================================================
-- 上游 Binance Spot REST /api/v3/ticker/24hr + Futures /fapi/v1/ticker/24hr
-- 一次扫全市场 600+ symbols · 每分钟拉一次 · 用于涨幅榜
-- TTL 30 天 · 长期归档走冷存(M2-E)
-- symbol 统一 ccxt 风格 "BTC/USDT"(因要跟现有 spot kline 表对齐)

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

-- ============================================================================
-- Crypto Pro · 全市场 overview + Fear & Greed Index
-- ============================================================================
-- 上游:
--   CoinGecko /api/v3/global · 5min 拉一次 · 提供 total_market_cap / dominance
--   alternative.me /fng · 1day · 提供 fear_greed_value + classification
-- 同表存因都是「全市场单点快照」· 节省一张表

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

-- ============================================================================
-- Crypto Pro · premium index 标记价/指数价/资金费 实时快照(M2-C.2.1 · ADR-0020)
-- ============================================================================
-- 上游 Binance fapi/v1/premiumIndex(无 symbol = 全市场单请求 · 极轻)· 每 1min 采
-- symbol 用 Binance Futures 风格 "BTCUSDT"(无斜杠)· 跟其余 perp 表一致
-- 用途:
--   mark_price  → 撮合/强平价源(M2-C.2.1 起替代 perp ticker last_price · 注入式换源)
--   index_price → 基差 = mark - index(补 M2-B 基差数据缺口)
--   next_funding_time → 修 futures/info 的 +8h 硬编码 bug(真实回源)
--   last_funding_rate / funding_interval_hours → M2-C.2.2 资金费结算用(interval 暂统一 8)
-- TTL 7 天:mark price 是「最新」语义,撮合/强平/基差只看近实时,无需长历史 · 磁盘稳态封顶
-- ⚠️ 与 apps/worker/ch_schema.py 的 DDL 必须保持一致(那边是 worker 启动幂等 ensure ·
--    update.sh 没有 ClickHouse 建表步骤 · 本文件只在容器首次启动/全新 CH 执行)
CREATE TABLE IF NOT EXISTS crypto_premium_index (
    symbol String,                          -- "BTCUSDT" Binance 风格(无斜杠)
    ts DateTime,                            -- 快照时间(回源 time 字段 · UTC)
    mark_price Float64,                     -- 标记价(撮合/强平价源)
    index_price Float64,                    -- 指数价(现货综合)· 基差 = mark - index
    last_funding_rate Float64,              -- 最近资金费率 · decimal 0.0001=0.01%
    next_funding_time DateTime,             -- 下次资金费结算时间(UTC · 回源真值)
    funding_interval_hours UInt8 DEFAULT 8, -- 资金费周期(小时)· M2-C.2.2 用 · 暂统一 8
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
TTL ingested_at + INTERVAL 7 DAY
SETTINGS index_granularity = 8192;

-- ============================================================================
-- 0023 阶段③ · A股/美股 市场首页(3.1 基建)· 大盘指数快照 + 交易日历
-- ============================================================================
-- ⚠️ 与 apps/worker/ch_schema.py 的 DDL 必须保持一致(那边 worker 启动幂等 ensure ·
--    update.sh 没有 ClickHouse 建表步骤 · 本文件只在容器首次启动/全新 CH 执行)。
--
-- market_index_snapshot · 大盘指数快照(cn/us 共表 · market 列区分)
--   cn:Sina stock_zh_index_spot_sina(上证/深成/创业板/沪深300)· symbol 'sh000001'
--   us:yfinance(道指/纳指/标普/罗素)· symbol '^DJI'
--   TTL 7 天:指数卡只看「最新」· 历史趋势走 kline 表 · 无需长留
CREATE TABLE IF NOT EXISTS market_index_snapshot (
    market String,                          -- 'cn' / 'us'
    symbol String,                          -- 'sh000001' / '^DJI'
    name String,                            -- '上证指数' / '标普500'
    ts DateTime,                            -- 快照时间(UTC)
    last_point Float64,                     -- 最新点位
    prev_close Float64,                     -- 昨收
    change_point Float64,                   -- 涨跌点
    change_pct Float64,                     -- 涨跌幅 %(已是百分数 · 可负)
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (market, symbol, ts)
TTL ingested_at + INTERVAL 7 DAY
SETTINGS index_granularity = 8192;

-- ADR 0035 阶段 A · 复用本表装全球指标概览(指数/商品/外汇/债券)· 幂等加列(非破坏):
--   category 分类(index/commodity/forex/bond/crypto)· unit 显示单位 · market 列存地区码
--   cn/us 市场首页旧行 category='' 默认值 · 旧读路径(WHERE market IN ('cn','us'))不受影响
ALTER TABLE market_index_snapshot ADD COLUMN IF NOT EXISTS category String DEFAULT '';
ALTER TABLE market_index_snapshot ADD COLUMN IF NOT EXISTS unit String DEFAULT 'point';

-- market_trade_calendar · 交易日历(目前仅 cn · AKShare tool_trade_date_hist_sina)
--   给市场状态机判「今天是不是交易日」· 美股用 market_calendar 硬编码节假日,不入此表
CREATE TABLE IF NOT EXISTS market_trade_calendar (
    market String,                          -- 'cn'(美股暂不入表)
    trade_date Date,                        -- 交易日
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (market, trade_date)
SETTINGS index_granularity = 8192;

-- ============================================================================
-- 0023 阶段③ · A股榜单 / 情绪 / 行业板块(3.2)· 数据源统一 Sina(东财 _em 不可达)
-- ============================================================================
-- ⚠️ 与 apps/worker/ch_schema.py 的 DDL 必须保持一致。
--
-- cn_spot_snapshot · 全市场个股快照(Sina stock_zh_a_spot ~5500 只)· 每次扫描同一 ts 写全量
--   榜单 = 最新 ts 的快照按 涨跌幅/成交额 排序;换手率/量比 Sina 无字段 → 不存、本期不做
--   TTL 2 天:榜单只看最新 · 个股历史走 kline 表
CREATE TABLE IF NOT EXISTS cn_spot_snapshot (
    symbol String,                          -- 纯代码(去 sh/sz/bj 前缀)· '600519'
    name String,
    ts DateTime,                            -- 快照时间(UTC · 一次扫描全量同值)
    last_price Float64,
    change_pct Float64,                     -- 涨跌幅 %(可负)
    change_amount Float64,
    amount Float64,                         -- 成交额(元)
    volume Float64,                         -- 成交量(股)
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toDate(ts)
ORDER BY (ts, symbol)
TTL ingested_at + INTERVAL 2 DAY
SETTINGS index_granularity = 8192;

-- cn_market_breadth · 情绪条单行(涨跌平家数精确 + 涨跌停估算 + 总成交额)
--   涨跌停按板块涨跌幅阈值估(东财涨跌停池不可达)· 口径见 services/cn_market.py
CREATE TABLE IF NOT EXISTS cn_market_breadth (
    ts DateTime,
    up_count UInt32,
    down_count UInt32,
    flat_count UInt32,
    limit_up_count UInt32,                   -- 估算
    limit_down_count UInt32,                 -- 估算
    total_amount Float64,                    -- 两市总成交额(元)
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY ts
TTL ingested_at + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;

-- cn_sector_snapshot · 行业板块快照(Sina stock_sector_spot · 新浪行业 ~49 板块)
CREATE TABLE IF NOT EXISTS cn_sector_snapshot (
    name String,                            -- 板块名
    ts DateTime,
    change_pct Float64,
    stock_count UInt32,                      -- 成分股家数
    total_amount Float64,                    -- 板块总成交额(元)
    leader_name String,                      -- 代表/领涨股
    leader_change_pct Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (ts, name)
TTL ingested_at + INTERVAL 2 DAY
SETTINGS index_granularity = 8192;

-- ============================================================================
-- 0023 阶段③ · 美股榜单 / 行业·中概板块(3.3)· 数据源 yfinance 批量(策展池 · 决策⑥)
-- ============================================================================
-- ⚠️ 与 apps/worker/ch_schema.py 的 DDL 必须保持一致。
--
-- us_spot_snapshot · 策展池个股快照(重点关注池 · 非全市场)· 每次扫描同一 ts 写全池
--   成交额 amount = 现价 × 成交量(美元估 · yfinance 无直接美元成交额)
CREATE TABLE IF NOT EXISTS us_spot_snapshot (
    symbol String,                          -- yfinance 代码 'AAPL'
    name String,                            -- 中文名
    sector String,                          -- 板块(11 GICS 行业 / 中概股)
    ts DateTime,                            -- 快照时间(UTC · 一次扫描全池同值)
    last_price Float64,
    change_pct Float64,                     -- 涨跌幅 %(可负)
    amount Float64,                         -- 成交额(美元估 = close × volume)
    volume Float64,                         -- 成交量(股)
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (ts, symbol)
TTL ingested_at + INTERVAL 2 DAY
SETTINGS index_granularity = 8192;

-- us_sector_snapshot · 板块聚合(行业 + 中概股)· change_pct = 成分等权均值
CREATE TABLE IF NOT EXISTS us_sector_snapshot (
    name String,                            -- 板块名(科技 / 金融 / 中概股 …)
    ts DateTime,
    change_pct Float64,                     -- 成分等权均值涨跌幅
    stock_count UInt32,
    total_amount Float64,                    -- 板块成交额(美元估)
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (ts, name)
TTL ingested_at + INTERVAL 2 DAY
SETTINGS index_granularity = 8192;

-- ============================================================================
-- 港股首页全市场 · 新浪 stock_hk_spot(~2764 只)· spot 快照 + 情绪条(★无涨跌停 · 无板块)
-- ⚠️ 与 apps/worker/ch_schema.py 的 DDL 必须保持一致。
-- ============================================================================
-- hk_spot_snapshot · 港股全市场个股快照(新浪 stock_hk_spot)· 每次扫描同一 ts 写全量
CREATE TABLE IF NOT EXISTS hk_spot_snapshot (
    symbol String,                          -- 5 位港股代码 '00700'
    name String,
    ts DateTime,
    last_price Float64,
    change_pct Float64,
    change_amount Float64,
    amount Float64,                         -- 成交额(港币元)
    volume Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toDate(ts)
ORDER BY (ts, symbol)
TTL ingested_at + INTERVAL 2 DAY
SETTINGS index_granularity = 8192;

-- hk_market_breadth · 港股情绪条单行 · ★港股无涨跌停制度 → 无 limit 列(对比 cn_market_breadth)
CREATE TABLE IF NOT EXISTS hk_market_breadth (
    ts DateTime,
    up_count UInt32,
    down_count UInt32,
    flat_count UInt32,
    total_amount Float64,                    -- 全市场总成交额(港币元)
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY ts
TTL ingested_at + INTERVAL 30 DAY
SETTINGS index_granularity = 8192;
