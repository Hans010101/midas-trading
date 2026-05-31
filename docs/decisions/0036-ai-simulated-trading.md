# 0036 · AI 模拟交易模块(AI-Assisted Simulated Trading)设计

## 状态
**草案**(2026-05-31 · 待产品负责人审 —— 重点审 ① 虚拟红线焊死 ② 校验器放松边界 ③ 现有交易零回归)

> 调研基线:[docs/research/ai-simulated-trading-feasibility.md](../research/ai-simulated-trading-feasibility.md)(已读源码核实复用度)。
> 本 ADR 只出设计,不含实现代码。审过 + 拍板 → 按批次甲先起步、批次乙并行开工。

---

## 上下文

产品要在现有「**AI 分析(0011 缠论 + 0012 决策卡)+ 虚拟交易(0008 现货 + 永续系列)**」之上,新增 **AI 模拟交易**模块 —— 让 AI 更深度参与交易动作,给用户**可借鉴、有指导价值**的 AI 交易能力。三层渐进:① AI 建议→一键模拟下单 ② AI 策略模拟参考 ③ AI 自动模拟托管(远期)。

调研结论(复用度极高,详见研究文档):
- **下单侧 ~70–75% 复用、撮合引擎零改动** —— 三个下单入口(`place_market_order` / `route_open_perp` / `route_close_perp`)都是纯 service 函数;且已有**跑通的非 HTTP 内部下单通道** `bot/order.py::execute(db, ch, user_id, intent)`,已含方向解析 + 仓位预设 + 报价 + 预览。
- **AI 侧 ~80%+** —— 真实 DeepSeek(LiteLLM)+ LangGraph + 缠论输入 + Redis 缓存 + 决策卡/信号条/买卖点前端全复用。
- **唯一真缺口** —— 现有 AI 只产「分析观点」(评分 + 强多/弱多/中性/弱空/强空 + 关键价位 + 缠论点),**无 direction/仓位/进出场价**等可下单字段(当初为合规有意去 actionable)。

### 产品负责人 5 点拍板(本 ADR 据此设计)

| # | 拍板 | 落到本 ADR |
|---|---|---|
| ① | **合规放松**:放松校验器"禁 actionable",允许 AI 给「方向 + 仓位」可操作建议;但必保留 VIRTUAL 徽章 + 免责声明 + "模拟"语境。红线是不接真实交易,不是不给虚拟建议。 | §2.3 校验器放松边界(精确) |
| ② | **第一层市场**:先 cn/us/crypto;港股(hk 半接线)等其阶段三接数据后再加。 | §2.6 |
| ③ | **仓位策略**:第一层先复用现有 `BotOrderPreset`,不新建 AI 专用风险预设。 | §2.4 |
| ④ | **第二层策略形态**:先参数化策略 DSL,不做"AI 生成可执行代码"(避开 `safe_exec` 沙箱大工程)。 | §5 + §4 |
| ⑤ | **批次节奏**:第一层(批次甲)先起步 + AI 增强(批次乙)并行跟上。 | §7 |

---

## 决策

## 1. 模块定位 + 红线对齐

### 1.1 头号红线(焊死)· 全程虚拟、绝不接真实交易通道
- **AI 发起的下单,与用户手动单走同一条路:只调 `app/services/virtual_trading/*` 撮合引擎,绝不接任何真实交易所/券商通道。** 这条与 0008「永不接真实下单」完全一致 —— AI 模块**不新开任何下单出口**,只是多一个**触发源**(AI 信号),触发源之后的撮合/记账/持仓全部复用既有虚拟引擎。
- 本 ADR §4 明确列出 QuantDinger 中**为真实下单/券商服务、我们一律排除**的部分。

### 1.2 模拟语境 + 免责分级(复用现有机制)
- 任何 AI 建议 + 一键模拟下单元素,**必带帝王金 `VIRTUAL · 模拟` 徽章**(复用 `components/ui/VirtualBadge.tsx`)。
- 强制 disclaimer「仅供参考,不构成投资建议」(复用 `DecisionCardResponse.disclaimer` 既有兜底,API + UI 双层)。
- 文案语境保持"模拟"措辞(不暗示真实收益)。

### 1.3 ★ 现有功能完整保留 · 零回归(AI 模拟交易是【新增并行能力】)
- 现有**手动虚拟交易**(网页 + bot 下单)、**AI 分析决策卡**、**四市场行情**,在本模块落地后**行为不变、零回归**。
- AI 模拟交易是在它们**旁边新增的一条并行能力**,不替换、不重构既有路径。零回归用三套既有纪律证明(§6.3)。

---

## 2. 批次甲 = 第一层(AI 建议 → 一键模拟下单)细案

> 一句话:**用户看 AI 建议 → 一键按建议在虚拟账户成交 → 记进虚拟持仓(标记为 AI 单)。**

### 2.1 U0 共享底座(第一、二层都用 · 一次做好)

**复用现有非 HTTP 下单核心** `bot/order.py::execute(db, ch, user_id, intent: OrderIntent)`:
- 它已是渠道中立的(`db` 是普通 `AsyncSession`,`user_id` 由调用方传入),已含:方向→`(side, position_side, quantity)` 解析、**从 `BotOrderPreset` 算仓位**、symbol 规范化、报价、"平仓=平整个活仓"、`build_preview` 预览不落库。
- `OrderIntent = {market, symbol, direction}` 本身就是一个干净的"下单意图"载体。

**U0 要做的事(薄,且守"引擎零改 + bot 行为零回归"):**
1. **下单核心标记来源**:给 `OrderIntent` / `execute` 增加可选 `source: str = "manual"`,贯穿到订单行(见 §2.5)。bot 路径默认 `"bot"`,行为字节级不变(用 P1 golden 快照证明)。
2. **抽不抽公共 `place_order_intent`** 留实现期定:原则是**撮合引擎一行不改**;若 web 一键与 bot 长期共用,可把 `execute` 的下单核心抽成渠道中立函数、bot 与 web 各薄封装。第一层最小可行做法 = web 端点直接复用 `execute`。

### 2.2 actionable 适配层(★ 不改 AI 分析管线本身,只加适配层)

**输入**:现有 `DecisionCardResponse`(`composite_label` + `composite_score` + `composite_confidence` + `agent_scores[].key_levels` + `chan_signals`)。
**输出**:一个新增的 `ActionableAdvice` 结构(typed,**纯函数确定性派生,不调 LLM**):

```
ActionableAdvice {
  direction:  buy | sell | hold | open_long | open_short | close   # 按市场取子集
  size_hint:  来自 BotOrderPreset 的名义额(拍板③)· 可选 confidence 备注
  entry/target/stop:  可选 · 从 key_levels + chan_signals 派生(派生不出就 null,不编造)
  basis:      "强多 · score 72 · conf 0.66" 这类可读依据
}
```

**映射规则(确定性,可单测)**:
- **现货 cn/us**:强多/弱多 → `buy`;中性 → `hold`(不下单);弱空/强空 → **有持仓则 `sell`(平),无持仓则 `hold`/观望**(现货不裸做空;us 卖空第一层先不做,简化)。
- **加密 perp**:强多 → `open_long`;强空 → `open_short`;中性 → `hold`;弱多/弱空 → 弱信号(默认 `hold` 或小仓,可配置)。
- **仓位**:拍板③ —— 复用 `BotOrderPreset`(perp 100 USDT@3x、现货 10000 CNY / 1000 USD)。按 confidence 缩放仓位留作批次乙增强,第一层固定 preset。

★ **关键纪律**:这层只**读** `DecisionCardResponse` 输出、产 actionable,**绝不改** `workflow.py` / `technical.py` / 现有 `DecisionCardResponse` 字段(只 **ADD** 一个可选 `actionable` 子字段,不破坏现有消费方)。AI 分析管线本身零改动。

### 2.3 ★ 校验器放松边界(精确:放松什么 / 保留什么)

现状:`validator.py` 把 narrative 里的祈使句改写(「建议买入」→「分析显示买入信号」),即**禁一切 actionable**。

**放松(因产品要 actionable 虚拟建议)**:
- **允许新增结构化 `ActionableAdvice` 字段**(typed `direction` + 仓位)。注意:它是**结构化数据、不是散文**,本就不经过 narrative 的祈使句校验 —— 所以"放开 actionable"主要是**产品层允许暴露这个字段**,代码上对它**无需**跑 prose 校验(typed 枚举天然有界)。
- 可选:把 narrative 散文校验从 strict 调成 **advisory 模式**,允许出现方向性结论措辞(让 AI 建议读起来更自然)。

**保留(任何模式都不放松)**:
- ✅ disclaimer「仅供参考,不构成投资建议」强制存在(API + UI 双层兜底)。
- ✅ VIRTUAL · 模拟徽章 + "模拟"语境。
- ✅ **仍然过滤真违规话术**:保证收益 / 稳赚 / 无风险 / 诱导性营销词 —— 这类是**真红线,与 actionable 无关**,放松 actionable 不等于放开这些。即 validator 从「禁所有 actionable」改成「**禁违规营销话术、允许 actionable 分析建议**」。

**零回归保护**:默认**现有只读决策卡的 narrator 行为不变**(strict 保持),advisory 仅作用于 AI 模拟交易模块的新路径;这样老卡片字节级零回归,新路径才放松。strict↔advisory 用显式开关区分,不靠隐式默认。

### 2.4 一键模拟下单流程

```
AI 决策卡(新增 actionable 建议 + VIRTUAL 徽章 + disclaimer)
   │  用户点「一键模拟下单」
   ▼
二次确认模态(★ 必走 · 复用 R6 现成确认模态 · 显示:模拟 + 标的/方向/仓位 + 免责)
   │  确认
   ▼
POST /api/v1/virtual/ai-order  →  execute(db, ch, user_id, OrderIntent(source="ai_signal"))
   │  (现货走 place_market_order · 加密走 perp_dispatcher · 撮合引擎零改)
   ▼
虚拟账户成交 → 记进虚拟持仓(source=ai_signal)→ toast 反馈 + 持仓刷新
```

- **仓位**来自 `BotOrderPreset`(拍板③);用户在确认模态可见名义额。
- **二次确认必走**(§6 建议):AI 单是真实改变虚拟持仓的写操作,且 AI 单**更需要**确认(防用户盲从)—— 复用既有 R6 模态,零新增 UI 范式。

### 2.5 来源标记(区分手动单 vs AI 单 · 喂批次乙)

- `virtual_order` + `virtual_perp_order` 各加一列 `source`(nullable String,值域 `manual` / `bot` / `ai_signal` / `ai_strategy`,默认 `manual`)。
- **可逆 additive 迁移**(nullable + 默认值,现有行视为 `manual`,零回归;沿用 MC-1 "Enum→String 可逆迁移" 的做法)。
- 用途:① 后续统计 **AI 建议单的真实表现** ② ★ **与批次乙自学习闭环协同** —— `source=ai_signal` 的单 = 真实模拟成交结果,是 reflection 回填验证的高质量样本(不只纸面决策)。

### 2.6 市场范围(拍板②)

- **第一层:cn / us / crypto**(AI 今天能分析的 3 市场)。现货流统一(`place_market_order` 处理 cn/us)+ 加密永续分支(`perp_dispatcher`)。
- **hk 暂不纳入**:半接线(无 `hk_source` 适配器;`fees.COMMISSION_RATES`、`ai/agents/technical._system_prompt`、bot `_DIRECTIONS` 三个 dict 缺 hk 键)。等港股阶段三(0034a 后续)接数据 + 补三个 dict + CH `Enum8` ALTER 后再加,**那时 AI 模拟交易复用同一条现货流即可**。

### 2.7 复用度

下单侧 ~70–75% + AI 侧 ~80%+,**撮合引擎零改动**。第一层主体 = actionable 适配层 + 一个 endpoint + 确认/disclaimer 守卫 + 来源标记迁移 + 前端一键按钮。

---

## 3. 批次乙 = AI 增强(可与甲并行 · 与下单零耦合)

> 借鉴 QuantDinger 的**纯 AI 设计**(★ 已排除所有实盘/券商部分,见 §4)。全程不碰下单、不碰真实交易。

### 3.1 ★ 自学习闭环(借鉴 QuantDinger §8.3 · 价值最高)

让 AI 决策**可验证、可校准**,把"AI 历史命中率"亮给用户 —— **指导价值高、零实盘风险**,直接兑现产品"可借鉴、有指导价值的 AI 能力"。

| 组件 | 借鉴 | 我们怎么落(复用现有基建) |
|---|---|---|
| **analysis_memory** | `qd_analysis_memory` 存每次分析 | 新建 `ai_analysis_memory` 表,AI 决策生成时落一行(symbol/market/period/label/score/confidence/key_levels/ts)。写法借鉴现有 `ai_usage_log` |
| **reflection** | 守护线程用真实价格回填验证 ≥N 天前决策 | **复用现有 Celery beat**;worker 取到期决策 → **`ch.select_kline` 拉后续真实价格** → 算 `was_correct` / `actual_return_pct` 回写 |
| **calibration** | 用已验证记录搜阈值、自调优 | 纯 Python:按 label/score 桶算真实命中率;market 维度 |

- **前端**:"AI 历史命中率"展示(决策卡内或独立面板,待定 §8)。
- ★ **与批次甲协同**:`source=ai_signal` 的真实模拟成交 = reflection 的高质量样本;但 reflection 也能直接验证**纸面决策卡**(不依赖甲先上线),所以乙可独立先跑。

### 3.2 多周期共识 + 置信度校准(借鉴 §8.2)

- workflow 加**多周期采集**(主周期 + 辅周期)→ 每周期 `objective_score` → **客观共识** `consensus_score` + `agreement_ratio`。
- **强共识覆盖 LLM** + **质量过低强制 HOLD**(聪明的 AI 兜底:客观指标强烈一致时不盲信 LLM;数据太差不乱给信号)。
- 历史分桶**置信度校准**(消费 §3.1 calibration 数据)。
- 输出 schema 基本不变(score/confidence 更可信),前端零改。

### 3.3 ensemble 多模型投票(可选开关)

- 多模型对 decision 多数表决,提鲁棒但**翻倍 LLM 成本**。做成 **env 开关,默认关**(预算 ¥200/mo,当前 ¥0.0007/call,有空间但非必须)。

---

## 4. ★ 明确排除(不做 · 别评估)

QuantDinger 以下都是**为真实下单/券商服务**的,我们**只要虚拟,一律排除**:

| 排除项 | 文档章节 | 原因 |
|---|---|---|
| 两段式队列下单的「**真实交易所**」段 | §7.1 | 接真实通道(注:队列**模式**本身可借鉴用于远期第三层异步模拟托管,但只调虚拟引擎) |
| 自研下单 REST client(9+ 交易所、返佣码) | §7.2 | 真实下单 |
| IBKR / MT5 / Alpaca 券商集成 | §7.3 | 真实下单 |
| Fernet 凭据加密(`qd_exchange_credentials`) | §7.4 | **我们永不存交易所 key** |
| Agent Gateway 的 **live 实盘三重闸门** + T scope | §9.1 | 实盘开关 |
| USDT 链上支付 / 积分计费 / 会员 | §10 | 它的变现,与我们无关 |
| **`safe_exec` 沙箱** | §6.2 | 拍板④走参数化 DSL → 第二层也不需要沙箱,整块避开 |

---

## 5. 批次丙 = 第二层(AI 策略模拟参考 · 远期 · 粗略带过)

- **形态(拍板④)**:**参数化策略 DSL**(声明式规则,像现有前端 4 条实战策略规则 / QuantDinger no-code `StrategyCompiler`),**不做 AI 生成可执行代码** → 整块避开 `safe_exec` 沙箱工程。
- AI/规则生成**多步策略信号序列** → **复用 U0 下单通道**在虚拟账户模拟跑。
- 依赖 U0,排批次甲之后。本 ADR 不展开细案,留第一层落地、产品验证后单独出设计。

---

## 6. 红线与零回归

### 6.1 虚拟账户焊死
AI 下单**只走 `services/virtual_trading/*` 引擎**,与手动单同一条路,绝不接真实通道。AI 模块不新开任何下单出口。

### 6.2 模拟徽章 + 免责 + 二次确认
- VIRTUAL 徽章 + disclaimer 强制(§1.2)。
- **★ 建议:AI 建议下单必走二次确认**(复用 R6 模态)。理由:是真实改变虚拟持仓的写操作 + AI 单更需防盲从 + 教育"这是模拟"。

### 6.3 现有功能零回归(三套既有纪律证明)
1. **撮合引擎 git diff 证零改动**(沿用 MC 系列"引擎一行不改"自证)。
2. **bot 行为 golden 快照零回归**(沿用 P1 `test_bot_golden.py` 字节比对)—— U0 给 `execute` 加 `source` 后,bot 路径输出必须字节级不变。
3. **全量回归 pytest + 四市场(cn/us/crypto)真机抽查** —— 现有手动单 / AI 决策卡 / 行情不变。

### 6.4 校验器放松要精确
放松 = 允许结构化 actionable + (可选)narrator advisory 措辞;**不破坏** disclaimer 强制、不放开违规营销话术过滤、默认不动现有只读卡片行为(§2.3)。

---

## 7. 分批次开发计划(尽量合并 · 边界清晰 · 各自可验收)

### 批次甲 = 第一层(U0 + AI 建议→一键模拟下单)· 中风险 · feature 分支 + 审 + 验收

| sub-task | 内容 | 风险 |
|---|---|---|
| **甲1 U0 下单核心** | `source` 列可逆迁移(virtual_order + virtual_perp_order)+ `execute`/OrderIntent 接 `source` 标记 · **bot golden 零回归** | 中(碰下单核心 + 迁移) |
| **甲2 actionable 适配层** | `DecisionCard → ActionableAdvice` 确定性映射(纯函数 + 单测)+ `actionable` 子 schema(additive) | 低(纯新增) |
| **甲3 校验器放松** | advisory 模式 + 精确边界(允许 actionable / 保留 disclaimer + 禁营销违规)+ 测试 | 中(合规边界) |
| **甲4 web 下单端点** | `POST /api/v1/virtual/ai-order`(复用 `execute`)+ 来源标记 + 二次确认契约 | 中(碰下单) |
| **甲5 前端 + 自验** | AI 卡 actionable 展示 + 一键模拟下单按钮 + 复用 R6 确认模态 + VIRTUAL 徽章 · 全量回归 + 四市场真机抽查 | 中 |

**甲验收点**:点 AI 卡「一键模拟下单」→ 二次确认 → 虚拟账户成交 → 持仓更新且标 `source=ai_signal`;cn/us/crypto 三市场跑通;**现有手动单 / AI 决策卡 / 行情零回归**(三套证明)。

### 批次乙 = AI 增强 · 低风险(纯新增 + 与下单解耦)· 可与甲并行

| sub-task | 内容 | 风险 |
|---|---|---|
| **乙1 memory 表** | `ai_analysis_memory` 表 + 模型 + 迁移 + 决策生成时落库 | 低 |
| **乙2 reflection worker** | Celery beat + `select_kline` 真实价格回填 + `was_correct`/`actual_return_pct` | 低 |
| **乙3 calibration + 命中率展示** | 桶命中率聚合 + 前端"AI 历史命中率"展示(可消费甲的 `ai_signal` 单) | 低 |
| **乙4(后置/可选)** | 多周期共识 + 置信度校准 + ensemble 开关 | 中(改 workflow) |

**乙验收点**:reflection 用真实价格回填验证历史 AI 决策,前端展示"AI 历史命中率";全程不碰下单、零实盘风险。

### 甲乙并行关系
- **甲碰已上线交易核心 = 中风险** → feature 分支 + 产品负责人审 + 验收。
- **乙纯新增 + 与下单零耦合 = 低风险** → 可与甲并行;`乙1/乙2` 用纸面决策即可先跑,不阻塞甲;`乙3` 命中率统计在甲上线后可额外消费 `ai_signal` 真实单(协同,非依赖)。
- **接口边界清晰**:U0 下单通道(甲)/ AI 管线增强(乙)/ 第二层策略(丙)三条线接口分明,互不阻塞。

---

## 8. 需产品负责人拍板的点(审本 ADR 时一并定)

1. **二次确认**:AI 建议下单是否必走二次确认?**(建议:是,必走,复用 R6 模态)**
2. **校验器放松边界确认**:结构化 actionable 放开(必须);narrator 散文是否也切 advisory 措辞,还是保持现有 strict 不动?**(建议:结构化 actionable 放开;narrator 默认保持 strict 以零回归,advisory 仅 AI 模拟交易新路径可选)**
3. **actionable 放哪**:决策卡加 `actionable` 子字段(建议,单一事实源)vs 独立 endpoint?
4. **现货弱空/强空处理**:现货不裸做空 —— 弱空/强空时「有持仓则建议平、无持仓则观望」?**(建议:是)**
5. **`source` 值域**:`manual` / `bot` / `ai_signal` / `ai_strategy` 够用?现有 bot 单标 `bot`、网页手动标 `manual`?
6. **AI 历史命中率展示位置**:决策卡内 vs 独立面板?
7. **仓位 confidence 缩放**:第一层固定 `BotOrderPreset`(拍板③确认),缩放留批次乙?**(建议:是)**

---

> 本 ADR 为设计草案,不含实现代码。产品负责人审过(尤其 §1 虚拟红线焊死、§2.3 校验器放松边界、§6 零回归)+ 拍板 §8 → 按批次甲先起步、批次乙并行开工。每批次走 feature 分支 + 自验闭环 + 验收点,守"撮合引擎一行不改 + 现有交易零回归"。
