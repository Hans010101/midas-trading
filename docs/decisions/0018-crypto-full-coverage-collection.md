# 0018 · 加密合约采集全量覆盖 + 三项配套(top100 → 全量解耦)

## 状态
Approved · 待实现(2026-05-23)
产品方已批准"全量采集 + 三项配套措施"方向。本 ADR 是实现方案,代码尚未写。

承接:0017(M2-A Crypto Pro 数据层)· [M2-数据打磨·任务2](采集 top30 → 动态 top100)。

---

## 1. 背景与问题

M2-数据打磨·任务2 把 OI / 多空比 / 资金费率的采集从硬编码 top30 改成
"按 24H 成交额动态取 top100"(`_top_perp_symbols(limit=100)`)。

**问题**:采集范围(top100 by 成交额)和展示需求耦合了。
- 看**跌幅榜**、按**资金费率/OI 变化**等其他维度排序时,需要的币可能不在
  "成交额 top100"里 → 列表 3 列、详情页合约维度图显示「—」。
- 本质:采集层用一个固定排序(成交额)截断,展示层却要任意排序/筛选,
  两者必须解耦。

**方向**:采集层**全量覆盖** Binance USDT 本位永续,展示层任意排序/筛选。

---

## 2. 决策

加密合约采集从"成交额 top100"扩展为**全量覆盖 Binance USDT 本位永续
(~527 个,`PERPETUAL` + `TRADING` + `quoteAsset=USDT`)**。
- 采集层:OI / 多空比 / 资金费率对全量 USDT 永续逐币采集。
- 展示层:批量接口 + 前端排序已与采集解耦(M2-数据打磨·任务3),数据全
  覆盖后任意榜单自然有数。
- ticker 已是单请求拉全市场(~623,含 USDC 等其它 quote),不变。

**全量口径选 USDT 本位 527**,不取全部 623(USDC 本位等流动性低、展示价值
小、徒增负载)。名单仍动态从 `crypto_ticker_24h` 取(过滤 `quote=USDT`),不
硬编码。

**前提:全量必须同时落地下面三项配套,否则不批准上线**(裸全量会超 expires /
触发 Binance 限流 / 磁盘无限涨)。

### 实测依据(2026-05-23)
- `fapi/v1/exchangeInfo`:全 symbol 741 · `PERPETUAL`+`TRADING` 567 · 其中
  USDT 本位 **527**;ticker 端点返回 ~623(含其它 quote)。
- CH 压缩后 bytes/行(实测 `system.parts`):OI 29.6 · 多空比 61 ·
  资金费率 51.5 · ticker 54.5。
- worker `--concurrency=4`(`apps/worker/Dockerfile:25`)· beat 频率见
  `celery_config.py`。
- 现状 TTL:**仅 `crypto_ticker_24h` 有 `TTL ingested_at + INTERVAL 30 DAY`**;
  `crypto_open_interest / crypto_long_short_ratio / crypto_funding_rate`
  **无 TTL → 无限累积**。
- 生产磁盘已用 **72.5%**(本地参考:docker 镜像 37GB + build cache 27GB =
  真正占盘大头,crypto 数据当前才 ~1MB)。

---

## 3. 三项必须的配套措施

### 配套 ① · 多空比 fetch limit 96 → ~4
**问题**:`long_short_scan` 每币每轮 `fetch_long_short_ratio(symbol, limit=96)`。
- 多空比是 5min 栅格,任务每 10min 跑一次 → 每轮其实只新增 ~2 个点,却拉 96 个。
- 全量(~527)单轮串行 96 点 × 3 端点 × 527 币,最坏耗时 ~560s **> expires 540s**
  → 轮次被丢弃,永远跑不完。
- 写放大:527 × 96 × 144 轮/天 ≈ **730 万 insert/天**,ReplacingMergeTree 去重后
  仅 ~15 万/天 → **~48× 写放大**,4 核 CH merge 压力大。

**改法**:`fetch_long_short_ratio(symbol, limit=4)`(覆盖 4×5min=20min > 10min 轮间隔,
保证有重叠 ts 供三上游交集合并)。
- 单轮请求数不变(仍 3 端点/币),但每端点返回 4 行而非 96 行 → 响应体积、
  insert 量、merge 压力降 ~24×;单轮耗时大幅下降,消除 expires 风险。
- 详情页要展示的历史窗口(288 点)由 ClickHouse 累积提供,不依赖单轮拉满。

> 注:OI 任务已是 `limit=1`(只补最新一根),无此问题;资金费率 `limit=1`,无此问题。
> 只有多空比是 `limit=96`。

### 配套 ② · 给 3 张合约表加 TTL 60 天
**问题**:OI / 多空比 / 资金费率三表无 TTL,全量后无限累积。

**改法**:加 `TTL ingested_at + INTERVAL 60 DAY`,对齐已有的 ticker 表(ticker 是
30 天;合约维度图要算 OI 24H/历史趋势,留 60 天更稳)。

- **`docker/clickhouse-init.sql` 同步**:在三张表 DDL 末尾加
  `TTL ingested_at + INTERVAL 60 DAY`(新部署的全新 CH 卷自动生效)。
- **生产已有 CH 卷 init.sql 不重跑** → 必须**一次性手工 ALTER**(同 instrument 列
  的处理方式):

  ```sql
  ALTER TABLE crypto_open_interest      MODIFY TTL ingested_at + INTERVAL 60 DAY;
  ALTER TABLE crypto_long_short_ratio   MODIFY TTL ingested_at + INTERVAL 60 DAY;
  ALTER TABLE crypto_funding_rate       MODIFY TTL ingested_at + INTERVAL 60 DAY;
  ```

  `MODIFY TTL` 立即生效于后续 merge;存量超期数据在下次 merge 时被清理(也可
  `OPTIMIZE TABLE ... FINAL` 主动触发,但全量表较大时谨慎,建议让后台 merge 自然清)。
- 这条 ALTER 由产品方/我在生产 CH 跑一次(非脚本,一次性 SQL),写进部署 runbook。

### 配套 ③ · 多空比降频 + 防限流
**问题**:worker `--concurrency=4`,OI(5min)/多空比(10min)/资金费率(15min)
可并行,全量后同一分钟叠加请求可能逼近 Binance fapi IP 限额 2400 weight/min;
`/futures/data/*`(OI hist / 多空比)有非公开的更严限速,裸全量有 429/418 风险。

**改法(二选一或叠加)**:
- **降频**:多空比 10min → **15min**(`crontab(minute="2-59/15")`),错峰编排保持
  与 OI/funding 分钟数不重叠。
- **限并发/限速**:在采集循环里加轻量节流——每 N 个 symbol `await asyncio.sleep(小)`,
  或用 `asyncio.Semaphore` 限制在途请求数(当前是纯串行,主要风险来自
  concurrency=4 的**多任务并行**叠加,而非单任务内并发)。
- 最低限度:确保 OI / 多空比 / 资金费率三个 task 的 beat 分钟数严格错峰
  (现状已错峰:OI `*/5`、多空比 `2-59/10`、funding `3-59/15`),全量后维持。

---

## 4. 改动文件清单

| 文件 | 改动 |
|---|---|
| `apps/worker/tasks/crypto_metrics_ingest.py` | ① `_top_perp_symbols()` 去掉 `LIMIT 100`、加 `quote=USDT` 过滤(取全量 ~527);② 多空比 task `fetch_long_short_ratio(limit=96→4)`;③(可选)采集循环加节流 |
| `apps/worker/config/celery_config.py` | 多空比 beat `2-59/10` → `2-59/15`(降频);维持错峰 |
| `docker/clickhouse-init.sql` | OI / 多空比 / 资金费率 三表 DDL 加 `TTL ingested_at + INTERVAL 60 DAY` |
| **生产一次性 ALTER**(非代码) | 上面配套②的 3 条 `ALTER TABLE ... MODIFY TTL`,生产 CH 手工跑一次,写进 runbook |
| `apps/api/...` | **无需改**——批量接口 `metrics-batch` + `_top_perp_symbols` 读 CH,数据多了自然全覆盖;前端展示层不动 |

> 红线确认:本方案**不含** `perp_kline_incremental` 采集任务(仍 A1 纯实时回源);
> 不接任何 trade endpoint。

---

## 5. 资源结论(4核8G 阿里云轻量 · 带配套后)

**磁盘(带 60 天 TTL,稳态封顶,不再无限涨)**:
- 唯一行/天/币:OI 288(5min)· 多空比 288 · 资金费率 ~3(8h)· ticker 144。
- 全量 ~527 日增(压缩):OI 4.5MB + 多空比 9.3MB + 资金费率 0.08MB + ticker 4.1MB
  ≈ **18 MB/天**。
- 60 天稳态:三张无 TTL→现加 TTL 的合约表 ≈ (4.5+9.3+0.08)×60 ≈ **0.83 GB**;
  ticker(30天 TTL)≈ 4.1×30 ≈ 0.12 GB。**合约维度总稳态 ≈ 1 GB 封顶**(留余量算 ~1.2GB)。
- 对比:不加 TTL 则 OI+多空比+资金费率 ≈ 5 GB/年无限增长。

**限流**:配套③后,多空比降到 15min + 错峰,单分钟峰值远低于 2400 weight/min;
多空比 limit 96→4 也大幅缩短单轮在途请求时长。

**CPU/merge**:配套①把多空比写放大砍 ~24× → CH merge 压力从"全量裸跑会吃紧"
降到可承受;worker 任务 I/O 等待型,CPU 低。

**结论**:带三项配套,全量在 4核8G **可承受**,磁盘稳态 ~1.2GB 封顶。

---

## 6. 运维前置:生产先跑 docker system prune

**为什么**:72.5% 磁盘的真正大头是 docker 镜像 + 构建缓存(本地参考:镜像 37GB +
build cache 27GB),不是数据。上全量前先回收,把磁盘降下来再说。

**怎么做**(生产 VPS 上,一次性):
```bash
# 1. 先看能回收多少(只读,不删)
docker system df

# 2. 清构建缓存(最大头 · 安全:只是缓存,下次 build 会重建)
docker builder prune -f

# 3. 清悬空(dangling)镜像 + 停止的容器 + 未用网络
#    注意:不要加 -a / --volumes(见下方风险)
docker system prune -f
```

**会删什么**:
- `builder prune -f`:删所有构建缓存层(下次 `docker compose build` 变慢但会重建,无数据风险)。
- `system prune -f`(不带 `-a`/`--volumes`):删**悬空镜像**(无 tag 的旧层)、
  **已停止的容器**、未被使用的网络。

**风险 / 红线**:
- **绝不加 `--volumes`** —— 那会删未被容器引用的卷,可能误删 ClickHouse / Postgres
  数据卷(若当时容器恰好停了)。**数据安全第一,本步严禁碰卷**。
- **绝不加 `-a`** 到 `docker image prune -a` 除非确认 —— `-a` 会删所有"当前没有
  容器在用"的镜像;若某服务恰好停着,它的镜像会被删,下次起要重新 pull/build。
  保守起见只用 `builder prune` + 不带 `-a` 的 `system prune`。
- 跑前确认 `docker compose ps` 五服务在跑(在用的镜像不会被 prune 误删)。

---

## 7. 实施分步顺序 + 验证 + 风险

> 全部在 `feature/m2-crypto-pro` 做,验收后逐文件挑 main(同既往)。

**Step 0 · 运维前置(生产)**:`docker builder prune -f` + `docker system prune -f`(不带
`-a`/`--volumes`)。**验证**:`df -h` 磁盘占用从 72.5% 明显下降;`docker compose ps`
五服务仍 healthy。

**Step 1 · 配套①+③(worker 改动)**:
- `_top_perp_symbols` 去 limit + 加 USDT 过滤;多空比 `limit=4`;celery_config 多空比降 15min。
- **验证**(本地全栈):重建 worker → 跑 `ticker_24h_scan`(perp_count ~623)→ 跑
  `open_interest_scan` / `long_short_scan` / `funding_rate_refresh`,看 ok/written ≈ 527、
  fail 低、单轮耗时 < expires;三表 distinct symbol ≈ 527。

**Step 2 · 配套②(TTL)**:
- `clickhouse-init.sql` 三表加 TTL 60d;**生产一次性 ALTER**(3 条 MODIFY TTL)。
- **验证**:本地 `ALTER` 后 `SHOW CREATE TABLE` 含 TTL;插旧 `ingested_at` 测试行,
  `OPTIMIZE FINAL` 后被清(本地小表可验);确认现货/A股/美股 kline 等其它表不受影响。

**Step 3 · 真机自查 + 验收**:
- /crypto-market 跌幅榜、按资金费率/成交额排序都不再出现成片「—」(全量覆盖后)。
- 详情页随机几个冷门币,合约维度图 ①②③⑤ 有数据(在采集范围内)。
- worker 日志:多空比单轮耗时、无 429/418、无 expires 丢弃。

**风险点**:
1. **多空比单轮超时**:不先做配套① 就全量 → expires 丢弃。故配套①必须先行。
2. **Binance 限流 429/418**:concurrency=4 全量叠加;配套③(降频+错峰)缓解,
   上线后盯日志,必要时进一步加 semaphore 限速。
3. **TTL 生产 ALTER 是 schema 改动**:`MODIFY TTL` 安全(不重写存量、后台 merge 清理),
   但属碰生产 schema,需走 runbook、跑前备份/确认。
4. **冷门币数据质量**:新上市/低流动性永续 OI/多空比可能稀疏或 0、缺 24h 历史 →
   OI 24H 变化噪声大/null。沿用现有"如实空态/—",不造假(CLAUDE.md 红线)。
5. **docker prune 误删卷**:见 §6 红线,绝不带 `--volumes`/`-a`。

---

## 8. 红线复述
- 全程虚拟资金,worker 只 GET + INSERT,永不调 trade endpoint。
- 接不上/采不到的币如实空态,绝不硬编造假数据。
- 不接 `perp_kline_incremental`(A1 纯实时回源不变)。
