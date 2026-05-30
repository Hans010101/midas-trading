# ADR 0034a · 港股阶段一 实施细案 · 数据层(CH 迁移 + hk_source + 采集)

- 状态:**Accepted**(2026-05-30 审过 · 4 决策点已拍板,见文末)· 前置(P0 延迟补测 + midas_test 迁移演练)过了才真在生产改库
- 关联:ADR 0034(港股接入 · 已 Accepted)+ `scripts/hk-phase0/`(阶段零探测)+ `scripts/hk-phase1/`(P1-1 迁移脚本)
- 范围:**只数据层** —— CH `market` Enum8 迁移 + `hk_source` 适配器 + kline 采集打通 + 每手股数策展配置壳。
  **不碰**:行情前端 / 自选 / 持仓(阶段二)· 下单 / 每手取整逻辑(阶段三)。

## 阶段零实测结论(已确认 · 本细案的前提)
- 零-A CH Enum8 迁移:✅ 加 `hk=4` 纯加值、metadata-only、轻量(数据量小:kline **1.6 万行** / symbol_meta **4 行**)。
- 零-B 历史 K 线 + 复权:✅ `ak.stock_hk_hist("00700")` 成功(5408 行 + 前复权生效),免费源够用。
- 零-C 每手股数:走**手动策展兜底**(热门池配死每手数,不依赖免费源动态取)。
- 实时延迟:⏳ 周末测不准(yfinance 1461min 不可信 + akshare 实时接口被掐)→ **★ 阶段一前必须工作日港股时段补测**。

---

## 0. 阶段一【写代码前】的两个前置(必须先过)
- **P0-补测 · 工作日实时延迟**:港股交易时段(09:30–16:00 HKT)重跑 `scripts/hk-phase0/probe_hk_data.py`,
  确认 akshare 实时延迟 **≤ 15min**(决策③可接受线)。不过 → 回产品负责人(换源 / 调预期)。
- **P0-演练 · CH 迁移 midas_test**:在 midas_test 库走 up→插 hk 测试行→down→up 验可逆(见 §1.3)。
两个都过,才进 P1 写生产代码。

---

## 1. ★ CH `market` Enum8 迁移(中风险 · 改已上线存储)

### 1.1 迁移语句(纯加值 · cn/us/crypto 映射不变)
```sql
ALTER TABLE kline       MODIFY COLUMN market Enum8('cn'=1,'us'=2,'crypto'=3,'hk'=4);
ALTER TABLE symbol_meta MODIFY COLUMN market Enum8('cn'=1,'us'=2,'crypto'=3,'hk'=4);
```
零-A 已探测确认 metadata-only;且数据量小,即使非 metadata-only 也秒级。

### 1.2 ★ 迁移机制(关键 · 与 deploy 解耦)
- **`clickhouse-init.sql` 只在容器【首次 init】(空数据目录)跑**(挂在 `/docker-entrypoint-initdb.d/` ·
  docker-compose.yaml:47)→ **对已存在的生产 CH 不会重跑**。现有 `instrument` 列 ALTER(init.sql:40
  `ADD COLUMN IF NOT EXISTS`)就是这个先例:新环境靠 init.sql,**老库靠手动 ALTER**。CH **没有 alembic 式自动迁移**。
- 所以本次迁移是 **Hans 手动跑 clickhouse-client ALTER 的【带外 ops 步骤】,不进 deploy pipeline**。
  → 干净分离:**先手动迁移(Hans)→ 再正常 deploy 代码(hk_source / init.sql 同步)**。
- ⚠ 顺序硬约束:**ALTER 必须先于 hk 采集代码上线**(否则插 `market='hk'` 被 CH 拒)。

### 1.3 上生产前 · midas_test 演练(可逆证明)
```
up:   ALTER … 'hk'=4(两表)
test: INSERT 一条 market='hk' 测试 kline 行 → SELECT 查出来确认
down: DELETE 测试行 → ALTER … 回 Enum8('cn'=1,'us'=2,'crypto'=3)
up:   再 ALTER … 'hk'=4 → 确认可逆 + 幂等
```
(★ 仅 midas_test 插测试行;生产迁移**不插任何测试数据**。)

### 1.4 生产执行流程(决策⑤:低峰 + 停 worker)
1. 低峰窗口(A 股 / 美股 / 港股都收盘,如 UTC 深夜)。
2. `docker compose stop worker`(停采集 · 防迁移期写入)。
3. 跑迁移脚本(P1-1 产出:像 `probe_ch_enum8.sh` 但**执行** ALTER · 带 SHOW CREATE 前后对比 + 幂等)。
4. 验证:`SHOW CREATE TABLE kline/symbol_meta` 确认 Enum8 含 hk。
5. `docker compose start worker` 恢复。
6. 盯 worker 日志正常 + 现有 cn/us/crypto 采集不受影响。

### 1.5 回滚预案
- **无 hk 数据**(迁移后还没采港股)→ `ALTER … MODIFY COLUMN market Enum8('cn'=1,'us'=2,'crypto'=3)`(两表)。
- **已有 hk 数据** → 先 `ALTER TABLE kline DROP PARTITION <hk 分区>` 再 MODIFY 回。
- 迁移脚本写成**幂等**(重复跑不报错;ALTER 到同一 Enum8 是 no-op)。

### 1.6 init.sql 同步
`clickhouse-init.sql` 的 kline + symbol_meta 的 Enum8 改成含 hk(**给将来新环境干净建库**);
**线上靠 §1.4 手动 ALTER,不重建**。这条改动随 P1-2/3 的代码一起 commit。

---

## 2. `hk_source` 数据源适配器
### 2.1 文件 + 类(对齐 cn_source)
- 新建 `app/services/data_sources/hk_source.py` · `class HkSource(BaseDataSource)` · `name="akshare-hk"` · `market="hk"`。
### 2.2 历史 K 线(akshare · 已实测)
- `fetch_kline(symbol, period, limit)` → `ak.stock_hk_hist(symbol=<5位代码>, period=<映射>, adjust="qfq")`(前复权 · 零-B 已验)。
- **period 映射**:我们的 `Period`(15m/1h/1d/1w)→ akshare(daily/weekly)。**★ 阶段一先支持日线/周线**
  (零-B 只测 daily);分钟级 akshare 港股支持度待确认,不支持则阶段一只日 / 周(决策点 3)。
- 字段映射:akshare 列(日期/开盘/收盘/最高/最低/成交量…)→ 我们的 `Kline` schema。
- 限流 / retry:复用 `BaseDataSource._retry`(对齐 us_source)。
### 2.3 实时 / 最新价(★ 带降级 · 零-B 实测连接不稳)
- 实时:akshare 港股实时(`stock_hk_spot_em`)取目标 symbol 最新价。
- **降级**:`try 实时 → 失败则用 CH 最近一根 K 线收盘价兜底`(`select_kline limit=1`)→ **绝不崩**。
- 只在「需要最新价」(报价 / 撮合价)时调,**非高频轮询**(红线:只读 CH 为主 + 低频 warm)。
### 2.4 代码规范化(港股 5 位数字)
- 港股代码 5 位补零(`700`/`0700`/`00700`/`00700.HK` → 规范成 `"00700"`)。
- akshare 用 `"00700"`;yfinance 风格 `0700.HK`(备用源 / 深链)。
- 对齐 crypto `BTC/USDT`↔`BTCUSDT` 的 normalize 模式(放 hk_source 内或 order/query 的市场分支)。

---

## 3. 采集复用现有模型(零新管线)
- hk K 线走 market.py:70-115 现成「**读 CH 优先(`select_kline`)→ miss 回源(`_source_for`→`hk_source.fetch_kline`)→ `insert_kline` 缓存**」。
- 只需:`_source_for`(market.py:146)mapping 加 `"hk": hk` + `api/deps.py` 加 `HkSourceDep`(对齐 `CnSourceDep`)。
- 板块榜单(spot/sector)= **阶段四可选**,阶段一不做。

---

## 4. 每手股数策展配置(阶段一搭壳 · 阶段三下单用)
### 4.1 结构
- 新建 `app/services/hk_pool.py`(对齐 `us_pool.py` 策展池)· `HK_LOT_SIZE: dict[str, int] = {"00700": 100, …}`(代码→每手股数)+ 标的元信息(名称)。
- 阶段三下单:`lot = HK_LOT_SIZE.get(code)`;**`None` → 该标的暂不可下单**(决策②兜底,给提示)。
### 4.2 ★ 首批策展池 + 每手股数【种子值 · 全部待核 HKEX 官方 board lot】
> 以下是**最佳努力的种子值**,**必须核对港交所官方每手**(board lot 会变);请你 + 产品负责人 / Hans 核。

| 代码 | 名称 | 每手股数(种子·待核) |
|---|---|---|
| 00700 | 腾讯控股 | 100 |
| 09988 | 阿里巴巴-W | 100 |
| 03690 | 美团-W | 100 |
| 01810 | 小米集团-W | 200 |
| 09618 | 京东集团-SW | 50 |
| 01024 | 快手-W | 100 |
| 09999 | 网易-S | 100 |
| 09888 | 百度集团-SW | 50 |
| 00388 | 香港交易所 | 100 |
| 01299 | 友邦保险 | 200 |
| 00005 | 汇丰控股 | 400 |
| 00939 | 建设银行 | 1000 |
| 01398 | 工商银行 | 1000 |
| 00941 | 中国移动 | 500 |
| 02318 | 中国平安 | 500 |
| 01211 | 比亚迪股份 | 500 |
| 02015 | 理想汽车-W | 100 |
| 09868 | 小鹏汽车-W | 100 |

(首批 ~18 只核心蓝筹 + 科技 + 中概回港;阶段三/四再扩到 ~120 只对齐美股池规模 — 决策点 1/2。)

---

## 5. 红线(数据层)
- **虚拟资金**:数据层不碰交易,纯采集 / 存储。
- **只读 CH 为主**:warm 是 cache miss 时低频回源(非高频轮询);实时最新价按需取 + 降级兜底(§2.3)。
- **不碰 cn/us/crypto**:`_source_for` 加一行、Enum8 加一值、init.sql 加配置 —— 现有市场行为零变。
- **迁移可回滚**(§1.5)· **顺序硬约束**(ALTER 先于 hk 采集代码上线)。
- **TG 零回归**:数据层完全不碰 bot 渲染(replies/renderers)→ golden 天然不受影响(数据层 PR 不动 bot 文件)。

---

## 6. 阶段一内部拆分(小步 · 每步 feature 分支 + 审 + 验收 + 合 main)
| 子步 | 范围 | 风险 | 验收点 | 分支 |
|---|---|---|---|---|
| **P1-1 · CH 迁移先行**(单独验)| 迁移脚本(执行 ALTER · 幂等 + 停 worker 护栏)+ init.sql 同步 + midas_test 演练 up/down/up + **Hans 生产手动迁移** + 回滚预案文档 | 中(改存储)| `SHOW CREATE` 确认 hk + 可逆 + 现有采集不受影响 · 按 0033 盯 ops 确认 | feat/hk-1a-ch-migrate |
| **P1-2 · hk_source 适配** | `hk_source.py`(fetch_kline akshare + qfq 复权 + normalize + 实时降级)+ `_source_for` 接入 + deps + `hk_pool.py` 壳 | 低(纯新增)| `HkSource.fetch_kline("00700", "1d")` 返数据 · 单测(mock akshare)· 现有源零回归 | feat/hk-1b-source |
| **P1-3 · 采集打通**(端到端)| 无新代码(验证现有 market.py 链路对 hk 生效)+ 必要的 normalize 接入点 | 低 | `/market/kline?market=hk&symbol=00700&period=1d` → 读 CH miss → hk_source 回源 → insert → 再读命中;00700 日 K 进 CH 可读出 | feat/hk-1c-collect |

- **P1-1 迁移单独先上**:它改存储,单独一个分支 + 单独部署验证(0033 铁律:盯 Actions 绿 + docker ps + **Hans 确认 CH 迁移成功**);
  迁移确认 OK 才继续 P1-2/3(否则 P1-2 的 hk 采集会因 Enum8 没 hk 而失败)。
- 每步真机验收过再合 main。

---

## 决策点(已拍板 · 2026-05-30)
1. **每手股数** → **现在定策展结构 + 种子值**(§4.2 的 ~18 只)· **真实每手数阶段三下单前核港交所(HKEX)官方**。
2. **首批港股标的池** → **接受 §4.2 这 ~18 只核心**(蓝筹 + 科技 + 中概回港);**阶段四扩到 ~120**。
3. **K 线粒度** → **港股首版只做日 / 周线**(若免费源不支持分钟级)· **分钟级以后补**。
4. **CH 迁移执行** → 走 §1.2「**Hans 手动 clickhouse-client ALTER(带外)+ 低峰停 worker · 先改库后上代码**」机制 ·
   P1-1 产出可执行迁移脚本(`scripts/hk-phase1/` · 执行 ALTER + 最高规格护栏 + 回滚 + midas_test 演练)给 Hans。

> 前置(写生产代码前 / 真改库前必须过):**① 工作日实时延迟补测**(`scripts/hk-phase0/probe_hk_latency.py`)·
> **② midas_test 迁移可逆演练**(`scripts/hk-phase1/rehearse_ch_migration_testdb.sh`)。两个都过 → 才真在生产改库。

---
> 待审重点:**§1 迁移方案(机制解耦 + 可逆演练 + 回滚)**· **§2.3 实时降级**· **§6 子步拆分(P1-1 迁移单独先行)**。
> 审过 + 拍板 → 先做 **P0 工作日延迟补测 + midas_test 迁移演练** → 再进 P1-1 写迁移脚本。本轮只出细案。
