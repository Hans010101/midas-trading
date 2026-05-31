# 0037 · AI 模拟交易第二层【形态A:AI 推荐策略模板 + 模拟信号展示】设计

## 状态
**Accepted**(2026-06-01 · 产品负责人审过 §1 展示型边界 + §6 排除自动交易/沙箱 + §5.3 三套主图 + §7 零回归,并拍板 7 个细节,见 §拍板结论)· 本 ADR 只出设计,不含实现代码。按 §8 分单元开工(MVP = 前 3 单元 · 单元1 = 后端序列信号引擎先行)。

> 调研基线:[docs/research/ai-strategy-form-a-feasibility.md](../research/ai-strategy-form-a-feasibility.md)(已读源码核实复用度,带 file:line)。
> 上游依赖:[ADR 0036](0036-ai-simulated-trading.md) —— 第一层(AI 建议→一键下单,批次甲已上线)+ 批次乙(自学习闭环 memory/reflection/ai-accuracy 已上线)+ §4 排除清单。形态A = 0036 §5「第二层」的**轻量展示型变体**。

---

## 上下文

第一层(批次甲)已让用户「看 AI 建议 → 一键模拟下单」;批次乙已让 AI 决策「可验证」(历史命中率)。第二层要往**「策略指导」**走一步:平台预设几个经典策略模板,**AI 推荐这个标的现在适合用哪个策略**,并把该策略的**历史买卖信号点标在 K 线上** + 提示**当前是否触发**。

★ **形态A 的本质是「展示型 / 指导型」**:AI 选策略 + 把信号画给用户看,让用户**看得懂、学得到**。**不执行策略、不自动下单、不跑模拟撮合** —— 用户看完信号若要下单,**仍走第一层「一键模拟下单」**(不新建任何自动交易机制)。

调研结论(复用度 ~65–70%,详见研究文档):
- **极高复用**:K 线图、**信号标注 overlay(`midas-fractal`,策略信号与缠论买卖点完全同构)**、指标线(klinecharts 内置)、K 线读取(`select_kline`)、AI 管线、二次确认/VIRTUAL/disclaimer、展示型策略 UI 先例(`StrategyChecklist`)。
- **唯一真缺口**:现有指标全是「最新快照值 / 当前是否命中」([indicators.py](../../apps/api/app/services/ai/indicators.py) 只 return 尾值),**没有任何地方算「历史信号点序列」** → 需新增**序列级信号扫描器**(数学基础可复用,改成吐序列 + 找穿越点)。

### 产品负责人拍板(本 ADR 据此设计)

| # | 拍板 | 落到本 ADR |
|---|---|---|
| ① | **3 个经典策略模板**(纯价格 · 四市场通用):均线金叉(MA5×MA20)/ RSI 超卖反弹(14·30/70)/ **布林带均值回归**(20·2σ,★触下轨买、触上轨卖,**不是突破追涨**) | §2 精确定义 |
| ② | **信号后端算**(序列扫描器 · 可单测 · 能喂批次乙命中率 · 与缠论架构一致),前端**复用 `midas-fractal` overlay** 标注 | §3 + §5 |
| ③ | **AI 推荐第一版走纯规则**(类比 `actionable.py` · 零 LLM 成本 · 可测),不上 LLM | §4 |
| ④ | **市场:cn / us / crypto**(港股搁置,等阶段三) | §1.3 + §5 |
| ⑤ | **MVP = 前 3 单元上线**;单元④(策略历史命中率 · 复用批次乙自学习闭环)作为随后增强 | §8 |

---

## 决策

## 1. 模块定位 + 边界 + 红线

### 1.1 头号红线(焊死)· 全程虚拟、不碰真实交易、不自动下单
- 形态A **只算信号 + 画信号 + 推荐策略**,**绝不执行策略、绝不自动下单、绝不触发任何撮合**(连虚拟撮合都不碰)。
- 用户看完信号若要下单 → **走第一层「一键模拟下单」**(0036 批次甲已上线:`execute` + 二次确认 + VIRTUAL + disclaimer)。形态A **不新开任何下单出口**。
- 与 0036 §1.1 一致:本模块不接任何真实交易所 / 券商通道。

### 1.2 展示型 / 指导型边界(精确:做什么 / 不做什么)
- ✅ **做**:预设策略模板信号计算(后端只读历史 K 线)+ 在 K 线标历史买卖信号点 + 提示当前是否触发 + AI 规则推荐「适合哪个策略」。
- ❌ **不做**:策略自动运行、自动下单、策略持仓管理、模拟撮合执行(那是**形态B**,本 ADR 不做)。
- ❌ **不做**:AI 生成可执行策略代码 / `safe_exec` 沙箱(0036 拍板④焊死)。
- ❌ **不做**:回测(收益/夏普/回撤曲线)—— 形态A 只标信号点,不算绩效(回测另见 [strategy-backtesting-feasibility.md](../research/strategy-backtesting-feasibility.md),CLAUDE.md 标 defer)。

### 1.3 ★ 现有功能完整保留 · 零回归
- 现有 **AI 分析决策卡(0012)、缠论标注(0011)、K 线图、第一层(0036 批次甲)、批次乙(自学习闭环)、四市场行情**,在形态A 落地后**行为不变、零回归**。
- 形态A 是在它们**旁边新增的一条只读展示能力**,不替换、不重构。零回归用 §7 证明。
- **市场范围**:cn / us / crypto(拍板④)。hk 搁置(无 hk 数据 + AI prompt 无 hk 键,等港股阶段三)。

---

## 2. 3 个策略模板的精确定义

**统一框架**:每个策略 = 对 K 线序列**逐根算指标 + 检测「穿越」事件** → 产离散信号点 `StrategySignal {ts, price, kind: buy|sell, reason}`。穿越式(crossover)= 状态切换的那**一根**才标点,**天然离散**、不连续噪音、完美匹配 `midas-fractal` 标注。所有策略**只用 OHLCV → 四市场通用**(不用资金费/OI 等加密专属指标)。

> 记号:`MA_n[i]` = 第 i 根收盘 SMA(n);`RSI[i]` = 第 i 根 RSI(14);`UP[i]/LOW[i]` = 第 i 根布林上/下轨;`C[i]` = 第 i 根收盘价。穿越判定都看**相邻两根**(i-1 → i)。

### 策略1 · 均线金叉/死叉(趋势范式)· key=`ma_cross`
- **参数**:fast=5,slow=20(收盘 SMA)。
- **买信号(金叉)**:`MA_5[i-1] ≤ MA_20[i-1]` 且 `MA_5[i] > MA_20[i]`。
- **卖信号(死叉)**:`MA_5[i-1] ≥ MA_20[i-1]` 且 `MA_5[i] < MA_20[i]`。
- **信号点**:`{ts: K[i].ts, price: C[i], kind, reason: "MA5 上穿 MA20(金叉)" / "MA5 下穿 MA20(死叉)"}`。
- 需 ≥ 21 根 K 线才有第一个可判定点(MA20 预热)。

### 策略2 · RSI 超卖反弹/超买回落(反转范式)· key=`rsi_reversal`
- **参数**:period=14,oversold=30,overbought=70(Wilder RSI,同 [indicators.py:87](../../apps/api/app/services/ai/indicators.py))。
- **买信号(超卖反弹)**:`RSI[i-1] < 30` 且 `RSI[i] ≥ 30`(从超卖区**回升上穿** 30 = 反弹确认)。
- **卖信号(超买回落)**:`RSI[i-1] > 70` 且 `RSI[i] ≤ 70`(从超买区回落下穿 70)。
- **信号点**:`reason: "RSI 超卖反弹(上穿30)" / "RSI 超买回落(下穿70)"`。
- ★ **口径(拍板①已定 · 反弹确认式)**:RSI **上穿 30 = 买 / 下穿 70 = 卖**(穿越回归),**不用**「进入超卖即买」(下穿 30)。理由:① 「反弹/回落」语义 = 极值后**回归**;② 穿越式离散,避免 RSI 持续 < 30 时连续标点的噪音。

### 策略3 · 布林带均值回归(反转范式)· key=`boll_reversion`
- **参数**:period=20,k=2.0σ(同 [indicators.py:117](../../apps/api/app/services/ai/indicators.py))。
- ★ **均值回归(不是突破追涨)**:价格偏离均值到极端(触轨)→ 预期回归中轨。
- **买信号(触下轨)**:`C[i-1] > LOW[i-1]` 且 `C[i] ≤ LOW[i]`(收盘**下破/触及下轨** → 博反弹回中轨)。
- **卖信号(触上轨)**:`C[i-1] < UP[i-1]` 且 `C[i] ≥ UP[i]`(收盘上破/触及上轨)。
- **信号点**:`reason: "价格触布林下轨(均值回归买点)" / "价格触布林上轨(均值回归卖点)"`。
- ★ **判定基准(拍板②已定)**:用**收盘价 `C` 穿越**(稳健,不被插针/影线误触发);**不用**当根最低/最高价 `touch`。

> **信号 kind 语义(拍板③已定)**:形态A 信号统一是抽象**「买/卖」(看涨/看跌)**,**不区分现货/合约**(因为形态A 不下单)。用户看完去第一层下单时,由第一层既有映射处理(现货 buy/sell、perp open_long/open_short,见 [actionable.py:36-62](../../apps/api/app/services/ai/actionable.py))。形态A 不重复这层映射。

---

## 3. 序列信号扫描器(核心新增)

**唯一真缺口** —— 把现有「只吐尾值」的指标数学改成「吐整段序列 + 找信号点」。

### 3.1 设计
- **新建模块**(建议 `app/services/ai/strategy_signals.py` 或 `app/services/analysis/strategy.py`,命名实现期定)。
- **输入**:`list[Kline]`(从 `ClickHouseClient.select_kline` 读,只读历史 K 线)+ `strategy_key` + 可选 `params`。
- **输出**:`list[StrategySignal]`,`StrategySignal = {ts: AwareDatetime, price: float, kind: Literal["buy","sell"], reason: str}`。
- **当前是否触发**:信号序列**最后一根 K 线**是否产生信号点(或「最近一个信号 + 距今几根」)→ 前端「当前触发」提示。

### 3.2 复用现有数学(序列化)
- 复用 [indicators.py](../../apps/api/app/services/ai/indicators.py) 的 `_sma` / `_ema_series`(MACD 已用,line 65)/ `_stdev` / RSI 的 Wilder 遍历(line 87)—— 但现有都只 return 尾值;扫描器需**逐根算出整段序列**(新增 `_sma_series` / `_rsi_series` / `_boll_series` 等序列版,或重构现有数学为序列版 + 尾值版共用)。
- ★ **纪律:不改现有 `compute_*` 的对外契约**(workflow / technical agent 仍要尾值快照,零回归)。序列版是**新增并行函数**,不动现有。

### 3.3 性能
- 200–500 根 K 线逐根算 MA/RSI/BOLL + 找穿越,纯 Python ~毫秒级(indicators.py 注释:200 根 ~3ms),低频只读端点,无压力。

### 3.4 ★ 喂批次乙(协同)
- 扫描器产的信号点是**结构化、可验证**的 → 单元④可把策略信号喂批次乙 reflection(算「该策略在该标的的历史命中率」),复用已上线的 `ai_analysis_memory` + reflection + `/ai-accuracy` 基建。MVP 不做,随后增强。

---

## 4. AI / 规则推荐适配层(第一版纯规则)

**拍板③:第一版纯规则推荐**,类比已上线的 [actionable.py](../../apps/api/app/services/ai/actionable.py)(`composite_label → ActionableAdvice` 纯函数确定性映射 + API 层补算 + 不改 workflow)。

- **输入**:当前行情快照(复用 `TechnicalSnapshot`:`trend_5d` + MA 排列 + RSI 值 + 布林位置/带宽)。
- **逻辑(纯函数确定性 · 可单测)**:
  - 趋势市(`trend_5d=up/down` + MA 多头/空头排列)→ 推荐 **均线金叉**(`ma_cross`)。
  - 震荡市(`trend_5d=sideways`)+ RSI 触及极值区 → 推荐 **RSI 反弹**(`rsi_reversal`)。
  - 震荡市 + 价格贴近布林轨(高波动偏离)→ 推荐 **布林均值回归**(`boll_reversion`)。
  - 兜底:无强匹配 → 默认 `ma_cross`(最经典)+ 标注「无强匹配」。
- **输出**:`StrategyRecommendation {strategy_key, reason}`(reason 给可读依据,如「近 5 日趋势向上 + 均线多头排列 → 适合均线金叉策略」)。
- **零 LLM 成本**;LLM 推荐(additive 字段让 DeepSeek 选 + 给理由)留作后续增强,本版不做。

---

## 5. 只读信号 API + 前端

### 5.1 后端 API(只读 · 复用 `analysis.py` 路由)
- 挂在现有 [analysis.py](../../apps/api/app/api/v1/analysis.py)(已有本地 `DbDep` 等),**新增只读 GET 端点**(无鉴权,与 decision-card / ai-accuracy 一致):
  - **信号**:`GET /api/v1/analysis/strategy-signals?symbol=&market=&period=&instrument=&strategy=` → `{strategy, signals: [...], current_triggered, params}`。
  - **推荐**:`GET /api/v1/analysis/strategy-recommend?symbol=&market=&period=&instrument=` → `{recommended_strategy, reason}`。
  - **(拍板④已定)** **先拆两个端点**(`/strategy-signals` + `/strategy-recommend`,职责清晰,前端按需调),不合并。
- ★ **只读**:只 `select_kline` 读 CH 已采历史 K 线,**不打实时上游**;K 线不足时回源逻辑沿用 decision-card 既有模式(或直接返回「数据不足」让前端兜底)。
- **crypto instrument(拍板⑦已定)**:**跟随当前详情页**(crypto-preview 是 perp → 传 `instrument=perp`),与缠论一致。

### 5.2 前端
- **策略选择器**:3 选 1(`ma_cross` / `rsi_reversal` / `boll_reversion`),**默认选中 AI 推荐的那个**(调 recommend 端点)。
- **信号标注**:**复用 `midas-fractal` overlay**([klinecharts-extensions.ts](../../apps/web/lib/klinecharts-extensions.ts)),新增一个 `strategy-overlay.tsx`(结构照搬 [chan-overlay.tsx](../../apps/web/components/chart/chan-overlay.tsx) 第 4 层买卖点画法:`points:[{timestamp, value:price}]` + `extendData` + 买=朱红/卖=墨绿)。`groupId` 用独立 id(如 `midas-strategy-overlay`),与缠论 overlay 互不干扰、可独立开关。
- **当前触发提示**:复用 [strategy-checklist.tsx](../../apps/web/components/crypto-preview/strategy-checklist.tsx) 的「命中/未触发/待预热」徽章范式。
- **指标线对照**:用户可同时开 klinecharts 内置指标线(MA/BOLL/RSI,[indicator-panel.tsx](../../apps/web/components/workbench/indicator-panel.tsx))对照信号点。
- **VIRTUAL 徽章 + disclaimer**:策略信号是教育展示,带「仅供参考,不构成投资建议」+ 模拟语境;**「去下单」入口复用第一层一键下单**(不新增下单 UI)。

### 5.3 ★★ 前端必须覆盖 3 套主图入口(多页面验收铁律)
`ChanOverlay` 已统一接入的**三套主图**,形态A 信号 overlay **必须全部覆盖**:

| 入口 | 组件 | 服务市场 |
|---|---|---|
| 工作台 | [workbench/chart-area.tsx](../../apps/web/components/workbench/chart-area.tsx) | 通用(cn/us/crypto) |
| 现货详情页 | [spot-preview/spot-main-chart.tsx](../../apps/web/components/spot-preview/spot-main-chart.tsx) | cn / us |
| 合约详情页 | [crypto-preview/crypto-main-chart.tsx](../../apps/web/components/crypto-preview/crypto-main-chart.tsx) | crypto perp |

> ⚠️ **CLAUDE.md 协作铁律(AiDecisionCard vs CryptoAiCard 翻车教训)**:同一功能在不同页面可能是不同组件;上次 AI 一键下单只接了 workbench 的 `AiDecisionCard`、漏了 crypto-preview 的 `CryptoAiCard`,真机只验一个面就报「三市场跑通」。**形态A 信号标注必须 3 套主图都接入 + 3 套都真机验**(单元3 验收铁律,见 §8)。`ChanOverlay` 的 props override 设计([chan-overlay.tsx:37-49](../../apps/web/components/chart/chan-overlay.tsx))是现成范本(props 驱动详情页、store 驱动工作台)。

---

## 6. ★ 明确排除(不做 · 别评估)

| 排除项 | 原因 |
|---|---|
| **AI 生成可执行策略代码** + `safe_exec` 沙箱 | 0036 拍板④焊死 · 走预设模板,不执行 AI 代码 |
| **策略自动运行 / 自动下单 / 策略持仓管理** | 那是**形态B**,本 ADR 不做 · 形态A 看完走第一层 |
| **模拟撮合执行 / DSL 执行引擎** | 形态A 不执行策略,连 0036 §5 设想的 DSL 引擎都不需要 |
| **回测引擎**(QuantDinger ~4145 行)/ 绩效曲线(收益/夏普/回撤) | 形态A 只标信号点,不算绩效 · 回测 defer |
| **实盘队列 / 自研下单 REST / IBKR·MT5·Alpaca 券商 / Fernet 凭据** | 0036 §4 已焊死排除 · 真实交易,红线禁止 |
| **加密专属指标策略**(资金费/OI/大户多空比 · `StrategyChecklist` 那 4 条) | 形态A 走纯价格策略(四市场通用);加密专属那套是另一回事,不并入 |

---

## 7. 红线与零回归

### 7.1 虚拟 + 不下单焊死
- 形态A 全程**只读**(`select_kline` 读历史 K 线 + 纯计算),**不触发任何下单/撮合/写操作**。下单只能走第一层(已带二次确认 + VIRTUAL + disclaimer)。

### 7.2 现有功能零回归(三套证明)
1. **git diff 证不碰核心**:不改撮合引擎、不改 `workflow.py`/`technical.py`/decision-card 现有字段、不改第一层 `ai-order` 端点、不改批次乙 memory/reflection/accuracy。序列扫描器是**新增并行模块**;序列版指标数学**不动现有 `compute_*` 契约**(§3.2)。
2. **全量回归 pytest** + ruff/mypy:现有 AI 分析 / 缠论 / 第一层 / 批次乙测试全绿。
3. **四市场 + ★3 套主图真机抽查**:现有决策卡 / 缠论标注 / 行情 / 第一层一键下单不变;形态A 新标注在 3 套主图都正确显示(单元3)。

### 7.3 只读不打实时
- 信号扫描器**只读 `select_kline`**(CH 已采历史价),不打实时上游(同批次乙 reflection 纪律)。

---

## 8. 分单元开发计划(MVP = 前 3 单元)

| 单元 | 内容 | 依赖 | 风险 | 验收点 |
|---|---|---|---|---|
| **单元1 · 后端信号引擎** | 3 策略模板精确定义(§2)+ 序列信号扫描器(§3,复用指标数学序列化,**不改现有 `compute_*`**)+ `StrategySignal` schema + 单测 | 无 | **低**(纯新增计算) | 造 K 线(含已知金叉/超卖/触轨点)→ 扫描器返**正确信号序列**;ruff/mypy/pytest 绿 |
| **单元2 · 后端推荐 + API** | 纯规则推荐适配层(§4,类比 actionable.py)+ 只读 API(`/strategy-signals` + `/strategy-recommend`,§5.1) | 单元1 | **低**(只读端点) | 四市场 curl 返信号序列 + 推荐;数据不足兜底;现有 analysis 端点零回归 |
| **单元3 · 前端标注展示** | 策略选择器 + 信号 overlay(复用 midas-fractal)+ 当前触发提示 + VIRTUAL/disclaimer · **接入 workbench + spot-preview + crypto-preview 三套主图** | 单元2 | **中**(碰 3 套主图) | ★ **3 套详情页逐套真机**(零 mock):选策略→K 线标信号→看当前状态;cn/us/crypto 全覆盖;现有缠论 overlay / 决策卡零回归 |
| **单元4(随后增强)** | 策略历史信号喂批次乙 reflection → 算每策略命中率 → AI 按命中率推荐(数据驱动) | 单元1-3 + 批次乙 | **低**(复用批次乙基建) | `/ai-accuracy` 风格端点返策略命中率;推荐参考命中率 |

**MVP = 单元1 + 2 + 3**(前 3 单元上线即形态A 可用)。单元4 随后增强(拍板⑤)。

**单元间纪律**:
- 单元1 是地基(信号引擎),单测充分(每个策略的穿越判定造数据验)。
- 单元2 只读端点,职责清晰。
- ★ 单元3 是**多页面风险点**:3 套主图组件可能各自不同(workbench 用 store / 详情页用 props),**逐套接入 + 逐套真机验收**,不能只验一个面就报「四市场跑通」(§5.3 铁律)。
- 每单元走 feature 分支 + 自验闭环 + 验收点;红线贯穿(全程只读、不下单、不碰真实交易)。

---

## 拍板结论(2026-06-01 · 产品负责人已定)

| # | 议题 | ★ 拍板 |
|---|---|---|
| ① | **RSI 信号口径** | **反弹确认式**(RSI 上穿 30 = 买 / 下穿 70 = 卖)—— 采纳精确化,避免持续超卖连续标点噪音 |
| ② | **布林触轨判定基准** | **收盘价 `C` 穿越**(稳健,不被插针/影线误触发) |
| ③ | **信号 kind 语义** | **统一抽象「买/卖」**(不区分现货/合约,看完走第一层),不在形态A 重复 spot/perp 映射 |
| ④ | **API 形态** | **先拆两个端点**(`/strategy-signals` + `/strategy-recommend`) |
| ⑤ | **参数是否可调** | **MVP 固定默认**(MA5×20、RSI14·30/70、BOLL20·2σ),用户可调留后续 |
| ⑥ | **信号回看窗口** | **标全部可见历史信号点**(随图缩放) |
| ⑦ | **crypto 用 spot 还是 perp K 线** | **跟随详情页**(crypto-preview=perp → instrument=perp) |

---

## 红线小结(形态A 必守)
- **全程虚拟 · 不碰真实交易 · 不自动下单**:形态A 只读 + 展示,下单走第一层(已带确认+VIRTUAL+disclaimer)。
- **不执行策略 / 不撮合 / 不持仓**:展示型,形态B 才做执行(本 ADR 排除)。
- **避开沙箱/回测/实盘**:预设模板(非 AI 代码)+ 不回测 + 不接真实通道(0036 §4)。
- **只读不打实时**:信号扫描只读 `select_kline`(CH 已采历史)。
- **零回归**:现有 AI 分析/缠论/K 线/第一层/批次乙/四市场行为不变(§7,三套证明)。
- **★ 3 套主图全覆盖 + 全真机**:不重蹈「只接一个面」覆辙(§5.3)。

---

> 本 ADR 已 **Accepted**(2026-06-01)。产品负责人审过(★展示型边界 + 排除自动交易/沙箱 + 3 套主图覆盖 + 零回归)+ 拍板 7 个细节(见 §拍板结论)。按 §8 分单元开工(MVP = 前 3 单元),**单元1 = 后端序列信号引擎先行**。本轮只出设计,不含实现代码。
