# CH kline 重复 perp 日线 · 只读诊断报告(P1-4c 块4a · 2026-06-05)

> 背景:P1-3 实测 `MidasCHLoader` 查 BTC/USDT perp 1d 得 **503 根 > 实际天数**,引擎 `_align`
> reindex 报 `cannot reindex on an axis with duplicate labels`,故加了读侧去重补丁
> `frame[~frame.index.duplicated(keep="last")]`。本报告**只读代码定位根因**,不改采集逻辑。

## 结论(代码层定性)

**根因 = `kline` 表是普通 `MergeTree`(引擎层零去重)+ 去重全靠 `insert_kline` 的 app 级
「查 existing ts 再跳过」,而该 app 去重非原子(TOCTOU)且对 tz 敏感;多个写入路径反复写
同一 perp 日线序列 → 偶发漏判 → 重复行一旦写入,MergeTree 永不合并去重 → 月积月累 503 > 天数。**

★ 注意:**这不是 ReplacingMergeTree「未合并/没加 FINAL」问题** —— `crypto_premium_index` 等
是 ReplacingMergeTree,但 **`kline` 本身是 MergeTree**,根本没有引擎级去重可言。

## 证据(文件:行)

1. **kline 引擎 = MergeTree(不去重)** — `docker/clickhouse-init.sql:5-19`
   ```sql
   CREATE TABLE IF NOT EXISTS kline (
       symbol String, market Enum8(...), period Enum8(...), ts DateTime,
       open/high/low/close/volume/amount Float64
   ) ENGINE = MergeTree
   PARTITION BY (market, toYear(ts))
   ORDER BY (symbol, period, ts);              -- ★ 排序键不含 instrument
   ```
   `instrument` 是后来 ALTER 加的(`clickhouse-init.sql:40-41`):
   `ALTER TABLE kline ADD COLUMN IF NOT EXISTS instrument Enum8('spot'=1,'perp'=2) DEFAULT 'spot'`
   → 引擎仍是 MergeTree(ALTER ADD COLUMN 不改引擎),**排序键 `(symbol, period, ts)` 仍不含 instrument**。

2. **去重只在 app 层 · 非原子** — `apps/api/app/services/clickhouse_client.py` `insert_kline`(:101-187)
   - 注释自陈:「写入前先查已存在的 ts 集合,过滤掉重复行(**MergeTree 不自动去重**)」(:7)
   - 逻辑:`SELECT ts ... WHERE symbol/market/instrument/period AND ts BETWEEN min AND max`(:125)
     → 算 `existing_ts` 集合 → `new_rows = [r for r in rows if to_aware_utc(r.ts) not in existing_ts]`(:144)
   - **TOCTOU**:查 existing 与 INSERT 之间无锁/无事务;两条写入路径并发时都可能「查到不存在 → 都插入」→ 重复。
   - **tz 敏感**:`existing_ts` 是 CH 读回的 naive datetime 补 UTC(:139-141)与 `to_aware_utc(r.ts)` 比较;
     源 ts 与存储 ts 若有 tz/精度差(docs/decisions/0002 同族坑)→ 比较不等 → 漏判 → 重插。

3. **多写入路径反复写同序列**(每条都调 insert_kline,各自独立去重判定):
   - `apps/worker/tasks/incremental.py` `update_crypto_demo` —— **每 5 分钟** 拉 BTCUSDT perp 1d 最近 10 根
   - `incremental.warm_popular_klines` —— 每 30 分钟 拉 5 个 crypto perp(含 BTC)perp 1d 200 根
   - `apps/worker/tasks/data_ingest.py` `_backfill_one` —— 按需回填
   - `apps/api/app/api/v1/chart.py` `_fetch_on_miss` + `market.py` —— 端点 cache-miss 即拉即插
   → 高频(5min)× 多路径 × 数月 · 任一次 app 去重漏判产生的重复行,MergeTree **永久保留**。

4. **读侧也不去重** — `select_kline`(clickhouse_client.py:189)用 `ORDER BY ts DESC LIMIT N`,
   **无 `FINAL`、无 `GROUP BY`/`LIMIT 1 BY`**(:228);`MidasCHLoader.fetch` 的 SELECT 同样无去重
   → 重复行原样返回 → 才需要那个读侧 `duplicated(keep="last")` 补丁兜底。

## 待 Hans 在生产 CH 跑的确认查询(定位「是哪种漏判 + 多少重复」)

```sql
-- 1) 确认引擎 + 排序键(代码说 MergeTree,但生产可能被改过,以真机为准)
SHOW CREATE TABLE kline;

-- 2) 重复总量:count 与去重 ts 数差多少
SELECT count() AS rows, uniqExact(ts) AS distinct_ts
FROM kline
WHERE symbol='BTC/USDT' AND market='crypto' AND instrument='perp' AND period='1d';

-- 3) 哪些 ts 重复 + 每个重复几次 + 几个不同 ingested_at(多 ingested_at = 多次插入)
SELECT ts, count() AS c, uniqExact(ingested_at) AS ingests
FROM kline
WHERE symbol='BTC/USDT' AND market='crypto' AND instrument='perp' AND period='1d'
GROUP BY ts HAVING c > 1 ORDER BY ts;

-- 4) 取一个重复 ts 看 ohlcv 是否一致(一致=纯重复;不同=重抓写了新版)
SELECT ts, open, close, volume, ingested_at
FROM kline
WHERE symbol='BTC/USDT' AND market='crypto' AND instrument='perp' AND period='1d'
  AND ts = '<上一步某个重复 ts>'
ORDER BY ingested_at;
```
- 若 (4) 同一 ts 的多行 **ohlcv 相同** → 纯重复(TOCTOU/tz 漏判)。
- 若 **ohlcv 不同** → 重抓把「同日不同时刻的快照」当新行写了(去重按 ts 跳过本应拦住,说明 tz/比较漏判)。

## 修复选项(★ 等 Hans 定,本步不改)

| 方案 | 做法 | 代价 | 评价 |
|---|---|---|---|
| A 读侧兜底(已做) | `MidasCHLoader` 的 `duplicated(keep="last")`;`select_kline` 可加 `LIMIT 1 BY (symbol,market,instrument,period,ts)` 或 `argMax(...,ingested_at)` | 低 | 治标 · 重复行仍在表里堆积 |
| **B 引擎改 ReplacingMergeTree(治本)** | 重建 kline 为 `ReplacingMergeTree(ingested_at)` · `ORDER BY (symbol, market, instrument, period, ts)`(★ 含 instrument)· 读侧 `FINAL`/`argMax` | 中-高(建表 + 数据迁移 + 改读法) | 引擎层永久去重 + 留最新 · 长期正解 |
| C 清存量重复 | `INSERT INTO kline_dedup SELECT argMax(...) ... GROUP BY 全键` 后换表 | 中 | 一次性清,需配合 A/B 防再生 |
| D 硬化 app 去重 | insert_kline 按 symbol 串行化 / 周期 `OPTIMIZE`(MergeTree 无效)/ 改用 INSERT 幂等模式 | 中 | MergeTree 下 OPTIMIZE 不去重 → 仍需 B |

**建议**:长期走 **B(ReplacingMergeTree + 排序键含 instrument + 读侧 FINAL)** 一次性治本;过渡期 A 已兜底。

## 声明 vs 实测
1. **引擎/排序键来自代码(init.sql),非生产实查**:生产 kline 可能被手动改过 → 以 `SHOW CREATE TABLE kline` 真机为准(查询1)。我**没连生产 CH**(Hans 外出 + 只读排查约定)。
2. **「TOCTOU vs tz 漏判」哪种为主未实测**:需查询 (3)(4) 看 ingested_at 个数 + ohlcv 是否一致才能定。两者都可能,且都被 MergeTree 永久放大。
3. **不改采集**:本报告只定位 + 给方案;改采集/改表引擎须 Hans 拍板(涉及表重建,不可逆设计)。
