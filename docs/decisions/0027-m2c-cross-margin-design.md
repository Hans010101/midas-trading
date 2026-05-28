# 0027 · M2-C 全仓(cross)永续合约 · 设计方案

## 状态

**Approved**(2026-05-28)· 产品方就 §9 全部 10 个决策点拍板,按 §8 五期推进,先做 MC-1。
方案阶段不含实现代码;实施期每期 feature 分支 + 严格审(迁移逐行审 · 引擎核心碰不得 · 改动严格隔离)。

> **实施进度**:MC-1(迁移 + 隔离地基)· feature 分支 `feat/m2c-cross-mc1` · 进行中。
> MC-2 / MC-3 / MC-4 / MC-5 见 §8,逐期推进。

承接:ADR-0019(M2-C.1 逐仓永续引擎,已上线半年)+ ADR-0020(M2-C.2 资金费)+ 0025
DP5(bot 合约下单「全仓字段预留」)+ 0026 G5(`bot_order_preset.perp_margin_mode` 预留位)。

> 🔴 红线(贯穿):全程【虚拟资金】· 全仓引擎只是教学,绝不接真实交易 / 下单 / 资金费 /
> 转账。**改的是已上线半年、用户在用的 M2-C 逐仓引擎核心 —— 第二级别高风险(仅次于 G2a
> 不可逆迁移)**。所有改动必须严格隔离:现有逐仓持仓数据 + 逐仓强平 worker 绝对零影响。
> 实施期每期 feature 分支 + 严格审 + 迁移逐行审。本文只出方案。

---

## 1. 现状摸查:逐仓引擎是怎么做的(精确到函数 + 数据流)

> 全部读自:`services/virtual_trading/perp_engine.py`、`perp_fees.py`、`perp_funding.py`、
> `models/perp.py`、`worker/tasks/perp_liquidation.py`。

### 1.1 数据模型(`models/perp.py`)
- **钱包**:复用 0008 `VirtualAccount`(crypto 市场那一行,USDT)· `cash_balance` = 钱包余额。
- **`VirtualPerpPosition`**(单向净持仓):`account_id` FK → virtual_account · `symbol`(Binance
  风格 `BTCUSDT`)· `side`(long/short)· `margin_mode`(**Enum `margin_mode`,当前只有 `isolated`
  一个值**)· `leverage` · `quantity` · `entry_price` · **`initial_margin`(已冻结保证金 USDT)** ·
  `maintenance_margin_rate`(开仓快照 0.005)· **`liquidation_price`(入库,强平 worker 比对用)** ·
  `realized_pnl` · `fee_paid` · `funding_paid` · `opened_at` · `closed_at` · `close_reason`。
  - 关键约束:**partial unique index `(account_id, symbol) WHERE closed_at IS NULL`** —— 同账户同
    symbol 最多一个活仓。
- `VirtualPerpOrder`(流水)· `VirtualPerpFunding`(资金费流水)。

### 1.2 保证金计算(开仓 `_open_fresh` / 加仓 `_add_to`)
- `notional = qty × fill_price`;`required_margin = notional / leverage`(或显式 margin)。
- `total_cost = required_margin + taker_fee`(taker 0.05% `perp_taker_fee`)。
- **`_atomic_debit`**:`UPDATE virtual_account SET cash_balance = cash_balance − total WHERE id=? AND
  cash_balance >= total RETURNING id`(原子扣;不足返 False → 拒单)。
- **逐仓本质**:保证金从 `cash_balance` **划出**,存进 `position.initial_margin`(每仓独立锁定)。
- 加仓:杠杆须与现仓一致;`initial_margin += `新增 margin;加权均价重算 entry;重算 `liquidation_price`。

### 1.3 强平价(`perp_fees.liquidation_price` · 逐仓闭式解)
```
MMR = 0.005(全局常量)
long :  liq = entry × (1 − 1/lev + MMR)
short:  liq = entry × (1 + 1/lev − MMR)   (钳到 ≥ 0)
```
**每仓独立**,与其它仓 / 钱包余额无关。开仓 / 加仓后重算并入库;部分平仓 entry/lev 不变 → liq 不变。

### 1.4 平仓 / 减仓 / 强平(`_reduce` · `close_perp_position` · `liquidate_position`)
- `gross = realized_pnl_gross(side, entry, fill, qty)`;`realized_net = gross − fee`。
- `released_margin` = 全平时 = `initial_margin`,部分按 `initial_margin × (close_qty/qty)`。
- **逐仓地板**:`is_liquidation` 时 `realized_net ≥ −released_margin`(亏损不超保证金,穿仓平台虚拟承担)。
- `credit = released_margin + realized_net`;`_credit`:`cash_balance += credit`、`account.realized_pnl += realized_net`。
- 全平 → 软删(`closed_at` / `close_reason` / `initial_margin=0`);部分 → 减 `quantity` + 按比例减 `initial_margin`。

### 1.5 资金费(`perp_funding.settle_funding` · ADR-0020)
- 每 UTC 整点扫所有活仓,按各币 `funding_interval_hours` 对齐(`hour % interval == 0`)。
- `payment = sign × rate × mark × qty`(long sign=+1,short=−1;rate>0 多头付空头收)。
- **E4=A:`cash_balance −= payment`(原子;允许为负;不联动强平)**;`funding_paid += payment`;写流水;
  幂等键 `(position_id, funding_ts)`。

### 1.6 强平 worker(`perp_liquidation.scan_liquidations` · beat 60s)
- 扫**所有** `closed_at IS NULL` 活仓 → 批量取 mark(premiumIndex 优先 · ticker 兜底)。
- 命中:`long: mark ≤ liq_price` 或 `short: mark ≥ liq_price` → 重新 `SELECT … FOR UPDATE` →
  `liquidate_position(mark)`。取不到 mark 跳过(不误杀)。

### 1.7 价源(注入式)
撮合 / 强平 mark 都走 `select_premium_index_marks`(真标记价)优先 + perp ticker 兜底。引擎是注入式
`get_mark_price` fetcher,**价源可换不动引擎**(M2-C.2.1 已验证)。

---

## 2. 全仓(cross)的算法设计

**逐仓 vs 全仓本质差异**:逐仓每仓独立保证金 + 独立强平价 + 亏损封顶到本仓保证金;**全仓多仓
共用整个(全仓)钱包余额做保证金、盈亏共担、强平是账户级**(看整个全仓账户的保证金率)。

### 2.1 全仓保证金共担
仿主流交易所(Binance USDT-M)的钱包模型:
- **逐仓保证金「划出」钱包**(存 position.initial_margin);**全仓保证金「不划出」**,留在 `cash_balance`
  里作为共享抵押,只在开仓时做「可用保证金」校验。
- 因此 **全仓抵押池 = 当前 `cash_balance`**(逐仓仓位的保证金已被划走,剩下的就是全仓可用的)。
- **全仓账户权益** `cross_equity = cash_balance + Σ uPnL(所有全仓仓位)`。
  (逐仓仓位的 uPnL 不计入 cross_equity —— 逐仓是隔离的。)
- 开全仓仓校验:`可用 = cross_equity − Σ(全仓仓位 initial_margin_req)`,其中
  `initial_margin_req = notional / leverage`;要求 `可用 ≥ 新仓 initial_margin_req`。
  **开仓只从 `cash_balance` 实扣手续费(fee 是真实成本),保证金不实扣**(留作抵押)。
- → 全仓仓位的 `initial_margin` 字段语义变为「初始保证金**要求**」(用于可用计算),而非「已划出的钱」。

### 2.2 全仓强平算法(账户级)
- **全仓维持保证金** `cross_mm = Σ(全仓仓位 notional_at_mark × MMR)`,`notional_at_mark = qty × mark`。
- **全仓保证金率** `cross_margin_ratio = cross_equity / cross_mm`。
- **触发**:`cross_equity ≤ cross_mm`(即 ratio ≤ 1)→ 该全仓账户进入强平。
- **强平方式**(DP-2):
  - **方案 A · 全账户一次性全平**(教学友好 · 最简 · 推荐起步):一旦触发,把该账户**所有全仓仓位**
    按各自 mark 全平,close_reason=liquidated。穿仓(equity<0)→ 地板到 0(平台虚拟承担,同逐仓)。
  - **方案 B · 分级部分强平**(贴近真实):逐个平仓直到 `cross_margin_ratio` 回到安全线以上;
    需定**强平顺序**(DP-3):① 亏损最大优先 / ② 维持保证金占用最大优先 / ③ 名义额最大优先。
- **资金费**:公式与逐仓**完全相同**(`payment = sign×rate×mark×qty`),差别只在「扣的是共享池
  cash_balance」——而 settle_funding 本来就扣 cash_balance,所以**全仓资金费天然兼容,无需改资金费逻辑**
  (E4=A 仍成立:资金费扣到负也不直接触发强平;强平由全仓 worker 按保证金率独立判定)。

### 2.3 边界
- **开仓保证金占用**:见 2.1(可用 = 权益 − 已用初始保证金要求)。
- **反向仓**:沿用单向净持仓(同 symbol 一个活仓);反向单 → 减仓 / 反手(逐仓现有逻辑可复用)。
- **多仓同时该强平**:全仓是**账户级单一保证金率**,触发即按 2.2 方案处理;方案 A 无需排序,方案 B 需 DP-3 顺序。
- **价格剧烈波动**:全仓 worker 每 60s 扫(同逐仓);极端行情下 mark 取 premiumIndex,缺则 ticker 兜底,
  都缺则跳过不误杀。

---

## 3. 隔离设计:全仓与逐仓如何并存

### 3.1 同一用户能否同时持逐仓 + 全仓?(DP-1 / DP-7)
- 主流交易所(Binance USDT-M)做法:**保证金模式 per-symbol**,不同 symbol 可不同模式(BTC 逐仓 +
  ETH 全仓);**同一 symbol 同一时刻只能一种模式**(有活仓时不可切模式)。
- 推荐采纳同款:`virtual_perp_position` 的 `(account_id, symbol)` 活仓唯一约束**天然保证同 symbol 只有
  一个活仓**(无论哪种模式);不同 symbol 可逐仓/全仓混持。
- 备选(更简):**账户级单一模式**(整个 crypto 账户要么全逐仓要么全全仓)—— 实现更简但灵活性差。

### 3.2 表结构(不动现有逐仓数据)
- **复用 `virtual_perp_position` 表**,全仓仓位 = `margin_mode='cross'` 的行。现有逐仓行
  (`margin_mode='isolated'`)**一个字段都不改、一条数据都不动**。
- 字段语义按模式区分:
  - `initial_margin`:逐仓=已划出的钱;全仓=初始保证金**要求**(money 留在 cash_balance)。
  - `liquidation_price`:逐仓=每仓强平价(worker 用);**全仓此字段不用**(账户级强平)→ 存 `0`
    或 `NULL`。⚠️ 见 3.3 的安全点。
- 是否给现有表加字段:**大概率不需要新字段**(全仓状态可从 positions + cash_balance 现算)。若分级强平
  (方案 B)需要记录顺序/分档,可能加 1~2 个可空字段(DP 决定后定)。

### 3.3 ⚠️ 逐仓强平 worker 必须加一个过滤(唯一需碰的现有运行代码)
- 现状:`perp_liquidation.scan_liquidations` 扫**所有**活仓,按 `liquidation_price` 判强平。
- 风险:若全仓仓位 `liquidation_price=0`,逐仓 worker 的 `short: mark ≥ liq(0)` 会**恒真 → 误杀所有
  全仓空头**!所以**必须**给逐仓 worker 加 `WHERE margin_mode == 'isolated'`。
- 这是**全仓项目里唯一对现有 perp 运行代码的改动**,且是**纯加过滤**:现有逐仓行 margin_mode 全是
  `'isolated'`,加过滤后行为 100% 不变(只是显式排除将来出现的 cross 行)。**这一改动须逐行审 + 单测
  守护「逐仓 worker 永不碰 cross 仓 / cross worker 永不碰 isolated 仓」。**

### 3.4 引擎隔离
- 不在 `perp_engine` 现有 `_open_fresh/_add_to/_reduce/liquidate_position` 里塞 if-cross 分支(那会污染
  已上线逐仓核心);而是**新增全仓专用函数**(`open_cross_position` / `close_cross_position` /
  `liquidate_cross_account` 等),复用 `perp_fees` 的纯函数(uPnL/手续费/盈亏数学是共用的、不涉模式)。
- 逐仓核心函数**一行不改**(除 3.3 worker 过滤)。

---

## 4. 数据模型变动 / PG 迁移

- **`margin_mode` 加 `cross` 值**(DP-5):
  - 选项① `ALTER TYPE margin_mode ADD VALUE 'cross'`(PG 原生 enum 加值)· **不可逆**(PG 不支持删
    enum 值)· downgrade 难干净。
  - 选项② 把 `margin_mode` 列从 Enum 改成 `String(16)`(避开 enum-alter 不可逆;downgrade 可还原列类型)。
  - **✅ 已定:选项②**(DP-5 拍板 · 更可逆、迁移更干净;代价是丢 DB 层 enum 约束,改由应用层 +
    schema 校验)。MC-1 已落地:`d4e5f6a7b8c9` 迁移 Enum→`VARCHAR(16)` + 存量 `lower()` 归一为
    `isolated`,up/down/up 在真实 seed 行上实测可逆;`MarginMode.CROSS` 仅预定义不启用。
- 可能的可空新字段(仅当方案 B 分级强平需要)· 纯 `add_column` 可空 · 可逆。
- 迁移要求:**纯加值/加可空字段,不改不删任何现有列 / 不动任何现有行**;`down_revision` = 届时 head;
  up/down/up 实测;**逐行审**。

---

## 5. 接入点(本文只列,不细化前端 UI)

- **bot 下单(G4 `services/bot/order.py`)**:`_exec_perp` 现在硬走逐仓;接入点 = 读 `load_preset` 的
  `perp_margin_mode`,`isolated` → 现有 `open_perp_position`,`cross` → 新 `open_cross_position`。
  G5 的 `bot_order_preset.perp_margin_mode` 预留位**届时去掉 PUT 的「固定 isolated」**、放开 cross 选项。
- **网页下单(`api/v1/perp.py` `POST /orders`)**:`PerpOrderPlaceIn` 加 `margin_mode` 字段(默认
  isolated · 零回归),路由按模式分派到逐仓 / 全仓引擎。
- **G5 preset 启用**:`schemas/bot_preset.py` 的 `BotPresetUpdate` 放开 `perp_margin_mode ∈ {isolated, cross}`;
  `bot-order-preset-section.tsx` 的「全仓(即将支持)」灰显 chip 变可选。
- **持仓展示**:`GET /virtual/perp/positions` 给全仓仓位返回账户级保证金率 / 账户级强平价(估算)而非每仓 liq。

---

## 6. 零回归(铁律)

- 逐仓引擎核心函数:**0 改动**(全仓走新增函数)。
- 逐仓持仓数据:**0 改动**(全仓是新行 margin_mode='cross';现有行不动)。
- 逐仓强平 worker:**仅加 `margin_mode='isolated'` 过滤**(对现有全 isolated 行为零影响);单测守护双向不串。
- 资金费 worker:**0 改动**(payment 公式 + 扣 cash_balance 对两种模式通用)。
- 网页/bot 下单默认 isolated → 不选 cross 的用户行为完全不变。
- 自验门(每期):ruff/mypy/pytest + 迁移 up/down/up + 全量回归 + cross/isolated 互不干扰测试。

---

## 7. 风险点 + 测试覆盖思路

| 风险 | 缓解 / 测试 |
|---|---|
| **R1 逐仓 worker 误杀全仓仓**(liq_price=0 恒真) | 3.3 强制加 margin_mode 过滤 · 单测:逐仓 worker 扫到 cross 仓**不动**它 |
| **R2 全仓强平算法边界** | 单测矩阵:① 单全仓仓临界(equity 恰 = mm)② 多全仓仓共担(一个亏拖累全部)③ 全平 vs 分级 ④ 穿仓地板(equity<0 钳 0)⑤ 同时多仓该强平的顺序(方案 B)⑥ 资金费扣到负后是否触发(应不直接触发,按保证金率判) |
| **R3 可用保证金计算错** | 单测:开仓占用、加仓、部分平仓后可用回升、逐仓+全仓混持时 cash_balance 归属 |
| **R4 cross/isolated 同 symbol 冲突** | 单测:有 isolated BTC 活仓时不能开 cross BTC(模式冲突拒单);反之亦然 |
| **R5 并发**(全仓 worker 强平 vs 用户手动平 vs 资金费) | 全仓 worker 也 `SELECT … FOR UPDATE`;账户级强平须锁该账户全部 cross 仓(防中途变化) |
| **R6 迁移**(enum 改 String / 加值) | up/down/up 实测 + 逐行审 + 不碰现有行验证 |
| **R7 价源缺失** | 沿用「缺 mark 跳过不误杀」;全仓某仓缺 mark 时账户保证金率怎么算(保守:跳过该账户本轮 or 用上次?DP) |

---

## 8. 分期建议(模块大,务必拆期 · 每期 feature 分支 + 严格审)

| 期 | 范围 | 高风险点 |
|---|---|---|
| **MC-1** | 数据模型 + 迁移(margin_mode 放开)+ 逐仓 worker 加过滤 + 隔离单测(双向不串) | 迁移逐行审 · worker 过滤是唯一碰现有运行码 |
| **MC-2** | 全仓核心引擎(`open/close_cross_position` + 共享保证金会计 + 可用校验)+ 单测 | 新增函数,不碰逐仓核心 |
| **MC-3** | 全仓强平(account-level worker + 强平算法 + 边界单测矩阵) | 全仓强平算法 = 最难,边界用例最多 |
| **MC-4** | 接入:网页下单 margin_mode + bot G4 + G5 preset 放开 cross | 默认 isolated 零回归 |
| **MC-5** | 真机走查(开全仓→加仓→部分平→共担强平→资金费)+ 0027 收尾 | 端到端 |

---

## 9. 决策点 · 最终结论(产品方拍板 · 2026-05-28)

> 10 个决策点全部拍板,结论如下。本表是后续 MC-2~MC-5 实现的契约,不得偏离。

| # | 决策 | **最终结论** | 落地期 |
|---|---|---|---|
| **DP-1** | 是否允许同时持有逐仓 + 全仓 | **① per-symbol 模式** —— 不同 symbol 可不同模式,同 symbol 同时只一种(仿 Binance) | MC-4 |
| **DP-2** | 全仓强平方式 | **① 全账户一次性全平** —— equity ≤ Σ维持保证金 → 当前账户全部全仓单一次性平掉(教学最简) | MC-3 |
| **DP-3** | 全仓分级强平顺序 | **作废** —— DP-2 选①(一次性全平),不存在分级,本决策点不适用 | — |
| **DP-4** | 逐仓 ⇄ 全仓资金互转 / 调整保证金 | **① 本期不做** —— 开仓后保证金共担池固定,不支持加/减保证金、不支持已有仓位改模式 | 全 MC 期内不做 |
| **DP-5** | margin_mode 存储 | **② 改 `String(16)`** —— 可逆迁移,避开 `ALTER TYPE ADD VALUE` 不可逆 + 锁表;存量归一为小写 `isolated` | **MC-1(本期)** |
| **DP-6** | 全仓维持保证金率 | **① 沿用逐仓 0.005 全局** —— 与逐仓同一常量 `MAINTENANCE_MARGIN_RATE`,不引入分档表 | MC-2 |
| **DP-7** | 同 symbol 是否允许逐仓 + 全仓并存 | **① 否** —— 同 symbol 同账户同时只一种模式(与 DP-1 配套约束) | MC-4 |
| **DP-8** | 全仓穿仓(equity < 0) | **① 地板到 0,平台虚拟承担** —— 与逐仓穿仓处理一致,账户权益不记负债 | MC-3 |
| **DP-9** | 全仓某仓缺 mark 价时 | **① 本轮跳过该账户强平判定** —— 任一全仓仓位缺 mark 即整账户本轮不判强平(保守不误杀) | MC-3 |
| **DP-10** | MC 分期是否按 §8 | **采纳** —— 按 §8 五期(MC-1 迁移+隔离 → MC-2 全仓引擎 → MC-3 全仓强平 → MC-4 接入 → MC-5 走查) | — |

**结论提炼(给实现期当宪法用)**:per-symbol 模式;全仓 = 共担保证金池(`cash_balance`)+ 账户级
一次性全平 + MMR 0.005 + 穿仓地板到 0 + 缺价跳过整账户;不做模式互转/调保证金;`margin_mode` 走
`String(16)`。

---

## 10. 备注
§9 已拍板,本文转 Approved。后续按 §8 分期、每期 feature 分支 + 严格审(迁移逐行审 · 引擎核心碰不得 ·
改动严格隔离)落地。MC-1 已动工(`feat/m2c-cross-mc1`):仅 `margin_mode` 字段 Enum→String + 逐仓强平
worker 加一行 `margin_mode='isolated'` 过滤 + 预定义(不启用)`MarginMode.CROSS`,**不含任何全仓
开仓/计算/强平逻辑**。
