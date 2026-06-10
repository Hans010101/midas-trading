# ADR 0039 · K2b:kline 表重复数据治本(ClickHouse 去重迁移)

- 状态:**Draft(未拍板 · 未执行)** —— 纯方案,执行前 Hans 必须逐节审;执行本身 Hans 在场分小步走。
- 日期:2026-06-10(P2-prep 任务3 · 接力期间只读规划)
- 相关:docs/research/ch-kline-duplicate-diagnosis.md(根因诊断)· ADR 0038 技术债条目 · docs/decisions/0002(tz 坑)

## 背景与根因(已诊断,引用不重复)

`kline` 是普通 MergeTree(引擎层**零去重**),去重全靠 `insert_kline` 的 app 级「窗口查 existing ts → 过滤」,
该逻辑非原子(TOCTOU)且历史上对 tz 敏感;多写入路径(update_crypto_demo 每 5min / warm_popular_klines
每 30min / 手动 backfill)并发漏判 → 重复行写入后 MergeTree **永不合并去重** → 实测 BTC/USDT perp 1d
503 根 > 实际天数。读侧已兜住(vibe loader `duplicated(keep="last")`),但重复行持续堆积。

## 现状关键事实(代码层 · 实证)

1. 表定义只在 `docker/clickhouse-init.sql`:`ENGINE=MergeTree · PARTITION BY (market, toYear(ts)) · ORDER BY (symbol, period, ts)`。
2. ★ **排序键不含 `instrument`**:spot 与 perp 的 CH 符号同形(都是 `BTC/USDT`)→ 同 symbol/period/ts 的 spot 行与 perp 行排序键相同。普通 MergeTree 下无碍;**换 ReplacingMergeTree 后会互相吞行** → 新排序键**必须**含 instrument。
3. ★ **无版本列**(无 ingested_at):RMT 无版本列时按插入顺序保留,不确定性大 → 迁移需 `ADD COLUMN ingested_at DateTime DEFAULT now()`(或建新表直接带)。
4. 读侧共 5 处:`clickhouse_client.py` 4 处(insert 的 existing 窗口查 ×1 + select_kline ×2 + count ×1)+ vibe `midas_ch_loader.py` ×1。
5. ★ **磁盘账疑云(本次新发现)**:`scripts/backup_clickhouse.sh`(2026-05-29)摸底「default 库全部 MergeTree 表整库 ~**151 MiB**」,与交接口径「CH 32G」差两个数量级 → **32G 大头疑似不在业务表**(头号嫌疑:ClickHouse system 日志表 query_log/trace_log/metric_log 默认无限累积;次嫌疑:卷内其它)。**这决定 K2b 的真实优先级与磁盘风险,必须先实证(见 §待实证)。**

## 方案对比(等 Hans 拍)

| 方案 | 做法 | 治什么 | 风险/代价 |
|---|---|---|---|
| **甲 · RMT 重建(治本)** | 新表 `kline_v2`:`ReplacingMergeTree(ingested_at)` · `ORDER BY (symbol, instrument, period, ts)` · 分区不变 → 回填 → 切换 | 存量重复 + **未来重复**(引擎层幂等) | 核心表重建 · 需停写窗口 · 读侧需定 FINAL 策略 · 磁盘峰值 ≈ kline ×2(若 151MiB 量级则可忽略) |
| **乙 · 定期 DEDUPLICATE(治标)** | 保持 MergeTree,定期 `OPTIMIZE TABLE kline PARTITION <p> FINAL DEDUPLICATE BY symbol,market,instrument,period,ts`(beat 或 cron) | 仅存量重复(滚动清) | 不防新重复(TOCTOU 仍在,靠 app 去重)· 分区级重写 IO · **零结构变更零停写** |
| **丙 · 分两阶段** | 先乙清存量 + 观察新增率 → 数据多到值得时再甲 | 先止血后治本 | 两次工程 |

**顾问倾向(非拍板)**:先做 §待实证 的 4 条 SQL。若证实业务表确在百 MiB 量级 → 重复堆积的**绝对量很小**,
乙(每周一次 DEDUPLICATE)+ 现有读侧兜底已足够,甲可无限期延后;真正的磁盘问题(32G)另案治
(system 日志表加 TTL/降采样 —— 一条 `ALTER TABLE system.query_log MODIFY TTL` 级别的小动作,收益可能 >> K2b)。

## 甲方案完整迁移路径(若拍甲 · Hans 在场分小步)

1. **建新表**:`CREATE TABLE kline_v2 (...同列+ingested_at DateTime DEFAULT now()) ENGINE=ReplacingMergeTree(ingested_at) PARTITION BY (market, toYear(ts)) ORDER BY (symbol, instrument, period, ts)`。
2. **首轮回填**(在线 · 不停写):`INSERT INTO kline_v2 SELECT *, now() FROM kline` → `OPTIMIZE TABLE kline_v2 FINAL`(合并去重)。
3. **校验**:新旧表 `count()` / `uniqExact((symbol,market,instrument,period,ts))` 对账 —— 新表 count ≈ 旧表 uniq(差值=被去掉的重复)。每市场抽 1 symbol 对比首尾 ts + 任一日 OHLC 逐值相等。
4. **停写窗口**(低峰 04:00-05:00 · 估 ≤10min):`docker compose stop worker`(beat 全停 · 接受通知/预警同窗口暂停)→ **delta 补**:`INSERT INTO kline_v2 SELECT *, now() FROM kline WHERE ts > <首轮回填时的 max(ts) 水位>`(按市场取水位更稳)。
5. **原子切换**:`RENAME TABLE kline TO kline_old, kline_v2 TO kline`(秒级)→ `docker compose start worker`。
6. **读侧策略(三选,可后置)**:a) 什么都不做 —— RMT 后台合并最终去重 + 现有 app/loader 兜底仍在(推荐起步);b) 热查询加 `FINAL`(代价:查询放大);c) `select_kline` 加 `LIMIT 1 BY (symbol,instrument,period,ts)`(精准 · 改 2 处 SQL)。
7. **观察 ≥3 天**(图表/回测/bot 出图全正常)→ `DROP TABLE kline_old`。
- **回滚预案**:任何一步异常 → `RENAME TABLE kline TO kline_v2_bad, kline_old TO kline`(秒级回原)· 首轮回填/校验阶段失败直接 `DROP kline_v2` 重来,旧表全程未动。
- **写侧注意**:切换后 `insert_kline` 的 app 级去重**保留不删**(双保险 · RMT 合并是异步的,窗口内 count 类查询仍可能见重)。

## 待 Hans 在 Workbench 实证(整段复制 · 全只读)

```bash
docker exec midas-clickhouse sh -c 'clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --multiquery --query "
-- ① 业务表真实大小(151MiB vs 32G 之谜)
SELECT table, formatReadableSize(sum(bytes_on_disk)) AS size FROM system.parts WHERE active AND database='\''default'\'' GROUP BY table ORDER BY sum(bytes_on_disk) DESC;
-- ② system 日志表占用(32G 头号嫌疑)
SELECT database, table, formatReadableSize(sum(bytes_on_disk)) AS size FROM system.parts WHERE active AND database='\''system'\'' GROUP BY database, table ORDER BY sum(bytes_on_disk) DESC LIMIT 8;
-- ③ kline 重复总量(迁移收益)
SELECT count() AS rows, uniqExact((symbol,market,instrument,period,ts)) AS uniq_keys, rows - uniq_keys AS dup_rows FROM kline;
-- ④ perp 粒度分布(P2-period 同一刀实证)
SELECT period, count() AS rows, uniq(symbol) AS symbols, min(ts) AS earliest, max(ts) AS latest FROM kline WHERE market='\''crypto'\'' AND instrument='\''perp'\'' GROUP BY period ORDER BY period;
"'
```

## 后续

实证回来 → Hans 拍 甲/乙/丙(+32G 另案)→ 若动 CH,Hans 在场按 §迁移路径 分小步执行,每步有校验有回滚。
