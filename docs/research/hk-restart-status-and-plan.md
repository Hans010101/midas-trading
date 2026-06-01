# 港股重启 · 接数据源 现状盘点 + 路径梳理

> 性质:**纯梳理 · 不动代码**。整合 ADR 0034/0034a 已定方案 + 实测现状(分支/生产 CH),
> 供产品负责人确认重启路径,确认后再分步开工。
> 日期:2026-06-01 · 基线:当前 main + 4 个 hk 分支 + 生产 CH 实测。

---

## TL;DR

- 港股**卡在「接数据源」这步**(产品负责人判断准确):铺路骨架在 main,CH 迁移脚本在分支(已实测成熟),
  但 **`hk_source.py`(数据源适配器)从没写**,生产 CH 也没迁移 → **港股从没采过一行数据**。
- 方案早已定死(ADR 0034/0034a Accepted + 阶段零实测):**主源 akshare**(`stock_hk_hist` 日/周线 + 前复权,实测 OK)·
  **复用 kline 表 + 现有采集链路**(零新管线)· 标的策展 ~18 只。
- 重启路径 = **P1-1 生产 CH 迁移(Hans 带外)→ P1-2 写 hk_source → P1-3 采集打通 → 阶段二行情页显示**。
- ★ 延迟补测(P0)**不卡接数据**:它只影响「实时报价」(阶段三下单才用),历史 K 线行情展示不依赖 → 建议推后。

---

## 1. 现状盘点

### 1.1 main 已有(铺路骨架 · 早期合入)
| 项 | 位置 | 状态 |
|---|---|---|
| Market 类型含 hk | `schemas/market.py:15` `Literal["cn","us","crypto","hk"]` | ✅ |
| 每手股数策展壳 | `app/services/hk_pool.py`(`HK_LOT_SIZE` 种子值) | ✅ 壳在 |
| 港股占位页 | `apps/web/app/hk-market/page.tsx` | ✅ 占位 |
| 港股交易日历状态机 | `market_calendar.py:120` `_hk_status`(早盘/午休/午盘 + 节假日表)| ✅(注释自标「hk 无数据,仅状态机壳」)|
| **hk_source 适配器** | `app/services/data_sources/` | ❌ **没有**(接数据核心缺口) |
| **_source_for 接 hk** | `services/market.py` mapping | ❌ 未接 |
| **CH Enum8 含 hk** | `docker/clickhouse-init.sql` | ❌ 无 hk |

### 1.2 生产 CH 实测(今天 · 确认从没采过)
```
SELECT DISTINCT market FROM kline → cn / us / crypto(无 hk)
kline.market = Enum8('cn'=1,'us'=2,'crypto'=3)  ← 无 hk=4,插 market='hk' 会被 CH 拒
```
→ 港股停在「骨架完成、没接数据源」,**生产迁移/接数据/延迟补测都没落地**(全在分支)。

### 1.3 四个 hk 分支(都未合 main)
| 分支 | 内容 | 程度 / 演练 | 能直接用? |
|---|---|---|---|
| **feat/hk-phase0-probes** | 阶段零探测脚本(`probe_ch_enum8.sh` + `probe_hk_data.py`) | 实测已跑(结论见 §1.4)· 只读 | ✅ 服务器只读复跑(延迟补测用) |
| **feat/hk-phase1-migration** | P1-1 CH 迁移脚本(`migrate` + `rollback` + `rehearse` 演练 + `probe_hk_latency`) | ★ **midas_test 演练全绿 + CH 26.4.2.10 兼容治本**(commit 实证:复现两类不兼容并修)· 已 merge main 同步 | ✅ **迁移脚本成熟,可直接用** |
| **feat/hk-phase1-config** | 前端市场维度加 hk(31 文件:market-switcher / shared 类型 / fees / format-money / workbench-store)+ 重复的 hk-phase1 脚本 | 阶段二「市场维度」前端**超前做了一半** | ⚠️ 属**阶段二**范畴,接数据阶段用不上,留到阶段二再理 |
| docs/adr-0034-hk-market · docs/hk-phase1-plan | ADR 文档分支 | 已合 main(0034/0034a 在 `docs/decisions/`) | — |

### 1.4 阶段零实测结论(0034a 已记录 · 已确认)
- **零-A CH Enum8 迁移**:✅ 加 `hk=4` 纯加值、metadata-only、轻量(kline 1.6 万行 / symbol_meta 4 行)。
- **零-B 历史 K 线**:✅ `ak.stock_hk_hist("00700")` 5408 行 + 前复权(qfq)生效 → **主源定 akshare**(免费源够用)。
- **零-C 每手股数**:✅ 走**手动策展兜底**(hk_pool 配死每手,不依赖免费源动态取)。
- **实时延迟**:⏳ **周末测不准**(yfinance 1461min 不可信 + akshare 实时接口被掐)→ 需工作日港股时段补测。
  ★ 但**只影响实时报价**(阶段三下单用),历史 K 线行情展示**不依赖**。

---

## 2. 接数据源方案(ADR 0034/0034a 已定 · 重新摆出)

| 维度 | 方案 | 依据 |
|---|---|---|
| **数据源(主)** | **akshare** `stock_hk_hist(symbol, period, adjust="qfq")`(日/周线 + 前复权) | 0034a §2.2 · 零-B 实测 OK |
| 数据源(备) | yfinance `.HK` ticker(`0700.HK`) | 0034 §2.2 |
| **采什么标的** | 策展热门池 **~18 只**(00700 腾讯 / 09988 阿里 / 03690 美团 / 01810 小米…)· 阶段四扩 ~120 | 0034a §4.2 · 决策② |
| **采集频率/触发** | **复用现有 cache-aside**:`select_kline` 读 CH 优先 → miss 才 `hk_source.fetch_kline` 回源 → `insert_kline` 缓存 · **非高频轮询** | 0034a §3 |
| **存哪张表** | **复用 `kline` 表**(`market='hk'`)+ `symbol_meta` · **零新表、零新管线** | 0034a §3 |
| **采集器** | **新写 `hk_source.py`**(`class HkSource(BaseDataSource)` · 对齐 cn_source/us_source)· 内部 normalize 港股 5 位代码 + 实时降级(失败回落 CH 最近收盘价) | 0034a §2 |
| K 线粒度 | 首版**日/周线**(分钟级 akshare 港股支持度待定,以后补) | 0034a 决策③ |

> ⚠️ **全球概览那个 yfinance 通用采集器能用于港股吗?** 不能直接用——那是**指数/商品概览**(`global_overview`),
> 不是**个股 K 线**;但 `hk_source` 走的是 `BaseDataSource.fetch_kline` 模式(同 cn/us source),**模式可复用、代码要新写**。

---

## 3. 完整步骤 + 风险分档

| 步 | 内容 | 风险 | 谁做 | 现状 |
|---|---|---|---|---|
| **P0 · 延迟补测**(可推后) | 工作日港股时段(09:30–16:00 HKT)跑 `probe_hk_latency.py`,确认 akshare 实时延迟 ≤15min | 低(只读探测) | Hans 服务器(需工作日) | 未做 · **只卡阶段三下单报价,不卡历史行情** → 建议推到阶段三前 |
| **P1-1 · 生产 CH 迁移** | 低峰 + `docker compose stop worker` → 跑 `migrate_ch_market_enum.sh`(ALTER 加 hk=4 两表)→ `SHOW CREATE` 验证 → `start worker` | **中**(改生产存储)· 但**加值 metadata-only 无害 + 演练全绿 + 回滚预案** | ★ **Hans 带外手动**(clickhouse-client · 不进 deploy pipeline) | 脚本成熟(feat/hk-phase1-migration)· 待 Hans 执行 |
| **P1-2 · hk_source** | 写 `hk_source.py`(akshare fetch_kline + qfq + 5 位 normalize + 实时降级)+ `_source_for` 加 `"hk"` + deps `HkSourceDep` | 低(纯新增 · 不碰现有源) | Code(feature 分支) | **未写 · 核心缺口** |
| **P1-3 · 采集打通** | 验证 `/market/kline?market=hk&symbol=00700&period=1d` 走通(读 CH miss → hk_source 回源 → insert → 命中) | 低(验证现有链路) | Code | 未做 |
| **阶段二 · 行情页显示** | 市场维度 ~15 处加 hk + 行情/自选/持仓**只读**显示 + HKD 格式(feat/hk-phase1-config 前端做了部分) | 低(加配置) | Code | 部分(config 分支) |
| 阶段三 · 下单(每手) | lot_size 整手取整 + 不足 1 手拒单 + HKD 名义(**需先做 P0 延迟补测**) | 大(碰下单) | 后期 | 未做 · 本次不碰 |

★ **顺序硬约束**:P1-1 CH 迁移**必须先于** P1-2 hk 采集代码上线(否则插 `market='hk'` 被 CH 拒)。

---

## 4. 红线核对

- ✅ **港股 = 股票现货行情展示 · 只读 · 不可交易**:本次接数据只到「行情 K 线进 CH + 可读出」,**不碰下单**(下单是阶段三,且全程虚拟撮合)。
- ✅ **接数据只读上游**:akshare 历史 K 线 + 低频 cache-miss warm,**非高频轮询**;实时价按需取 + 降级兜底。不接任何真实券商通道。
- ✅ **与「加密合约为主」定位不冲突**:港股是**行情展示 + 复用现货路径**(对齐 A 股/美股),不套合约逻辑,是已有四市场框架的自然补全。
- ✅ **CH 迁移单向加值无害**:`'hk'=4` 加值 metadata-only;收窄(MODIFY-down)被 CH 禁(Code 524 · 已实测),回退靠「留着 4 值零影响」或整表重建。
- ✅ **现有 cn/us/crypto 零回归**:`_source_for` 加一行、Enum8 加一值、init.sql 加配置 — 现有市场行为零变。
- ✅ **凭证**:akshare 免费无 key;不进 git/前端/日志。

---

## 5. 需产品负责人确认 / 执行的点

1. **确认重启路径**:P1-1 迁移 → P1-2 hk_source → P1-3 采集 → 阶段二行情显示(本次目标 = 港股历史行情能在 K 线图显示)。
2. **★ P0 延迟补测时机**:现在工作日补测,还是**推到阶段三下单前**?**建议推后** — 接历史行情数据不依赖实时延迟,先让港股行情图有数据。
3. **★ P1-1 CH 迁移执行**:Hans 选低峰窗口**带外手动执行**(脚本在 feat/hk-phase1-migration,已演练全绿)。确认后:把迁移脚本合 main(归档)还是 Hans 直接用分支脚本跑?
4. **feat/hk-phase1-config(前端阶段二超前)怎么处理**:接数据阶段用不上 → 留到阶段二时并入,还是先看看它做了什么再定?(本次接数据不需要它)
5. **标的池**:沿用 0034a 的 ~18 只种子(每手数阶段三下单前核 HKEX 官方;接数据阶段每手不影响)。

> 方案确认后开工顺序建议:**先 P1-1(Hans 迁移)→ 我写 P1-2 hk_source + P1-3 采集打通(一个 feature 分支,审 + 真机验 /market/kline?market=hk 出数据)→ 再议阶段二行情页显示**。本轮只梳理,未动代码。
