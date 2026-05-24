# 0020 · 加密永续合约虚拟交易 M2-C.2:资金费结算 + 真标记价 + 实战策略清单

## 状态

**Proposed**(2026-05-24)· 待产品负责人审定 **§11「待拍板决策」** 后转 Approved,再按本 ADR 写实现代码。

> 只做设计,不含已落地实现代码。表结构 / 任务 / 公式均为「建议」,审定后才写。
> 接 ADR-0019(M2-C.1 核心闭环,已上线)· 本文是其 §4.8 / §11(D5/D7/D10)的展开。

---

## 红线(最高优先 · 先读)

1. **全程虚拟资金,永不接任何真实交易 / 下单 / 转账通道。** 资金费结算、强平、标记价全部走点金虚拟逻辑;Binance `premiumIndex` / `fundingInfo` 只用于**读行情/读元信息**,绝不下单。
2. **资金费 / 杠杆 / 强平只是虚拟教学**,不是真钱。
3. **实战策略清单只读提示,绝不自动下单**(沿用 0019 红线 §4)· 必带「VIRTUAL·模拟」+「仅供参考,不构成投资建议」。

---

## 上下文

M2-C.1(0019)已上线:perp 开/平/反手/逐仓保证金/强平(60s worker)/持仓订单中心。
当时三处**有意延后到 M2-C.2**,现在做:

| 延后项 | 0019 当时的状态 | 本期目标 |
|---|---|---|
| 资金费结算(D5) | 不计;`VirtualPerpPosition.funding_paid` 字段已预留(恒 0)| 按**各币种各自周期**结算并计入 |
| 真标记价(D7 / §4.1) | 撮合/强平用 **perp ticker `last_price`** 代理 | 接 premiumIndex 真 `markPrice` |
| 实战策略清单 | 详情页 4 条规则**占位** | 由实时指标驱动、只读提示 |

### 现状实测(已确认 · 引 0019 §4.8.1)

- `crypto_funding_rate` 表:`symbol/ts/rate/mark_price`,**无 interval 列**;`funding_rate_refresh` 每轮 `fetch_funding_rate(limit=1)` 只存最新一条。
- **`/fapi/v1/fundingInfo` 从未调用**(非8h币的 `fundingIntervalHours` 没采)。
- `futures/{sym}/info`:`next_funding_time = 最近ts + 8h`(**硬编码 bug**,crypto.py:346,对非8h币错)· `max_leverage=125`(stub)· `index_price=mark_price`(近似)。
- `binance_futures_source.fetch_symbol_info()` **已拉** `/fapi/v1/premiumIndex`(返回 `markPrice/indexPrice/lastFundingRate/nextFundingTime`)+ `/fapi/v1/exchangeInfo`,但只返回 raw dict、没接进任何端点。
- 缠论:`GET /api/v1/analysis/chan` → `buy_sell_points[].kind ∈ {B1,B2,B3,S1,S2,S3}`(**S1 = 一卖**)。
- perp 指标:`/futures/metrics-batch` → `funding_rate / account_long_short_ratio / oi_change_pct_24h`;`/perp/positions` 已返回 `liquidation_distance_pct`。

### 🔑 跨块关键联动(本 ADR 的核心洞察)

**接 premiumIndex(Block 2)= 一次拿到 `markPrice` + `indexPrice` + `lastFundingRate` + `nextFundingTime`**,于是:
- Block 2 的真标记价 ← `markPrice`;
- Block 1 的资金费率/下次结算 ← `lastFundingRate` / `nextFundingTime`(顺带修掉 +8h bug);
- Block 3 策略③的**基差 = markPrice − indexPrice 直接可算** → **D10 的「基差未采集需降级」前提被解除**(详见 §8.3 + §11 E7)。

所以三块共享一个数据源(premiumIndex),建议**一个统一采集 + 统一表**收口(§8.1)。

---

## Block 1 · 资金费结算

### 1.1 补采集「结算周期」(各币 funding interval)

- 新增 `binance_futures_source.fetch_funding_info()` → `GET /fapi/v1/fundingInfo`,返回**非8h币**的 `[{symbol, fundingIntervalHours, adjustedFundingRateCap, adjustedFundingRateFloor}]`;**未列出的币默认 8h**。
- 慢变(交易所偶尔调)→ 采集频率低(每 6h / 每日一次足够)。
- 存储:见 §8.1(建议并入统一 `crypto_premium_index` 表的 `funding_interval_hours` 列,或独立 `crypto_funding_info` 小表)。

### 1.2 资金费结算任务

新 Celery beat task `tasks.perp.settle_funding`。逐仓 · 线性合约 · 对每个活仓在其**各自结算时刻**计费:

```
funding_payment = funding_rate × mark × qty            # USDT
long :  cash_balance -= funding_payment   (rate>0 多头付)
short:  cash_balance += funding_payment   (rate>0 空头收)
       → 统一:cash_balance -= sign × payment(long sign=+1, short sign=−1)
       position.funding_paid 累加;写资金费流水(见 §8.2 / E5)
```

**触发时机(E3 待拍板)**:交易所均在**整点**结算(8h→00/08/16 UTC;4h→00/04/08…;2h→偶数点;1h→每点)。
- 方案 A(推荐):**每 UTC 整点跑一次**,对每个活仓 symbol 用 `funding_interval_hours` + 整点对齐判断「此刻是否其结算点」(`hour % interval == 0`),是则结算。一个任务覆盖所有周期。
- 方案 B:用 `premiumIndex.nextFundingTime` 逐 symbol 精确驱动(更准、更重)。

### 1.3 资金费扣款 → 保证金不足 → 强平衔接(E4 · 核心待拍板)

逐仓下,资金费扣的是**账户可用 `cash_balance`**(非冻结的 initial_margin)。问题:cash 扣到不足 / 持仓权益被侵蚀后,要不要触发强平?

- 方案 A(简化 · 教学够用):资金费只扣 `cash_balance`,**不联动强平**;cash 可能变小但仓位强平仍只看 `mark vs liquidation_price`(0019 现状)。`cash_balance` 设地板不为负(扣到 0 封底)。
- 方案 B(更真实):把累计资金费纳入「持仓有效权益」→ 资金费持续为正侵蚀多仓权益 → 强平 worker 在「权益 < 维持保证金」时触发强平。需**扩展 0019 强平判断**(从纯 `mark` 价触发 → 加「账户/仓位权益」触发),并可能重算 `liquidation_price`(含 funding)。
- 推荐:**A 起步**(M2-C.2 先把结算跑通,扣 cash,UI 显示累计资金费);B(资金费致强平)留 M2-C.2 的二阶段或 M2-C.3,避免一次改动太多强平核心逻辑。

### 1.4 修 `next_funding_time` 硬编码 bug(Block 2 顺带解决)

`futures/{sym}/info` 改为读统一表(来自 premiumIndex 采集):
- `next_funding_time` ← premiumIndex 真 `nextFundingTime`(替代 `+8h`);
- `index_price` ← premiumIndex 真 `indexPrice`(替代 `=mark`);
- `max_leverage` ← exchangeInfo 真值(替代 `125` · 可选,低优先)。

---

## Block 2 · 真标记价(mark price)接入

### 2.1 数据源 & 采集

- mark price ← `premiumIndex.markPrice`(标记价,抗插针;比 ticker `last_price` 更"官方")。
- **新增高频采集** `tasks.crypto.premium_index_scan`:`GET /fapi/v1/premiumIndex`(不带 symbol = **一次返回全市场**所有 perp 的 `markPrice/indexPrice/lastFundingRate/nextFundingTime`,极轻,类似 ticker)→ 写统一表。频率高(30s–1min · mark 变化快)· 错峰。

### 2.2 撮合/强平价源切换(零改引擎)

- 0019 的注入式 `PerpPriceFetcher` 设计就是为此:**只换 `make_perp_mark_price_fetcher` 的数据源**(从 `crypto_ticker_24h.last_price` → 统一表的 `mark_price`),`perp_engine` / 强平 worker 逻辑**一行不改**。
- ⚠️ E6:切源后撮合价从 ticker last → mark price,**同一笔单的成交价会有细微差异**(教学可接受,但要确认)。

---

## Block 3 · 实战策略清单接真实(只读提示)

详情页 4 条规则,由实时指标驱动,命中点亮 + 文案,**绝不自动下单**:

| # | 规则 | 触发判定(数据源) | 命中提示 |
|---|---|---|---|
| ① | 资金费正 + OI 增 → 顺势开多 | `funding_rate > 0` 且 `oi_change_pct_24h > 0`(metrics-batch / premiumIndex + OI) | 🟢 多头情绪占优,可考虑顺势开多(虚拟)|
| ② | 大户多空比极端 → 反向预警 | `account_long_short_ratio > 2` 或 `< 0.5`(metrics-batch) | 🟡 情绪过热,警惕反向 |
| ③ | 缠论一卖 + 基差走弱 → 减仓 | `analysis/chan` 最近 `buy_sell_points` 含 **S1** 且 **基差率走弱**(基差 = mark − index,来自 Block 2 premiumIndex)| 🟡 缠论卖点 + 基差转弱,可考虑虚拟减仓 |
| ④ | 强平距现价 < 5% → 降杠杆 | 当前**活仓** `liquidation_distance_pct < 5`(/perp/positions)| 🔴 强平距离仅 a% · 建议降杠杆/加保证金 |

- **策略③不再降级(E7)**:0019 D10 因「基差未采集」要求降级为只看缠论;Block 2 接 premiumIndex 后 `indexPrice` 有了 → **基差 = mark − index 可算** → ③ 可全做(缠论 S1 + 基差率阈值)。详情页 ⑥ 基差图也顺带能接真数据(本期可选)。
- 实现位置(E8):前端用已取的 metrics/positions/premiumIndex + 调 `analysis/chan` 自行判定(少一个后端端点),或后端出 `GET /perp/strategy-signals?symbol=` 聚合。推荐**前端算**(数据详情页大多已在取)。

---

## §8 跨块:数据模型 / 采集 / 衔接

### 8.1 数据模型变动(ClickHouse · E1/E2 待拍板)

**推荐:统一「合约实时元信息」表**(一次 premiumIndex 采集填满,一表多用):
```sql
crypto_premium_index (
  symbol String, ts DateTime,
  mark_price Float64, index_price Float64,
  last_funding_rate Float64, next_funding_time DateTime,
  funding_interval_hours UInt8 DEFAULT 8,   -- 来自 fundingInfo(慢刷合并)· 默认 8
  ingested_at DateTime DEFAULT now()
) ENGINE=ReplacingMergeTree(ingested_at) ORDER BY (symbol, ts) TTL ...
```
- 服务:Block2 mark price + Block1 资金费率/周期/下次结算 + futures/info 修复 + 策略③基差,全从这一张表读。
- 备选:mark/index 高频表 + funding_info 慢刷表 分开(E2)。

### 8.2 数据模型变动(PostgreSQL · E5 待拍板)

- `VirtualPerpPosition.funding_paid`:0019 已建,本期开始累加。
- 资金费流水:① 新建 `virtual_perp_funding`(position_id, symbol, funding_rate, mark, payment, settled_at)· 审计/复盘;或 ② 只更 `funding_paid` + cash 不建流水(轻量)。推荐 ①(可复盘 + 详情页/账户页可展示资金费历史)。

### 8.3 采集变动

- 新 `premium_index_scan`(高频 30s–1min · 全市场一请求)+ `funding_info_refresh`(慢刷 6h/日)· 错峰排进 celery beat(避开现有 ticker/oi/longshort/funding 的分钟栅格)。
- 现有 `funding_rate_refresh`(15min · limit=1)可保留(历史资金费率时序),或被 premium_index 的 `last_funding_rate` 取代(E2 一并定)。

### 8.4 前后端改动范围

- **后端**:`fetch_premium_index()` + `fetch_funding_info()`(data source)· 2 个采集 task + beat · `crypto_premium_index`(+`crypto_funding_info`?)CH 表 + DDL · `settle_funding` 结算 task · `make_perp_mark_price_fetcher` 换源 · `futures/info` 修复 · (E4-B 才改强平判断)· (E8 才加 strategy-signals 端点)· 资金费流水表 migration(E5-①)。
- **前端**:详情页「实战策略清单」占位 → 真实(4 规则)· (可选)详情页 ⑥ 基差图接真数据 · (可选)资金费历史展示。
- **不碰**:0008 现货 · perp 撮合/持仓/订单中心核心(只换价源,不改逻辑)。

---

## §9 分期建议(若一期做不完)

| 期 | 范围 | 理由 |
|---|---|---|
| **M2-C.2.1** | premiumIndex 采集 + 统一表 + **真 mark price 接入**(换价源)+ 修 `futures/info`(next_funding_time/index_price)| mark price 是资金费 & 策略基差的**共同前置**,先做 |
| **M2-C.2.2** | fundingInfo 采集 + **资金费结算任务**(按各币周期 · 扣 cash)+ 资金费流水/展示 | 依赖 2.1 的 mark + interval |
| **M2-C.2.3** | **实战策略清单**接真实(4 规则 · ③用基差不降级)· (可选)资金费致强平(E4-B)· 基差图真数据 | 依赖 2.1/2.2 |

---

## §10 风险点

1. **资金费致强平的数值边界(E4-B)**:逐仓下资金费侵蚀权益 → 强平判断要从「纯价格」扩展到「含 funding 的权益」,改动强平核心,易引入 bug;先用 A(扣 cash 不联动)降风险。
2. **premiumIndex 采集频率 vs 限流**:高频(30s）全市场请求,需确认 Binance fapi 权重;错峰 + expires。
3. **结算时刻对齐**:整点 + interval 对齐判断要精确(UTC 整点;1h 币每点、2h 偶数点…),错则多结/漏结。
4. **mark price 切源(E6)**:撮合价 ticker→mark,既有用户体感价格微变(教学可接受,需告知)。
5. **cash 扣负**:资金费扣款封底处理(不为负 / 或允许负 + 提示),需定义。
6. **基差解锁后策略③范围(E7)**:确认基差率「走弱」阈值定义(如基差率 < 0 或环比转负)。
7. **Decimal 精度 / 量纲**:资金费 `rate×mark×qty` 全程 Decimal + quantize(0002 教训)。

---

## §11 待产品负责人拍板的决策(最重要 · 逐条)

| # | 决策 | 选项 | 推荐 |
|---|---|---|---|
| **E1** | funding interval 存储 | A 落库(统一表列 / 独立小表)· B 结算时实时拉 fundingInfo | **A · 落库**(慢刷,稳定)|
| **E2** | premiumIndex 数据表 | A **统一表** `crypto_premium_index`(mark/index/funding/nextFunding/interval 一表)· B mark 高频表 + funding_info 慢表 分开 | **A · 统一表**(一表多用,最省)|
| **E3** | 资金费结算触发 | A 每 UTC 整点扫 + `hour % interval` 对齐 · B premiumIndex.nextFundingTime 逐 symbol 驱动 | **A**(简单、覆盖所有周期、对齐交易所整点)|
| **E4** | 资金费扣款 & 致强平 | A 只扣 cash、**不联动强平**(简化)· B 纳入权益、**可致强平**(真实,改强平核心)| **A 起步**(B 留 2.3 / M2-C.3)|
| **E5** | 资金费流水 | A 新建 `virtual_perp_funding` 流水表 · B 只更 `funding_paid`+cash 不建流水 | **A**(可复盘 + 可展示)|
| **E6** | mark price 切源影响 | 撮合/强平价 ticker `last_price` → premiumIndex `markPrice`,数值微变是否接受 | **接受**(mark 更官方、抗插针)|
| **E7** | 策略③基差降级 | A 接 premiumIndex 后**不降级**(用 mark−index 算基差)· B 仍按 0019 D10 降级为只看缠论 | **A · 不降级**(基差已解锁)|
| **E8** | 策略信号算在哪 | A 前端算(用已取数据 + 调 analysis/chan)· B 后端 `/perp/strategy-signals` 聚合端点 | **A · 前端**(少一个端点)|
| **E9** | 资金费方向确认 | `rate>0`:多头付、空头收(标准永续)· 计入虚拟盈亏 | **确认标准方向** |
| **E10** | `next_funding_time` 修复 | A 回源 premiumIndex 真 `nextFundingTime` · B 用 interval 算(ts+interval) | **A · 回源 premiumIndex**(交易所真值)|
| **E11** | `funding_rate_refresh`(15min limit=1)去留 | A 保留(独立资金费率时序)· B 被 premiumIndex.last_funding_rate 取代 | 倾向 **A 保留**(各司其职),请确认 |

---

## §12 红线复述(实现前再读)

- **永不接真实下单** · premiumIndex/fundingInfo 只读;资金费/强平走虚拟逻辑。
- **资金费/杠杆/强平仅虚拟教学。**
- **策略清单只读提示,绝不自动下单** · 全程「VIRTUAL·模拟」+「不构成投资建议」。

---

## 修订记录

### v1 (2026-05-24) · 初稿 Proposed

接 0019(M2-C.1 上线)· 展开资金费结算(按各币周期)+ 真标记价(premiumIndex)+ 实战策略清单三块。核心洞察:premiumIndex 一源解三块(mark/资金费/基差),建议统一表 + 先做 mark price。待 §11 十一条决策审定后转 Approved。
