# 0017 · M2-A · Crypto Pro 数据层设计

## 状态
Draft (2026-05-21 · feature/m2-crypto-pro 分支)

## 上下文

M1 部署完毕,产品负责人决定把 CryptoSharp 的加密行情体系整套迁进点金「加密」模块,
作为 M2 · Crypto Pro 里程碑。M2-A 是数据层(M2-B 后端 REST + 缠论联动,
M2-C 虚拟合约交易,M2-D 前端 UI,M2-E E2E)。

**红线复述(再次确认):**
- 点金永不接真实交易通道
- CryptoSharp 也是虚拟账户 · 它的合约 / 多空比 / 资金费率 / 做多做空 / 一键下单
  **可以迁移**
- 唯一硬约束:**所有交易动作必须接点金虚拟撮合引擎,用虚拟资金**

## 决策

### 1. 数据维度 · 9 个新数据流

| 类别 | 数据流 | 上游 | 频率 |
|---|---|---|---|
| **现货** | 24h ticker(全币种价/涨跌/量) | Binance Spot REST `/api/v3/ticker/24hr` | 1 min |
| **合约** | Perpetual K 线(15m/1h/4h/1d) | Binance Futures REST `/fapi/v1/klines` | 跟周期 |
| **合约** | Funding rate 时间序列 | Binance Futures REST `/fapi/v1/fundingRate` | 8h 结算 |
| **合约** | Open Interest 时间序列 | Binance Futures REST `/futures/data/openInterestHist` | 5 min |
| **合约** | Top trader long/short ratio(账户) | Binance Futures `/futures/data/topLongShortAccountRatio` | 5 min |
| **合约** | Top trader long/short ratio(持仓) | Binance Futures `/futures/data/topLongShortPositionRatio` | 5 min |
| **合约** | Taker buy/sell volume | Binance Futures `/futures/data/takerlongshortRatio` | 5 min |
| **市场** | Fear & Greed Index | alternative.me `/fng/?limit=N` | 1 day |
| **市场** | 全市场总市值 / BTC dominance / 24h vol | CoinGecko `/global` | 5 min |

(可选 M2-A v2 加: liquidation 24h、long/short ratio 历史栅格化、衍生品总盘子等)

### 2. ClickHouse Schema · 5 新表

#### 2.1 `crypto_funding_rate`

```sql
CREATE TABLE IF NOT EXISTS crypto_funding_rate (
    symbol String,                          -- e.g. "BTCUSDT" (Binance Futures 风格 · 无斜杠)
    ts DateTime,                            -- 资金费率结算时间(UTC · 通常 8h 整点)
    rate Float64,                           -- 资金费率(decimal · 0.0001 = 0.01%)
    mark_price Float64,                     -- 结算时标记价
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts);
```

#### 2.2 `crypto_open_interest`

```sql
CREATE TABLE IF NOT EXISTS crypto_open_interest (
    symbol String,
    ts DateTime,                            -- 采样时间(UTC · 5min 栅格)
    oi_coin Float64,                        -- OI 折算到币(BTC 计价)
    oi_usd Float64,                         -- OI 折算到美元
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts);
```

#### 2.3 `crypto_long_short_ratio`

```sql
CREATE TABLE IF NOT EXISTS crypto_long_short_ratio (
    symbol String,
    ts DateTime,                            -- 5min 栅格
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
ORDER BY (symbol, ts);
```

#### 2.4 `crypto_ticker_24h`

```sql
CREATE TABLE IF NOT EXISTS crypto_ticker_24h (
    symbol String,                          -- "BTC/USDT"(ccxt 风格,跟点金 spot 一致)
    instrument Enum8('spot'=1, 'perp'=2),   -- 现货 or 合约
    ts DateTime,                            -- 采样时间
    last_price Float64,
    change_pct_24h Float64,                 -- 24h 涨跌幅(% · 已乘 100)
    high_24h Float64,
    low_24h Float64,
    volume_24h Float64,                     -- base 币种成交量
    quote_volume_24h Float64,               -- 报价币(USDT)成交额
    count_24h UInt64,                       -- 24h 笔数(可选 · spot 才有)
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (instrument, symbol, ts);
```

#### 2.5 `crypto_market_overview`

```sql
CREATE TABLE IF NOT EXISTS crypto_market_overview (
    ts DateTime,                            -- 采样时间
    -- CoinGecko /global
    total_market_cap_usd Float64,
    total_volume_24h_usd Float64,
    btc_dominance Float64,                  -- 0..100
    eth_dominance Float64,
    -- alternative.me Fear & Greed
    fear_greed_value UInt8,                 -- 0..100
    fear_greed_classification String,       -- "Extreme Fear" / "Fear" / "Neutral" / "Greed" / "Extreme Greed"
    -- 衍生品总盘子(CoinGecko derivatives)
    derivatives_oi_usd Float64,
    derivatives_volume_24h_usd Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY ts;
```

### 3. 现有 `kline` 表 · 加 instrument_type · 不另起新表

合约 K 线**复用现有 `kline` 表** · 用新增列 `instrument` 区分 spot/perp。
理由:
- 缠论引擎读 kline · 不需要改任何代码就支持合约
- 工作台 K 线渲染逻辑不需要分叉
- ClickHouse 列裁剪 + 分区按 (market, year) 仍高效

**改造方式:**

```sql
ALTER TABLE kline ADD COLUMN instrument Enum8('spot'=1, 'perp'=2) DEFAULT 'spot' AFTER market;
-- 后续 INSERT 现货时 instrument='spot'(默认值,无需改 worker)
-- 合约 INSERT 时 instrument='perp'
```

老数据自动是 'spot' · 兼容性零问题。

`ORDER BY` 不动(仍是 symbol, period, ts)· 查询时 WHERE 加上 `instrument = 'spot'` 即可。
高频查询可加 SKIP INDEX,M2-A 不动 · M2-E 看实际查询模式再决定。

### 4. 数据源适配器架构

继承现有 `BaseDataSource` 模式 · 三个新模块:

```
apps/api/app/services/data_sources/
  binance_futures_source.py      # 合约 K 线 + funding + OI + long/short
  coingecko_source.py             # 全市场 overview
  alternative_me_source.py        # Fear & Greed Index
```

**接口契约(新增到 BaseDataSource 体系):**

| 方法 | 输入 | 输出 | 已有 / 新增 |
|---|---|---|---|
| `fetch_kline(symbol, period, limit)` | spot/perp | List[Kline] | 已有(spot)· 新增 perp |
| `fetch_funding_rate(symbol, start_ts, end_ts)` | "BTCUSDT" | List[FundingRate] | **新增** |
| `fetch_open_interest(symbol, period='5m')` | | List[OpenInterest] | **新增** |
| `fetch_long_short_ratio(symbol, period='5m')` | | List[LongShortRatio] | **新增** |
| `fetch_ticker_24h(symbols=None)` | None=全部 | List[Ticker24h] | **新增** |
| `fetch_global_overview()` | | MarketOverview | **新增**(CoinGecko)|
| `fetch_fear_greed(limit=30)` | | List[FearGreed] | **新增**(alternative.me) |

**地域选型:** Binance Futures API 全球可用 · 香港 VPS 直连无障碍。
CoinGecko + alternative.me 同样 · 无需代理。

### 5. Celery 任务节奏

| Task | 频率 | 拉取范围 | 写入 |
|---|---|---|---|
| `crypto.ticker_24h_scan` | 1 min | 全 Binance perp + spot(~600 symbols) | `crypto_ticker_24h` |
| `crypto.funding_rate_refresh` | 8 h(整点) | 全 perp · 各 1 条最新 | `crypto_funding_rate` |
| `crypto.open_interest_scan` | 5 min | top 30 perp · 各 1 条最新 | `crypto_open_interest` |
| `crypto.long_short_scan` | 5 min | top 30 perp · 各 1 条最新 | `crypto_long_short_ratio` |
| `crypto.global_overview_refresh` | 5 min | CoinGecko /global | `crypto_market_overview` |
| `crypto.fear_greed_refresh` | 1 day(UTC 00:30) | alternative.me 最近 30 天 | `crypto_market_overview`(只更新 FGI 列) |
| `crypto.perp_kline_incremental` | 跟周期(15m/1h/4h/1d) | top 30 perp × 4 周期 · 各 1 根最新 | `kline`(instrument='perp')|

**容量估算(top 30 symbols · 1 个月):**
- ticker_24h_scan:600 symbols × 1440/day × 30 day = **26M 行/月** · ~2 GB
- funding_rate:30 symbols × 3 entries/day × 30 day = **2700 行/月** · 忽略不计
- open_interest:30 symbols × 288/day × 30 day = **260K 行/月** · ~20 MB
- long_short:30 symbols × 288/day × 30 day = **260K 行/月** · ~25 MB
- overview:1 × 288/day × 30 day = **8.6K 行/月** · 忽略
- kline perp:30 × 4 周期 × 高频根 · 已在 kline 表 · 现有容量规划覆盖

**最大头是 ticker_24h_scan · 26M 行/月。** 配 TTL 30 天保留(超出走冷归档,M2-E 再做)。

```sql
ALTER TABLE crypto_ticker_24h MODIFY TTL ingested_at + INTERVAL 30 DAY;
```

当前 ClickHouse 限额 2GB · 完全 hold 得住 6-12 个月。

### 6. REST 端点 · `/api/v1/crypto/`

| Method | Path | 用途 |
|---|---|---|
| GET | `/api/v1/crypto/overview` | 全市场快照 · FGI + 总市值 + BTC dominance |
| GET | `/api/v1/crypto/tickers/24h?market=spot|perp&top=20` | 涨幅榜 / 跌幅榜 / 量榜 |
| GET | `/api/v1/crypto/futures/{symbol}/funding-rate?limit=N` | funding rate 时间序列 |
| GET | `/api/v1/crypto/futures/{symbol}/open-interest?limit=N` | OI 时间序列 |
| GET | `/api/v1/crypto/futures/{symbol}/long-short-ratio?limit=N` | 多空比 + taker 比 |
| GET | `/api/v1/crypto/futures/{symbol}/info` | 标的元数据(下次资金费率倒计时 / 标记价 / 最大杠杆) |
| GET | `/api/v1/crypto/fear-greed?limit=30` | FGI 时间序列(给图表用) |

`/api/v1/market/kline` 已有的端点 · M2-B 加 `?instrument=spot|perp` 参数支持合约。
本 ADR 不动 market.py · M2-B 处理。

### 7. 虚拟账户架构 · 加密总账户 + 现货/合约子账户

**产品负责人定调:** 加密总账户下分现货 + 合约两个子账户。

```
                user
                  │
       ┌──────────┼──────────┐
       │          │          │
 cn_account   us_account   crypto_account     ← 现状 + 新增 crypto 总账户
                              │
                  ┌───────────┴───────────┐
                  │                       │
          crypto_spot_account     crypto_futures_account
          (旧 crypto_account     (M2-C 新增)
           升级 · 不动 schema)
```

**M2-A 范围(本里程碑)只动 schema 准备 · 不实装 futures 撮合:**

- 现有 `VirtualAccount` 表(market='crypto')· **改名重定位为 `crypto_spot_account`**
- 新增 `crypto_futures_account` 表(M2-A 只建 schema · 撮合逻辑 M2-C)
- 新增 `crypto_futures_position` 表(同上)
- 新增 `crypto_futures_order` 表(同上)
- 新增 `crypto_funding_settlement` 表(资金费率结算流水 · M2-C 实装)

**为什么 spot / futures 用独立子账户:**

| 维度 | spot | futures |
|---|---|---|
| 风险模型 | 现金交易 · 无杠杆 | 杠杆 + 保证金 · 强平风险 |
| PnL 计算 | (sell - cost) × qty · 简单 | (mark - entry) × qty × direction + funding accrual |
| 持仓概念 | qty ≥ 0(只 long) | direction ∈ {long, short} · qty 可双向 |
| 资金 | USDT 余额 | USDT 保证金(初始 + 维持) |

强行合并会让 0008 设计崩塌 · 行业惯例也是分账户(Binance/OKX 都这么分)。

### 8. 配置 + 环境变量

新增 `.env` 项(都有默认值 · 不破现有配置):

```bash
# === Crypto Pro 数据源(M2-A 起接)===
BINANCE_FUTURES_API_URL=https://fapi.binance.com
COINGECKO_API_URL=https://api.coingecko.com/api/v3
COINGECKO_API_KEY=                              # 可选 · 免费档不需要 · 高频建议 demo plan
ALTERNATIVE_ME_API_URL=https://api.alternative.me

# 上游限流避让(默认即可 · 极端时调)
BINANCE_FUTURES_RATE_LIMIT_RPM=2400             # Binance Futures 上限 6000/min · 留余量
COINGECKO_RATE_LIMIT_RPM=30                      # 免费档 30/min
```

### 9. 接缝处的「翻车防御」清单(吸取 0002 / 0010 教训)

- **时区:** Binance Futures REST 返 Unix ms · 必须 tz-aware UTC 写 ClickHouse
- **funding rate 符号:** Binance 用 decimal(0.0001 = 0.01%)· 不要乘 100 存
- **OI 单位:** Binance 同时返 sumOpenInterest(币计)+ sumOpenInterestValue(USDT 计)· 都存
- **long/short ratio:** Binance period=5m/15m/30m/1h/2h/4h/6h/12h/1d · M2-A 固定取 5m
- **ticker 24h symbol 格式:** Binance API 用 `BTCUSDT`(无斜杠)· 写 CH 时统一转 `BTC/USDT`(ccxt 风格)· 跟现有 spot 表对齐
- **CoinGecko `/global` 返一个大对象 · 不是数组** · 解析路径:`data.total_market_cap.usd` / `data.market_cap_percentage.btc`
- **alternative.me 返 list[{value, classification, timestamp}] · timestamp 是 string 不是 int**
- **clickhouse-connect 写 tz-aware → 写 naive UTC**(继承 0002 教训)
- **ORDER BY LIMIT N · 凡是「最新」语义都 DESC LIMIT N + Python reverse**(继承 0010 教训)

### 10. M2-A 任务拆分(checkpoint 内的 sub-task)

| Sub | 范围 | 估时 |
|---|---|---|
| M2-A-1 | ADR 0017 + 技术方案 doc | ✓ done in this commit |
| M2-A-2 | ClickHouse schema 5 表 + kline ALTER COLUMN | 0.5 d |
| M2-A-3 | Pydantic schemas/crypto.py | 0.5 d |
| M2-A-4 | binance_futures_source.py adapter | 2 d |
| M2-A-5 | coingecko_source.py adapter | 0.5 d |
| M2-A-6 | alternative_me_source.py adapter | 0.5 d |
| M2-A-7 | clickhouse/crypto_metrics.py(写入 helper) | 1 d |
| M2-A-8 | REST 路由 /api/v1/crypto.py | 1.5 d |
| M2-A-9 | Celery tasks + beat schedule | 1.5 d |
| M2-A-10 | 虚拟合约账户 models + alembic migration(只建表 · 不撮合) | 1 d |
| M2-A-11 | pytest skeleton(adapter 单测 + 路由 mock) | 1 d |
| M2-A-12 | branch README · WIP 边界 + 接 M2-B 准备 | 0.5 d |
| **小计** | | **~10.5 d**(单人全职 · 兼职更慢) |

跟之前评估的 2-3 周一致。

### 11. 跟 M2-B / M2-C / M2-D 的接口

- **M2-B(后端 REST + 缠论联动)**:M2-A 已留好 instrument 列 · M2-B 只需在 `/api/v1/market/kline` 加 `?instrument` 参数 + 缠论引擎读 perp K 线即可
- **M2-C(虚拟合约交易)**:M2-A 已建好 4 张 futures 表 schema · M2-C 实装撮合 + 资金费率结算 + 强平
- **M2-D(前端 Crypto Pro UI)**:M2-A 提供的 REST 端点直接消费(overview / tickers / funding / OI / long-short / fgi)

## 已知边界(M2-A 不做 · 留 M2-B/C/E)

- 合约 K 线写入 worker · M2-A 只写 adapter 接口 + Celery task 骨架 · 真实 backfill 跑通在 M2-A 联调时
- Symbol 全集发现(perp 上 300+ 个)· M2-A 固定 hard-code top 30 · M2-B 再做 watchlist 联动
- 缠论联动 perp K 线 · 留 M2-B
- 虚拟合约撮合 / 强平 / 资金费率结算 · 留 M2-C
- 前端 UI 全部 · 留 M2-D

## 撤销路径

- M2-A 全部改动在独立分支 feature/m2-crypto-pro · main 不动
- ClickHouse 新表都是 ReplacingMergeTree · 删表不影响其他业务
- kline ALTER COLUMN instrument 是新增列 · 默认值 spot · 删列也兼容
- 虚拟合约 4 表(M2-A 只建空表)删表无业务损伤
- 任何 commit 都可单独 revert · 不会破坏跟 main 的合并能力

## 备注

- M2-A 的代码骨架在 feature/m2-crypto-pro 分支 · 不合并到 main · 等 M2-A 整个测过再考虑 PR
- 跑不通的部分 ADR 里明确标 「WIP · M2-A 联调时验证」
- 红线确认:本 ADR 所有数据接口只 GET · 一切交易动作走点金虚拟撮合 · 永不接 Binance trade endpoint
