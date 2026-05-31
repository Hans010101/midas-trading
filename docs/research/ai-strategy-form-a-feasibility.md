# 调研 · AI 模拟交易第二层【形态A:AI 推荐策略模板 + 模拟信号展示】可行性

> 性质:**纯调研评估,不写代码**。供产品负责人判断 + 出 ADR(第二层·形态A),再分单元开工。
> 日期:2026-05-31 · 调研基线:当前 main HEAD(批次乙自学习闭环刚合并上线)。
> A 部分代码结论**均直接读源码核实**,带 `file:line` 锚点。B 部分基于已有调研
> [ai-simulated-trading-feasibility.md](ai-simulated-trading-feasibility.md) 的 QuantDinger 拆解(源码不在本仓库)。
> 上游设计依据:[ADR 0036](../decisions/0036-ai-simulated-trading.md) §5(第二层)+ §4(明确排除清单)。

---

## 0. 形态A 定位(产品负责人锁定 · 本调研的边界)

- **平台预设几个经典策略模板**(均线金叉 / RSI 超卖反弹 / 布林带突破)。
- **AI 推荐**「这个标的现在适合用哪个策略」。
- 用户选中 → K 线上看该策略的**历史买卖点信号标注** + **当前是否触发**。
- ★ 本质 **展示型 / 指导型**:AI 选策略 + 把信号画给用户看,**不自动交易**;用户看完仍走**第一层「一键模拟下单」**(不新建自动交易机制)。
- ★ 核心价值:用户**看得懂、学得到**的策略指导。

**明确不做(本形态边界)**:
- ❌ AI 生成可执行代码(ADR 0036 拍板④ · 避开 `safe_exec` 沙箱)。
- ❌ 策略自动运行 / 自动下单 / 策略持仓管理(那是形态B,先不做)。
- ❌ 真实交易 / QuantDinger 实盘部分。

> ★ 关键认知:形态A **比 ADR 0036 §5 原设想的「参数化 DSL + 复用 U0 下单通道模拟跑」还要轻** —— 它**不执行策略、不下单、不跑模拟撮合**,只「算信号 + 画信号 + AI 选策略」。下单完全甩给已上线的第一层。这把工作量和风险都进一步压低。

---

## TL;DR(重点四问)

**① 现有复用度 ≈ 65–70%**(比第一层略低,因有一个真缺口):
- **极高复用**:K 线图(klinecharts 100%)、**信号标注 overlay 机制**(`midas-fractal` · 策略买卖点与缠论买卖点**完全同构**)、指标线(klinecharts 内置 MA/BOLL/MACD/RSI)、K 线读取(`select_kline`)、AI 管线(decision-card)、二次确认/VIRTUAL 徽章/disclaimer、**展示型策略 UI 先例**(`StrategyChecklist`)。
- **唯一真缺口**:现有指标全是**「最新快照值 / 当前是否命中」**,**没有任何地方算「历史信号点序列」**(何时金叉 / 何时超卖)。形态A 要在 K 线标历史买卖点 → 需新增**「序列级信号扫描器」**(数学基础 `indicators.py` 可复用,改成吐序列 + 找穿越点)。

**② 形态A 该新建什么**:序列级信号扫描器(真缺口)+ 3-4 个策略模板定义 + AI/规则「推荐选哪个策略」适配层 + 一个只读信号 API + 前端「策略选择器 + 信号 overlay(复用 midas-fractal)+ 当前触发提示」。

**③ 策略模板选哪几个**:先 **3 个经典、纯价格、四市场通用**的——**均线金叉/死叉**(MA5×MA20)、**RSI 超卖反弹/超买回落**(RSI14 <30/>70)、**布林带突破/回归**(close × 上下轨)。覆盖「趋势 / 反转 / 波动」三范式,只用 OHLCV,与现有指标线天然呼应。可选第 4 个 **MACD 金叉**(DIF×DEA,指标已算)。

**④ QuantDinger 可借鉴的纯信号逻辑**(排除回测/实盘/沙箱):真正可借鉴的是**声明式策略规则思路**(轻量,不需 DSL 引擎)+ **自学习闭环验证信号质量**(批次乙已落地,可复用算每个策略的历史命中率)。**经典模板本身是业界标准公式,不依赖 QuantDinger,自实现即可**(每策略几十行纯 Python)。回测引擎/沙箱/实盘队列/券商**全排除**(ADR 0036 §4 已焊死)。

---

# A. 现有系统能复用多少(代码侧 · 已核实)

## A1. 指标计算:均线/RSI/MACD/布林,现在算了吗?在哪算?

**算了,但全是「快照值 / 当前命中」,不是「历史信号序列」。** 三处:

| 位置 | 算什么 | 形态 | `file:line` |
|---|---|---|---|
| 后端 AI 指标 | MA(5/20/60)、MACD(12,26,9)、RSI(14)、BOLL(20,2)、trend_5d | **纯 Python 无 TA-lib**,**只返回最新 1 个值** | [indicators.py](../../apps/api/app/services/ai/indicators.py) `compute_ma:48` / `compute_macd:58` / `compute_rsi:87` / `compute_boll:117` |
| 后端告警 fetcher | MA5/20/60、MACD 柱、RSI14、布林 %B | 封装「取 K 线→算指标」返**单值**(告警阈值用) | [alerts/registry.py:107-130](../../apps/api/app/services/alerts/registry.py)(`_ma_fetcher`/`_f_macd_hist`/`_f_rsi_14`/`_f_boll_pctb`) |
| 前端指标线 | MA/BOLL(主图叠加)+ MACD/RSI(副图) | klinecharts **内置指标** createIndicator,前端算 | [kline-chart.tsx:184-187](../../apps/web/components/chart/kline-chart.tsx) + [indicator-panel.tsx:11-16](../../apps/web/components/workbench/indicator-panel.tsx) |

★ **关键缺口**:`compute_macd` 内部 `_ema_series`(indicators.py:65)其实**算了整段 EMA 序列**,但函数只 `return` 尾值(line 81-84);`compute_rsi` 也遍历全段但只吐最新 RSI。**「整段序列上找金叉/超卖/突破的那些时间点」现在没有任何地方做。** 形态A 标历史买卖点 = 必须新增这一层(数学可直接复用 `_ema/_sma/_stdev` + RSI 遍历,改成吐序列 + 找穿越/触发点)。

## A2. 现有 AI 能不能产出「推荐用哪个策略」?

**不能,需加适配(但很便宜)。** 现状:
- LangGraph 6 节点 + **单技术面 Agent**([workflow.py](../../apps/api/app/services/ai/workflow.py)),输出 `DecisionCardResponse`(label/score/confidence/key_levels/chan_signals/narrative)。
- 技术面 agent 的 system prompt 已把 **MA/MACD/RSI/BOLL + 缠论摘要**喂给 LLM,但只让它输出 score/confidence/rationale/key_levels —— [technical.py:25-49](../../apps/api/app/services/ai/agents/technical.py),prompt 按市场分叉(cn/us/crypto,**无 hk**)。
- ★ **没有「推荐用哪个策略」这种输出。** 两条加法(都不改现有管线):
  - **(推荐)纯规则推荐**:看当前指标状态(`trend_5d` + MA 排列 + RSI 值 + 布林位置)确定性匹配最适配的策略模板。类比已上线的 [actionable.py](../../apps/api/app/services/ai/actionable.py)(`composite_label → ActionableAdvice` 纯函数确定性映射)。**零 LLM 成本、可单测、四市场统一。**
  - **(进阶可选)LLM 推荐**:扩展 technical prompt 加 additive `recommended_strategy` 字段让 DeepSeek 选 + 给理由。复用现有真实 LLM 管线(生产已 `llm_mode=real`),但第一版规则推荐够用且更可控。

## A3. ★ 缠论买卖点怎么在 K 线上标注/渲染?策略信号能复用吗?

**能,而且是【完全同构】—— 这是形态A 复用度最高的一块。**

机制(已读源码):
1. **自定义 overlay 注册** [klinecharts-extensions.ts](../../apps/web/lib/klinecharts-extensions.ts):`midas-fractal`(line 52-88)= 干净文字标记,吃 `{timestamp, value}` + `extendData`(任意字符串),按首字母决定颜色偏移。`midas-rect`(line 25-50)= 矩形(中枢用)。
2. **数据→overlay** [chan-overlay.tsx](../../apps/web/components/chart/chan-overlay.tsx):从 `useChan` 拿 `{zhongshus/bis/fractals/buy_sell_points}` → 转 overlay 数组 → `chart.createOverlay()`。**缠论买卖点 B1/B2/B3/S1/S2/S3**(line 187-216)就是用 `midas-fractal` 画的:`points:[{timestamp, value:price}]` + `extendData: kind` + 颜色(买=朱红 / 卖=墨绿)。
3. `groupId` 统一管理(line 51),clear + recreate 幂等(line 97-102)。

★ **策略买卖信号 = 缠论买卖点的同构物**:都是「**某时间点 + 某价格 + 一个买/卖标签**」。形态A 只需后端产出 `[{ts, price, kind: buy/sell, reason}]`,前端**复用同一套 `midas-fractal` overlay**(新增一个 `strategy-overlay.tsx` 兄弟组件,或给现有组件加一类标记)即可画上去。**几乎零新机制。**

## A4. 形态A 需要新建什么 / 复用什么 / 复用度

| | 模块 | 复用 / 新建 | 说明 |
|---|---|---|---|
| 复用 | K 线图 + klinecharts | **100%** | 三套主图都在用(见 A5) |
| 复用 | **信号标注 overlay**(`midas-fractal`) | **~95%** | 仅新增一个组件壳,机制现成 |
| 复用 | 指标线(MA/BOLL/MACD/RSI) | **100%** | klinecharts 内置 createIndicator |
| 复用 | K 线读取 `select_kline` | **100%** | market-keyed,四市场统一 |
| 复用 | 指标数学(`_ema/_sma/_stdev`+RSI 遍历) | **~70%** | 要从「吐尾值」改成「吐序列 + 找穿越点」 |
| 复用 | AI 管线(decision-card / 缓存) | **~80%** | 推荐层挂在旁边 |
| 复用 | 二次确认 / VIRTUAL 徽章 / disclaimer | **100%** | 看完走第一层一键下单,全现成 |
| 复用 | 展示型策略 UI 范式 | **~60%** | `StrategyChecklist` 是先例(见 A5) |
| **新建** | **① 序列级信号扫描器** | **真缺口** | 对每根 K 线判断金叉/超卖/突破 → 产信号点序列 |
| **新建** | ② 策略模板定义(参数化) | 小 | 均线金叉 = MA_fast 上穿 MA_slow 等,声明式 |
| **新建** | ③ AI/规则「推荐选哪个策略」适配层 | 小 | 类比 actionable.py 纯函数(A2) |
| **新建** | ④ 只读信号 API 端点 | 小 | `GET /analysis/strategy-signals` |
| **新建** | ⑤ 前端策略选择器 + 信号 overlay + 当前触发提示 | 中 | 复用 midas-fractal + 覆盖 3 套主图 |

**复用度粗估 ~65–70%**(第一层是 ~70–75%;形态A 略低只因多了「序列信号扫描」这个真缺口;标注/图表/指标数学/AI/确认全现成)。

## A5. ★ 四市场(cn/us/crypto)策略信号 + AI 推荐能否统一?

**能统一,而且统一面已经铺好。**

**已存在的统一资产**(都市场无关):
- 一个 `Market` 字面量([schemas/market.py:15](../../apps/api/app/schemas/market.py))全栈穿。
- 一个统一 K 线读法 `select_kline(symbol, market, period, ...)`。
- 指标数学(indicators.py)纯 OHLCV 计算,**与市场无关**。
- 信号标注 overlay(midas-fractal)**只吃 `timestamp + value`,市场无关**。
- **经典价格策略(均线/RSI/布林)只用 OHLCV → cn/us/crypto 天然通用。**

**★ 前端三套主图入口(信号标注已统一接入,形态A 必须全覆盖)**:
| 入口 | 组件 | 服务市场 |
|---|---|---|
| 工作台 | [workbench/chart-area.tsx](../../apps/web/components/workbench/chart-area.tsx) | 通用(cn/us/crypto) |
| 现货详情页 | [spot-preview/spot-main-chart.tsx](../../apps/web/components/spot-preview/spot-main-chart.tsx) | cn / us |
| 合约详情页 | [crypto-preview/crypto-main-chart.tsx](../../apps/web/components/crypto-preview/crypto-main-chart.tsx) | crypto perp |

> ⚠️ **多页面验收铁律**(CLAUDE.md · AiDecisionCard vs CryptoAiCard 翻车教训):形态A 前端**必须覆盖这 3 套主图入口**,不能只接一个就报「四市场跑通」。ChanOverlay 当年就是同时接了这三套(props override 设计,见 chan-overlay.tsx:37-49)——形态A 信号 overlay 照此覆盖。

**两个不统一点(要诚实处理)**:
- **`StrategyChecklist` 现有 4 条规则是 crypto 专属**(用 funding/OI/大户多空比/强平距离 —— 见 [strategy-checklist.tsx:73-117](../../apps/web/components/crypto-preview/strategy-checklist.tsx)),**不能跨市场**。但形态A 的经典价格策略(均线/RSI/布林)是纯价格,**与那套是两回事**,天然四市场通用。
- **AI 推荐若走 LLM**:technical prompt 无 hk 键(technical.py:44-49);但形态A 若走**规则推荐**(A2 建议),不依赖 LLM prompt,四市场统一无障碍。ADR 0036 拍板②第一层 cn/us/crypto,**形态A 跟随**(hk 等港股阶段三)。

---

# B. QuantDinger 哪些【纯信号/指标价值·和实盘无关】可借鉴

> QuantDinger 源码不在本仓库,基于《技术拆解文档》v3.0.18(见 [ai-simulated-trading-feasibility.md §B](ai-simulated-trading-feasibility.md))。

## B1. IndicatorStrategy / 向量化信号那套——能借鉴吗?

- QuantDinger 的 `fast_analysis.py` 是**多周期 objective_score + 客观共识打分**(批次乙 §3.2 多周期共识已规划借鉴),那是「打分」不是「经典策略信号」。
- 它的 **no-code `StrategyCompiler`(JSON 声明式规则)** 才是与形态A 相关的:**「声明式策略规则」思路**值得借鉴 —— 把策略写成参数化规则(`{indicator, op, threshold}`)而非硬编码。
- ★ 但形态A **更轻,不需要 DSL 引擎**:3-4 个模板硬编码成参数化函数即可(`golden_cross(fast=5, slow=20)`),不必做通用规则编译器。借鉴的是**「策略 = 声明式参数 + 信号扫描」的形态**,不是它的实现。

## B2. ★ 明确排除(不评估 · ADR 0036 §4 已焊死)

| 排除项 | 规模 | 为什么 |
|---|---|---|
| 回测引擎 | ~4145 行 | 形态A 不回测(只标历史信号点,不算收益曲线/夏普)。回测另见 [strategy-backtesting-feasibility.md](strategy-backtesting-feasibility.md),且 CLAUDE.md 标 defer |
| `safe_exec` 沙箱 | ~618 行 | 拍板④走预设模板,不执行 AI 生成代码 → 整块避开 |
| 两段式实盘队列 | — | 接真实交易所,红线禁止 |
| 自研下单 REST / IBKR/MT5/Alpaca 券商 | — | 真实下单 |
| Fernet 凭据加密 | — | 永不存交易所 key |

★ 形态A **连「策略执行/模拟撮合」都不做**(看完走第一层),所以比 ADR 0036 §5 设想的还少碰一层 —— DSL 执行引擎也不需要。

## B3. 经典策略模板的标准实现——有现成可借鉴的纯计算逻辑吗?

**有,但是业界标准公式,不依赖 QuantDinger**(通用知识 + 现有 indicators.py 数学):

| 策略 | 标准信号定义 | 复用现有数学 |
|---|---|---|
| **均线金叉/死叉** | MA_fast 上穿 MA_slow → buy;下穿 → sell(如 MA5×MA20) | `_sma`(indicators.py:29)逐根算两条 MA,找穿越 |
| **RSI 超卖反弹/超买回落** | RSI(14) 上穿 30 → buy;下穿 70 → sell | `compute_rsi` 的 Wilder 遍历(indicators.py:87)改成吐序列 |
| **布林带突破/回归** | close 上穿上轨 → 突破买(或下穿下轨→均值回归买,口径二选一) | `_sma`+`_stdev`(indicators.py:29/36)逐根算轨道 |
| **MACD 金叉(可选)** | DIF 上穿 DEA → buy;下穿 → sell | `_ema_series`(indicators.py:65)已算整段,取穿越点 |

★ 每个策略 = 几十行纯 Python(逐根算指标 + 找穿越点 + 产 `{ts, price, kind, reason}`)。**真正要借鉴 QuantDinger 的不是这些公式,而是它的「自学习闭环验证信号质量」** —— 而那个**批次乙已经落地了**(`ai_analysis_memory` + reflection + ai-accuracy),形态A 可直接复用来算「每个策略在该标的的历史命中率」(见 C3 协同)。

---

# C. 形态A 实现评估

## C1. 策略模板建议(先做哪几个)

**先做 3 个**(覆盖三大范式,纯价格,四市场通用,与现有指标线呼应):

1. **均线金叉/死叉**(MA5 × MA20)—— 趋势跟踪 · 最经典 · 用户开 MA 指标线即可对照看信号点。
2. **RSI 超卖反弹/超买回落**(RSI14,30/70 阈值)—— 震荡反转 · 副图 RSI 线对照。
3. **布林带突破/回归**(BOLL 20,2σ)—— 波动率 · 主图布林带对照。

**可选第 4 个**:MACD 金叉(DIF×DEA)—— 指标已全算,加成本低。

> 建议参数**可调但给默认**(MA 快慢线、RSI 阈值、布林倍数),默认值与现有 indicator-panel 一致,降低认知负担。布林策略的「突破 vs 均值回归」口径要产品拍板(两种相反语义)。

## C2. 信号计算放哪 + 标注展示

- ★ **后端算**(强烈建议)。理由:
  1. 序列扫描要遍历几百根 K 线找穿越点 —— 后端一次算好返信号序列,前端只渲染。
  2. **与缠论一致**:缠论也是后端算 `chan_signals`、前端 overlay(A3),形态A 照此对齐,架构一致。
  3. 四市场统一在后端一处。
  4. ★ **可单测 + 可喂批次乙 reflection**(算策略历史命中率)。
  - 反例:`StrategyChecklist` 是**前端算**,但它只判「当前单点是否命中」(strategy-checklist.tsx:73),**不扫历史序列** —— 形态A 要历史信号点,前端算不合适。
- **标注**:**复用 `midas-fractal` overlay**(A3),数据格式同缠论买卖点 `[{ts, price, kind, reason}]`。
- **指标线**:复用 klinecharts 内置 createIndicator(用户可同时开 MA 线 + 看金叉点对照)。
- **当前是否触发**:信号序列最后一根的状态 = 当前是否触发(顺带复用 `StrategyChecklist` 那种「命中/未触发/待预热」徽章范式)。

## C3. AI 推荐策略的逻辑

- 形态A「AI 推荐用哪个策略」= 给定当前行情,选最适配的模板。
- **第一版:纯规则推荐**(确定性,类比 actionable.py)。映射示意(待拍板细化):
  - `trend_5d=up` + MA 多头排列 → 优先**均线金叉**(趋势市)。
  - 震荡(trend sideways)+ RSI 触及极值 → 优先 **RSI 反弹**。
  - 布林带张口/收口(波动率变化)→ 优先**布林突破**。
  - 零 LLM 成本、可单测、四市场统一。
- **进阶(可选)**:扩展 technical prompt 加 additive `recommended_strategy`(LLM 选 + 理由),复用真实 DeepSeek 管线。
- ★ **与批次乙天然协同**:批次乙已上线 `ai_analysis_memory` + reflection + `/ai-accuracy`。形态A 可把**每个策略的历史信号**也喂 reflection 验证 → 算「该策略在该标的的历史命中率」→ **AI 按命中率推荐**(数据驱动,而非纯规则)。这是形态A 的增值方向,也兑现「看得懂、学得到 + 可验证」。

## C4. 工作量评估(形态A 较轻)

**粗估 ≈ 2 个中等 Checkpoint**(展示型,不碰下单/不自动跑,主体是适配 + 复用):
- 后端 ≈ 1 Checkpoint:序列信号扫描器(3-4 模板)+ 规则推荐适配 + 只读信号 API + 单测。
- 前端 ≈ 1 Checkpoint:策略选择器 + 信号 overlay(复用 midas-fractal)+ 当前触发提示 + **3 套主图入口接入** + VIRTUAL/disclaimer + 四市场真机抽查。

比第一层略重(多了序列信号扫描这个真缺口),但**比回测引擎/沙箱轻一个量级**(那些全排除)。CLAUDE.md「不早期堆功能」对形态A 压力小 —— 它是已上线 AI 分析 + K 线标注的自然延伸,不引入新机制族。

## C5. ★ 分单元建议(能独立验收的粒度)

| 单元 | 内容 | 独立验收点 | 红线 |
|---|---|---|---|
| **单元1 · 后端信号引擎** | 策略模板定义(参数化)+ 序列信号扫描器(复用 indicators 数学,产 `[{ts,price,kind,reason}]`)+ 单测 | 造 K 线(含已知金叉/超卖点)→ 扫描器返正确信号序列;ruff/mypy/pytest | 纯计算 · 不碰下单 |
| **单元2 · 后端推荐+API** | `GET /api/v1/analysis/strategy-signals`(symbol/market/period/strategy)+ 规则推荐「选哪个策略」 | 四市场 curl 返信号序列 + 推荐;空数据兜底 | 只读 · 不打实时(读 CH/select_kline) |
| **单元3 · 前端标注展示** | 策略选择器 + 复用 midas-fractal 画信号点 + 当前触发提示 + VIRTUAL/disclaimer · **接入 workbench + spot-preview + crypto-preview 三套主图** | ★ **3 套详情页真机**:选策略→K 线标信号→看当前状态;四市场零 mock | 只读提示 · 绝不自动下单 |
| **单元4(可选·协同批次乙)** | 策略历史信号喂 reflection → 算每策略命中率 → AI 按命中率推荐 | `/ai-accuracy` 风格端点返策略命中率 | 只读统计 · 复用批次乙基建 |

**建议顺序**:单元1(地基)→ 单元2(API)→ 单元3(前端 · ★多页面全覆盖)→ 单元4(可选增值)。前三个单元即构成形态A MVP。

---

# D. 红线复核 + 待产品负责人拍板

**红线复核(形态A 全程守住)**:
- ✅ **不自动交易 / 不自动下单**:形态A 只算信号 + 画信号 + 推荐,**看完走第一层一键下单**(第一层已带二次确认 + VIRTUAL + disclaimer)。
- ✅ **不碰真实交易**:纯展示,连虚拟撮合都不触发(下单甩第一层)。
- ✅ **不改 analyze 主流程**:推荐适配层挂在 decision-card 旁边(类比 actionable.py / 批次乙 memory 旁路),不动 workflow。
- ✅ **只读不打实时**:信号扫描读 CH 已采 K 线(`select_kline`),不打实时上游。
- ✅ **避开沙箱/回测/实盘**:预设模板(非 AI 生成代码)+ 不回测 + 不接真实通道。
- ✅ **disclaimer + VIRTUAL**:信号是「历史这样标 / 当前是否触发」的教育展示,带「仅供参考,不构成投资建议」。

**待拍板点**:
1. **策略模板范围**:先 3 个(均线金叉/RSI/布林)还是含 MACD 金叉第 4 个?
2. **布林策略口径**:**突破**(顺势:破上轨买)还是**均值回归**(逆势:破下轨买)?两种相反语义,需定。
3. **AI 推荐**:第一版**纯规则推荐**(建议,零成本可测)还是直接上 **LLM 推荐**(additive 字段)?
4. **是否纳入「策略历史命中率」(单元4)**:与批次乙协同,数据驱动推荐 —— 形态A MVP 含还是后置?
5. **前端展示位置**:策略信号是 K 线主图 overlay(建议,与缠论一致)+ 选择器放哪(详情页右栏 / 工具栏)?
6. **市场范围**:cn/us/crypto(跟随 ADR 0036 拍板②),hk 等阶段三?(建议:跟随)

---

> 本调研回答「现有复用多少(查准)+ 形态A 新建什么 + 策略模板选型 + QuantDinger 纯信号可借鉴(排除回测/实盘/沙箱)」。A 部分代码结论已读源码核实(带 file:line);B 部分基于既有 QuantDinger 拆解。产品负责人据此判断 + 出 ADR(第二层·形态A)后,按 C5 分单元开工。**核心结论:形态A 是已上线 AI 分析 + K 线标注的轻量自然延伸,唯一真缺口是「序列级信号扫描」,标注/图表/指标/AI/确认全现成;四市场天然统一,但前端必须覆盖 3 套主图入口。**
