# 调研 · AI 模拟交易模块 —— 现有复用度 + QuantDinger 可借鉴纯 AI 设计 + 合并开发边界

> 性质:**纯调研评估,不写代码**。供产品负责人判断 + 出 ADR,再分(尽量合并的)阶段开工。
> 日期:2026-05-31 · 调研基线:当前 main HEAD。
> 定位(产品负责人已确认):在现有「AI 分析 + 虚拟交易」之上,让 AI 更深度参与交易动作,给用户**可借鉴、有指导价值**的 AI 交易能力。三层渐进:① AI 建议→一键模拟下单 ② AI 策略模拟参考 ③ AI 自动模拟托管(远期)。
> ★ 核心红线(地基):**全程虚拟账户、绝不接真实交易通道**。守住地基即可,合规层面不过度收紧。现有所有交易功能完整保留,这是【新增】模块。
> 调研方法:本文 A 部分的代码结论**均直接读源码核实**(关键两处 `DecisionCardResponse` schema + `bot/order.py::execute` 已亲自二次校验);B 部分基于用户上传的《QuantDinger 技术拆解文档》(v3.0.18,Apache 2.0 后端)。

---

## 0. 结论速览(TL;DR · 产品负责人最关心的三件事)

### ① 现有复用度 —— 第一层能多快做:**很快,底座几乎全现成**
- **下单侧 ~70–75% 复用,撮合引擎零改动**。三个下单入口(现货 `place_market_order`、永续 `route_open_perp/route_close_perp`)都是**纯 service 函数**,不依赖 HTTP;而且**已经有一个跑通的非 HTTP 内部下单通道**——Telegram bot 的 `bot/order.py::execute(db, ch, user_id, intent)`,AI 模块照搬这个缝即可。
- **AI 管线侧也几乎全现成**:真实 DeepSeek(LiteLLM)+ LangGraph + 缠论输入 + Redis 缓存 + 决策卡/信号条/买卖点 overlay 前端,全部可复用。
- **唯一的真缺口**:现有 AI 输出是「分析观点」(评分 + 强多/弱多/中性/弱空/强空 + 关键价位 + 缠论买卖点),**没有 direction/仓位/进出场价这些"可下单字段"**。补这层「信号→下单意图」适配器,就是第一层的核心新增工作(其余全复用)。
- 第一层粗估:**≈ 一个中等 Checkpoint(3–5 个 sub-task)**,量级类似过去的 MC-4 / G4。

### ② QuantDinger 可借鉴的纯 AI 设计(已排除实盘部分)
- ★★★ **AI 自学习闭环**(analysis_memory 历史形态 + reflection 真实价格回填验证 + calibration 阈值自调优)—— **最契合产品"可借鉴、有指导价值"定位,且全程不碰实盘**。把"AI 历史命中率"亮给用户,是巨大的信任 builder。复杂度中等,且**全部复用我们已有的 Celery + `select_kline` 基建**。
- ★★ **多周期客观共识打分 + 置信度校准**(fast_analysis 的 objective_score 多周期加权 + 强共识覆盖 LLM + 质量过低强制 HOLD)—— 让 AI 输出更稳健、confidence 有客观锚。纯后端增强,不碰下单。
- ★ **ensemble 多模型投票** —— 提升鲁棒性但翻倍 LLM 成本,做成可选开关即可。
- 🚫 **明确排除(为真实下单/券商服务,本调研不评估)**:两段式队列下单的"真实交易所"部分、自研下单 REST client、IBKR/MT5/Alpaca 券商集成、Fernet 凭据加密、Agent Gateway 的 live 实盘三重闸门、USDT 链上支付/计费。

### ③ 合并开发边界建议(尽量合并、边界清晰、各自可验收)
- **共享底座 U0**(下单通道复用 + actionable schema 扩展 + 来源标记)= 第一层和第二层都要用,**一次做好**。
- **批次甲 = U0 + 第一层**(紧耦合,合并开发一起验收)。
- **批次乙 = AI 能力增强(多周期共识 + 自学习闭环)**,与下单**完全解耦**,可**并行甚至先行**;最契合"可借鉴有指导价值 + 零实盘风险",建议优先级高。
- **批次丙 = 第二层(AI 策略)**,依赖 U0,排在第一层之后。
- 详见 §C2 的开发单元划分表。

---

## A. 现有系统能复用多少(代码侧 · 已核实)

### A1. 现有 AI 分析能力到什么程度?

**架构**(`apps/api/app/services/ai/`):LangGraph **6 节点线性图**,**单技术面 Agent**(非多 Agent)。
`entry → data_prepare → technical_agent → decision_card → validator → exit`(`workflow.py`)。
> ADR 0012 原计划 4 个并行 Agent(技术/基本面/新闻/价值)+ Aggregator 加权,M1「二波降级 v2」**砍成只跑技术面 Agent**;`agent_scores` 长度恒 1,`composite_score = technical_score` 直通,`contradiction` 永远 None。4-Agent 留作 M2+ 升级(schema 不变、前端 conditional render)。

**LLM 是真的、不是 stub**:`llm.py` 调 `litellm.acompletion(model="deepseek/deepseek-chat", response_format={"type":"json_object"})`。0012 ADR 有三市场真实 DeepSeek 验收记录(BTC/NVDA/600519,真实 token 数 + 中文解读,~¥0.0007/call)。
> ⚠️ 诚实标注一处**待实测**:`DecisionCardResponse.llm_mode` 默认值是 `"mock"`,真实/mock 取决于运行环境的 `DEEPSEEK_API_KEY` 是否配置(空 key 优雅降级到 mock,UI 不崩)。本地 `.env` 已配真 key、`LLM_MOCK_MODE=false`,代码路径是真实的;**生产当前跑真还是 mock,需上线时抽查 `llm_mode` 字段确认**(CLAUDE.md 待用环境变量表里 `DEEPSEEK_API_KEY` 标的是"Task 3+ AI Agent 阶段")。这不影响可行性结论(管线是真的,不是占位)。

**现在输出什么**(`schemas/ai_decision.py` `DecisionCardResponse`,已亲自核实全字段):

| 字段 | 类型 | 是否"可下单" |
|---|---|---|
| `composite_score` | `int` (-100..100) | 方向强度(可映射) |
| `composite_label` | `强多/弱多/中性/弱空/强空` | **方向倾向**(可映射成 buy/hold/sell) |
| `composite_confidence` | `float` (0..1) | 置信度 |
| `agent_scores[].key_levels` | `list[float]`(≤4) | LLM 给的 [支撑, 阻力](未对当前价校验) |
| `chan_signals[]` | `{ts, price, kind: B1..S3, description}` | 缠论买卖点 + 价格(规则引擎算的,非 LLM) |
| `narrative` | `str`(≤1000) | 散文解读(过 validator 改写、**剥离祈使句**) |
| `disclaimer` | `str` | 默认"仅供参考,不构成投资建议" |

★ **关键结论**:输出是**分析观点**(方向 + 评分 + 关键价位 + 缠论点),**不是下单工单**。已 grep 确认:schema 里**没有** `direction`(buy/sell/hold)、`side`、`suggested_position_pct`/仓位、`entry`/`target`/`stop` 任何"可直接下单"字段。这是**当初有意为之**(0012 红线 + `validator.py` 主动把"建议买入"改写成"分析显示买入信号",合规去 actionable)。

**暴露**:`GET /api/v1/analysis/decision-card`(query: symbol/market/period)。前端已有 `ai-decision-card.tsx`(右栏卡)+ `signal-bar.tsx`(顶部信号条)+ `chan-overlay.tsx`(K 线买卖点标注),共享同一 query/缓存。

**缓存**:Redis,key 按 `市场:标的:周期:交易日`(非 per-user),命中 35× 提速。**市场覆盖**:cn/us/crypto 可分析;**hk 会 KeyError**(无 hk 系统提示词、无 hk 数据)。**缠论**:既喂进 AI(缠论结构摘要进 prompt),又作为独立 overlay。

> **A1 小结 → 第一层最大缺口**:AI 产不出 direction + 仓位。但补这层很便宜——`direction` 可**确定性**从 `composite_label` 推导(强多/弱多→buy、中性→hold、弱空/强空→sell);仓位走预设/置信度规则;进出场价可选(从 `key_levels` + 缠论点派生)。**不需要改 AI 管线,纯加一个 additive 子 schema + 一个映射函数。**

### A2. 虚拟引擎能否接收"AI 信号"来下单?

★ **能,完全能,撮合引擎零改动。** 已核实:

- **三个下单入口都是纯 service 函数**,签名 `(db: AsyncSession, req/...params, user_id: UUID, fetcher)`,**零 FastAPI / `Request` / `Depends` / `get_current_user` 依赖**:
  - 现货 `services/virtual_trading/engine.py::place_market_order(db, PlaceOrderRequest(user_id,symbol,market,side,quantity,position_side), get_market_price)`
  - 永续 `services/virtual_trading/perp_dispatcher.py::route_open_perp(db, *, user_id, symbol, side, leverage, margin|quantity, preferred_mode, get_mark_price)` / `route_close_perp(...)`
  - 引擎自己**不 commit**(调用方持有事务边界),业务拒绝返回 `status=rejected` 的订单对象而**不抛异常**。

- ★ **已有跑通的非 HTTP 内部下单通道**(本调研最重要的发现,已亲自读 `bot/order.py` 二次核实):
  ```python
  # apps/api/app/services/bot/order.py:342
  async def execute(db: AsyncSession, ch: ClickHouseClient, user_id: UUID, intent: OrderIntent) -> OrderResult:
      """user_id 必须由调用方从已验证 chat 解析后传入(红线 R1)。"""
      if intent.market == "crypto": return await _exec_perp(db, ch, user_id, intent)   # → perp_dispatcher
      return await _exec_spot(db, ch, user_id, intent)                                  # → place_market_order
  ```
  它**复用同一套引擎**(import 与 HTTP 路由一模一样),并在引擎之上补齐了"程序化下单"需要的一切:方向→`(side, position_side, quantity)` 解析、**从预设算仓位**(`load_preset`:perp 默认 100 USDT@3x、现货 10000 CNY / 1000 USD)、symbol 规范化、报价、"平仓=平整个活仓"、**预览不落库**(`build_preview`,天然适合确认步)。`db` 是一路传下来的**普通 `AsyncSession`**,不是 FastAPI 依赖——**Celery 任务或别的 service 自取一个 session 就能直接调它**。
  > bot 的限流 + 两步确认在 `bot/router.py`(渠道 UX),**不在 `order.py`**——所以 `order.py` 是干净可复用的程序化内核。

- **钱包**:`(user_id, market)` 唯一一行 `VirtualAccount`,**服务端从 user_id + market 推导,无需 wallet_id**;懒创建即激活(无行=未激活,引擎自动拒)。所有 perp 硬走 crypto USDT 钱包。
- **无现成"入站信号"抽象**:只有**出站**通知事件(`TradeFilledEvent` / `PerpFilledEvent` / `PriceAnomalyEvent`…,成交后才发),它们带的是*结果*不是*下单意图*。AI 决策卡是只读的,**今天没有任何东西把 label/score 转成 OrderIntent**——这正是要新建的那一小块。

### A3. 第一层"AI 建议→一键模拟下单":新建什么 / 复用什么 / 复用度

| | 内容 | 复用 or 新建 |
|---|---|---|
| 撮合/持仓/PnL/equity/强平核心 | `engine.py` `perp_engine.py` `perp_cross_engine.py` `perp_dispatcher.py` `fees.py` `equity.py` | **复用(零改动)** |
| 钱包/持仓/订单模型 | `models/virtual.py` `models/perp.py` | **复用** |
| 程序化下单内核(方向解析+仓位+报价+预览) | `bot/order.py::execute` | **复用**(或抽成渠道中立的 `place_order_intent`) |
| AI 管线(LLM/缠论/缓存/卡片 UI) | `services/ai/*` + 前端三组件 | **复用** |
| 价格 fetcher 基建 | `ch.select_kline` / `make_price_fetcher` | **复用** |
| **① AI 信号→下单意图适配器** | label→direction 规则 + 仓位策略 | **新建**(真缺口) |
| **② 决策卡 actionable 子 schema** | `direction` + `suggested_position_pct`(可选 entry/target/stop) | **新建**(additive,不改现有字段) |
| **③ 前端"一键模拟下单"按钮** | 卡片/信号条上 → 复用 R6 现成确认模态 + VIRTUAL 徽章 + disclaimer | **新建**(小) |
| **④ 新入口** | `POST /api/v1/virtual/ai-order`(或复用 bot facade) | **新建**(薄 plumbing) |
| **⑤ 来源标记**(可选但建议) | order 加一列 `source=ai_signal/manual` 区分 AI 单 | **新建**(小,nullable 列) |

**复用度粗估:下单侧 ~70–75%、AI 侧 ~80%+。** 第一层基本是"AI 信号→意图→现成 facade"的薄适配 + 一个 endpoint + 确认/disclaimer 守卫,底层交易机器全是打磨过、有测试的。

### A4. 四市场(A股/美股/港股/加密)能否统一?

★ **AI 分析 + 现货下单能统一(cn/us/hk 共用一个引擎);加密永续不可并入,是独立引擎族。最干净的设计 = "一条统一现货流 + 一个加密永续分支"——而且代码库现在就是这么长的。**

**已存在的统一面**:
1. **一个 `Market` 字面量**(`schemas/market.py:15` `Literal["cn","us","crypto","hk"]`),全栈当普通字符串穿。
2. ★ **一个统一 K 线/报价读法** `ClickHouseClient.select_kline(symbol, market, period, limit, instrument)`(cache-aside over `BaseDataSource`),AI / 图表 / 告警 / 虚拟撮合报价**全走它**——最强的统一资产。
3. **一个市场无关的 AI workflow** `run_decision_workflow(symbol, market, period, klines)`,只有 3 行系统提示词按市场分叉。
4. **一个现货撮合引擎** `place_market_order`,内部只按 LONG/SHORT 分叉,不按市场分叉(cn/us 已跑,ADR 0034 指定 hk 也复用它)。

**不可约的逐市场分支**:
- **加密永续**(杠杆 + 资金费 + 强平 + 逐仓/全仓分流)= 真·独立引擎族 + `instrument=perp` 路由 guard。**这是唯一的硬分支,且已正确隔离。**
- **A股 T+1**:**当前根本没建模**——全代码库只有 AI 提示词里出现"T+1"字样,`VirtualPosition` 无可卖数量锁,`_execute_sell` 自由卖。**A股虚拟现在实质是 T+0。** 若产品要 T+1 保真,是唯一的净新增逐市场交易逻辑。
- **交易时段**:`market_calendar.py` 按 cn/hk/us 分(crypto 24/7),但**只用于展示状态、不 gate 下单**,不在交易关键路径。
- **逐市场费率/手数字典**:`fees.py` 等 dict 查表分支,扩展便宜,非结构性分叉。

> ★ **hk 半接线警告(对统一工作很重要)**:hk 在 `Market` 字面量 + `Currency` + `MARKET_CURRENCY` 里,但 ① **无 `hk_source` 适配器** ② kline/symbols 路由硬返空 ③ `fees.COMMISSION_RATES` + `ai/agents/technical._system_prompt` + bot `_DIRECTIONS` 三个 dict **都缺 hk 键(会 KeyError / 静默不可下单)** ④ ADR 0034a 明确把 hk 下单推到"阶段三"。**所以第一层应先打 cn/us/crypto(AI 今天能分析的 3 市场)**,hk 等港股阶段三落地时,三个 dict + CH `Enum8` ALTER + `hk_source` 一起补齐再纳入。

---

## B. QuantDinger 哪些设计【纯 AI 价值、与实盘无关】可借鉴

> 调研原则:QuantDinger 核心是"AI→策略→回测→**真实多券商实盘**",我们**只要虚拟、绝不要实盘那部分**。下面严格区分"纯 AI/分析价值"与"为实盘服务、我们不要的"。

### B1. AI 分析管线(`fast_analysis.py`,文档 §8.2)—— 可借鉴增强我们的 AI

QuantDinger 的 `analyze()` 五阶段,对我们有价值的是**前两阶段的"客观共识"思想**:

| 机制 | 它怎么做 | 对我们的借鉴价值 | 我们现状 |
|---|---|---|---|
| **多周期客观共识** | 每周期算 `objective_score`(技术/基本面/情绪/宏观综合),按强度加权 → `consensus_score` + `agreement_ratio` + `quality_multiplier` | ★★ 高 —— 让方向判断更稳健、给 confidence 一个**客观锚**(不只靠 LLM 自报) | 单周期、单技术面 Agent,confidence 由 LLM 自报 |
| **共识校准覆盖** | 强共识时**用客观共识覆盖 LLM 决策**并改写 confidence;**质量过低强制 HOLD** | ★★ 高 —— 聪明的"AI 兜底":客观指标强烈一致时不盲信 LLM;数据太差强制中性,避免乱给信号 | 无,完全信 LLM 输出 |
| **ensemble 多模型投票** | 多模型对 decision 做 Counter 多数表决 | ★ 中 —— 提鲁棒但**翻倍 LLM 成本**;做成可选开关 | 单模型;预算 ¥200/mo、当前 ¥0.0007/call,有空间但非必须 |

**借鉴方式**:这些是**纯后端 AI 管线增强,完全不碰下单**。可以把现有单 Agent 升级成"多周期采集 → 客观共识打分 → LLM/ensemble → 共识校准覆盖 → 置信度校准",输出 schema 基本不变(只是 score/confidence 更可信)。**与第一层下单完全解耦,可独立并行开发(见 §C2 批次乙)。**

### B2. ★★★ AI 自学习闭环(`analysis_memory` + `reflection` + `ai_calibration`,文档 §8.3)—— 最值得借鉴

这是整份文档**最契合产品定位、且全程不碰实盘**的设计:

| 组件 | 它怎么做 | 复杂度 / 我们怎么落 |
|---|---|---|
| **analysis_memory** | `qd_analysis_memory` 存每次分析;`get_similar_patterns` 给新分析注入历史相似形态;按分桶算准确率 | 中 —— 新建一张 `ai_analysis_memory` 表(我们已有 `ai_usage_log` 可借鉴写法);相似形态注入可后置 |
| **reflection** | 守护线程(默认每日),用**真实价格回填**验证 ≥7 天前的 AI 决策(`was_correct` / `actual_return_pct`) | 中 —— **复用我们现成的 Celery beat + `select_kline`**(回填真实价格我们完全有能力);纯后台任务 |
| **ai_calibration** | 用已验证记录在阈值网格搜索最大化准确率,market 维度自调优 | 低-中 —— 纯 Python 阈值搜索,读 memory 表 |

★ **为什么这个最值得做**:它让 AI 决策**"可验证、可校准"**,而非一次性黑箱——把"这个 AI 过去 N 次建议的真实命中率 / 平均收益"亮给用户,**直接兑现产品"给用户可借鉴、有指导价值的 AI 能力"这句话**,而且**零实盘风险**(纯历史回填验证)。是巨大的信任 builder。**全部复用我们已有基建**(Celery / select_kline / 决策卡)。建议优先级高(§C2 批次乙)。

### B3. 🚫 明确排除(为真实下单/券商服务,本调研不评估)

文档里以下都是**为真实实盘服务**的,我们**不要、调研里排除**:

| 文档章节 | 内容 | 为什么排除 |
|---|---|---|
| §7.1 | 两段式队列下单的"**真实交易所**"部分(`PendingOrderWorker` → 自研 REST → 真实下单) | 接真实通道,红线禁止。(注:**队列模式本身**可借鉴用于"异步模拟托管"第三层,但只调虚拟引擎) |
| §7.2 | 自研下单 REST client(9+ 加密交易所、broker code 返佣) | 真实下单 |
| §7.3 | IBKR / MT5 / Alpaca 三家券商集成 | 真实下单 |
| §7.4 | 凭据加密 `credential_crypto.py`(Fernet,`qd_exchange_credentials`) | **我们永不存交易所 key**(CLAUDE.md:不在前端/DB/日志放凭证) |
| §9.1 | Agent Gateway 的 **live 实盘三重闸门** + T(交易)scope | 实盘开关;但 `paper_only`/scope/审计模型对**远期第三层的安全边界**有参考(纯模拟语境) |
| §10 | USDT 链上支付 / 积分计费 / 会员 | 它的变现,与我们无关 |
| §7.4 | `broker_market_policy` 多券商兼容矩阵 | 为多券商实盘服务 |

### B4. 策略沙箱 `safe_exec`(文档 §6.2)—— 第二层才可能需要,评估不深入

`safe_exec` = 正则黑名单 + AST 双校验 + 白名单 builtins + 超时(~618 行 + 持续的逃逸攻防)。

★ **是否需要,取决于第二层"AI 策略"的形态**:
- 若 **AI 生成可执行 Python 策略代码** 并在服务端跑 → **必须要沙箱**(否则 RCE),且这是一个**独立大工程**(沙箱本身 + 长期攻防维护)。
- 若 **AI 策略是"参数化规则 / 声明式 DSL"**(像我们现在前端算的 4 条实战策略规则,或 QuantDinger 自己的 no-code `StrategyCompiler` JSON 规则)→ **不需要沙箱**。

**建议**:第二层**优先走"参数化规则 / 声明式 DSL"**,避开沙箱复杂度;若产品坚持"AI 写任意策略代码",再引入 `safe_exec` 级沙箱(单独立项)。**这个选择直接决定第二层工作量(差一个沙箱大工程)**,是 §C3 的关键拍板点。

---

## C. 分层与合并开发评估(产品负责人特别关心)

### C1. 三层依赖关系

```
                ┌─────────────────────────────────────────────┐
   共享底座 U0  │ AI 信号→下单意图适配 + actionable schema +    │  ← 第一、二层都用
                │ 下单通道复用(bot/order facade)+ 来源标记     │
                └───────────────┬─────────────────────────────┘
                                │
   第一层 ───────────────────────┤  AI 建议→一键模拟下单(U0 + 前端一键 + 确认 + endpoint)
                                │
   AI 增强(批次乙,与下单解耦)  ┊  多周期共识 + 自学习闭环 —— 可并行/先行,不依赖 U0
                                │
   第二层 ───────────────────────┤  AI 策略模拟参考(策略表达 DSL + 多步信号 → 复用 U0 下单通道)
                                │
   第三层(远期)────────────────┘  AI 自动模拟托管(第一+二层 + 自动调度循环 + 授权/风控边界)
```

- **第一层**自包含:`AI 信号→意图`(U0)+ 现成引擎。
- **第二层**依赖 U0 的下单通道;但它的核心(策略表达 + 多周期共识)**可与第一层并行设计**。
- **第三层**(远期)= 第一层下单通道 + 第二层策略 + 一个 Celery 自动调度循环 + 用户授权/风控边界。**本调研不展开细节**(产品负责人定为远期)。
- ★ **AI 能力增强(B1 多周期共识、B2 自学习闭环)与下单完全解耦**,是一条可任意并行的独立线。

### C2. ★ 开发单元划分(尽量合并 · 边界清晰 · 各自可独立验收)

| 单元 | 内容 | 依赖 | 能否独立验收 | 合并建议 |
|---|---|---|---|---|
| **U0 共享底座** | ① label→direction + 仓位策略适配器 ② 决策卡 actionable 子 schema(additive)③ `bot/order.py` 抽成渠道中立 `place_order_intent`(或直接复用)④ order 加 `source` 来源标记 | 无 | 配合单元1验收 | **与单元1 合并**(紧耦合) |
| **单元1(第一层)** | 前端 AI 卡/信号条"一键模拟下单"按钮 → 复用 R6 确认模态 + VIRTUAL 徽章 + disclaimer;`POST /virtual/ai-order` | U0 | ✅ 点 AI 卡"一键模拟"→确认→成交 | **批次甲 = U0+单元1** |
| **单元2(AI 增强)** | 多周期客观共识 + 共识校准覆盖 + 置信度校准(借鉴 B1)| 无(纯 AI 管线) | ✅ AI 卡 score 更稳健、confidence 有客观锚 | **批次乙**,与批次甲**并行** |
| **单元3(自学习闭环)** | analysis_memory 表 + reflection 回填 worker + calibration(借鉴 B2)| 无(复用 Celery+select_kline)| ✅ 展示 AI 历史决策回填命中率 | **批次乙**,与批次甲**并行**;★ 价值最高 |
| **单元4(第二层)** | 策略表达(参数化 DSL,避开沙箱)+ 多步信号序列 → 复用 U0 下单通道 | U0 | ✅ AI 给出多步策略 + 模拟跑 | **批次丙**,排第一层后 |

**合并/并行总策略**:
- **批次甲(U0 + 单元1)= "第一层完整交付"**:它们紧耦合,合并开发、一起自验最高效(下单通道是一块整的地基)。
- **批次乙(单元2 + 单元3)= "AI 能力增强"**:与下单**零耦合**,可与批次甲**并行,甚至先行**。★ 最契合"可借鉴有指导价值 + 零实盘风险",**建议优先级高**(尤其单元3 自学习闭环,是信任 builder)。
- **批次丙(单元4)= 第二层**:依赖 U0,排在批次甲之后。
- **边界清晰原则**:下单通道(U0)是所有层共享地基;AI 管线增强(乙)与下单完全解耦可任意并行;第二层(丙)= 策略表达 + 复用下单通道。三条线之间接口清晰,不会互相阻塞。

### C3. 工作量评估

**第一层(批次甲 = U0 + 单元1)≈ 一个中等 Checkpoint(3–5 个 sub-task),量级类似 MC-4 / G4。**
- 后端(主体):信号→意图适配 + actionable 子 schema(additive)+ `ai-order` endpoint + 来源标记 + 测试。**撮合引擎/facade 已就绪,主要是适配层 + 一个 endpoint + 确认/disclaimer 守卫。**
- 前端(小):AI 卡/信号条加"一键模拟下单"按钮 + **复用现成 R6 确认模态** + VIRTUAL 徽章 + disclaimer。
- 之所以快:**底座(引擎 + bot facade + AI 管线 + 确认模态 + 钱包模型)全现成**,新增的是薄适配层和 UI 触点。

**批次乙(AI 增强)粗评:**
- 单元2(多周期共识):**中**。改 AI workflow,加多周期采集 + 客观共识打分 + 校准覆盖。
- 单元3(自学习闭环):**中**。一张 memory 表 + 一个 reflection worker(复用 Celery+select_kline)+ calibration 阈值搜索。无下单耦合。

**第二层(批次丙 = 单元4)粗评:**
- 若走**参数化规则 DSL**(建议):**≈ 2 个 Checkpoint**(策略表达 + 多步信号 + 复用下单 + 模拟跑展示)。
- 若坚持**AI 生成可执行代码**:**额外 +1 个大 Checkpoint** 给 `safe_exec` 级沙箱(独立攻防工程)。**§B4 的拍板直接决定这里。**

> 工作量以**项目惯用的 Checkpoint / sub-task 量级**表达(非人天);"中等 Checkpoint"≈ 过去 MC-4(全仓分流接入)那种"底座已在、主要做接入 + 前端 + 自验"的批次。

---

## D. 红线复核 + 留给产品负责人的拍板点

**红线复核(本方案全程守住)**:
- ✅ 全程虚拟:所有下单只调 `services/virtual_trading/*` 撮合引擎,**永不接真实交易通道**。AI 信号也只能进虚拟引擎。
- ✅ 凭证:不存任何交易所 key(QuantDinger 的 §7.4 Fernet 凭据加密整块排除)。
- ✅ 现有功能完整保留:U0 把 `bot/order.py` 抽成渠道中立内核时**零改撮合引擎**(沿用 MC 系列"引擎一行不改"的纪律);AI 模块是**新增**,不动现有手动下单 / bot 下单 / 永续。
- ✅ disclaimer:AI 输出继续带"仅供参考,不构成投资建议"+ VIRTUAL 徽章。

**留给产品负责人的拍板点(供出 ADR)**:
1. ★ **合规口径**:第一层要给 actionable 建议(direction + 仓位),需**适度放松**现有 `validator.py` 的"禁祈使句"设计。红线是**不接真实交易**,不是"不给虚拟建议";产品要的"可借鉴有指导价值"本身就需要 actionable。**建议:放松,但保留 disclaimer + VIRTUAL 徽章 + "模拟"语境**(这正是产品负责人说的"合规层面不必过度收紧")。
2. **第一层市场范围**:先 **cn/us/crypto**(AI 今天能分析的 3 市场),hk 等港股阶段三?**建议:是。**
3. **仓位策略**:复用 `BotOrderPreset`(per-user 名义/杠杆),还是新建**AI 专用风险预设**(按 confidence 缩放仓位)?**建议:第一层先复用 BotOrderPreset,AI 专用预设留作增强。**
4. ★ **第二层策略表达形态**:**参数化规则 DSL**(避开沙箱)vs **AI 生成可执行代码**(需 `safe_exec` 沙箱)?**建议:先 DSL**(直接省掉一个沙箱大工程)。
5. **批次乙优先级**:AI 增强(尤其单元3 自学习闭环)是否**先于/并行于**第一层做?**建议:并行,且自学习闭环可优先**(价值最高、零下单耦合、最兑现产品定位)。

---

> 本文为纯调研评估,不含代码改动。A 部分代码结论已读源码核实(关键两处亲自二次校验);B 部分基于《QuantDinger 技术拆解文档》v3.0.18。产品负责人据此判断 + 出 ADR 后,按 §C2 的批次划分(尽量合并)分阶段开工。
