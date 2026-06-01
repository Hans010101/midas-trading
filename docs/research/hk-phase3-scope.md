# 港股阶段三 完整方案 · 详情页配齐 AI决策卡 + 策略信号 + 下单(含每手股数)

> 性质:**纯调研 · 不动代码**。供产品负责人确认完整方案,确认后分单元单线稳扎稳打做。
> 日期:2026-06-01 · 目标:港股详情页(`/hk-preview`)与 A股/加密统一 —— AI 决策卡 + 形态A 策略信号 + 虚拟下单(按手)。
> ★★ 第一红线(焊死):港股下单**只走现有虚拟下单引擎,全程虚拟,绝不接真实交易通道**。

---

## TL;DR

- 三块:**① 下单(最硬)· ② AI 决策卡 · ③ 策略信号**。AI 卡/策略是「解 gate + 后端加 hk 配置」(中),下单是真硬骨头(每手股数核 HKEX + 按手取整 + 虚拟引擎)。
- **每手股数**:akshare **无可靠 board lot 接口**(实测确认),港交所官方(HKEX)才权威 → 下单**先限策展池(18 只,lot 逐一核 HKEX)**,全市场 lot 难核留后续。
- **虚拟红线焊死**:港股下单复用 `place_market_order`(虚拟引擎,写 VirtualAccount,全程虚拟)+ 二次确认模态(现成)。
- 分 **3 单元单线**(1 AI 卡 → 2 策略 → 3 下单),下单单元最重,拆 3a 后端 / 3b 前端。

---

## 1. ★ 下单(最硬 · 港股交易规则 · 红线)

**现状(虚拟引擎已就绪,港股要补 3 处)**:
- `virtual_trading/engine.py` `place_market_order(req)`:虚拟引擎,`market: str` 参数,`get_market_price(symbol,market)` → `apply_slippage` → `notional=quantity*fill_price` → `calc_commission`。**全程虚拟(写 VirtualAccount)· 港股直接复用(market='hk')**。
- ⚠️ **缺①佣金/滑点**:`fees.py` `COMMISSION_RATES`/`SLIPPAGE` 只 cn/us/crypto,**无 hk** → `commission_rate('hk')` KeyError。要加 hk 港股佣金率(港股佣金 + 印花税 0.1% + 交易费,虚拟可简化为一个综合费率)。
- ⚠️ **缺②按手取整**:`place_market_order` 用 `quantity` 直接成交,**没有按手取整**。港股**按手交易(board lot)** → 要加 `floor(quantity/lot)*lot`(不能买零散股)。lot 取自 hk_pool。
- ⚠️ **缺③每手股数准确性**(见下,最关键)。

**★ 每手股数 board lot 怎么拿准**(产品负责人红线:核港交所官方,别瞎填误导):
- `hk_pool.py` lot 字段是**种子值**(腾讯100/汇丰400…手填,注释明写「待核 HKEX」)。
- akshare **无专门 board lot 接口**(WebSearch + 之前侦察确认,只有行情/财务指标)。
- ✅ **港交所官方(HKEX)权威**:HKEX 官网「上市证券一览」含每只 board lot,可下载 securities list(CSV)。
- **建议**:港股下单**先限策展池(18 只)** → lot 逐一核 HKEX 官网(18 只人工可行,半天),`hk_lot_size()` 返准确值;策展池外的 `lot=None` → 「该标的暂不可下单」(已有兜底)。全市场 lot 留后续(找 HKEX 批量数据再开放)。

**其他**:港股 **T+0**(无 A股 T+1 锁定)· 二次确认模态(`SpotOrderPanel` pending + 确认下单模态,**现成复用**)· VirtualAccount(market='hk')账户需建(见 §6 执行点)。

## 2. AI 决策卡(后端加港股支持)

**`decision-card?market=hk` 500 根因(已定位)**:
- `agents/technical.py` `_system_prompt(market)` dict 只 `cn/us/crypto`(line 46-48)→ **`[hk]` KeyError**。
- `ai/cache.py` `_TTL_BY_MARKET` dict 只 cn/us/crypto(line 31-33)→ **`[hk]` KeyError**。
- `ai/actionable.py` 等按 market 分支(`is_crypto` 等)需确认 hk 落点。

**要加**:
- `_SYSTEM_HK`(照 `_SYSTEM_CN/US`):港股 prompt = **T+0 · 无单日涨跌停 · 复权口径「前复权」(qfq,对齐 hk_source)· 关注 board lot**。
- `technical._system_prompt` + `cache._TTL_BY_MARKET`(hk: 4h,同 cn/us)+ actionable hk 落点 各 dict 加 hk。
- **复用**:整条 AI 管线(`workflow.analyze_technical` + LLM + 指标快照 TechnicalSnapshot)· 港股特殊性仅 prompt 口径(T+0/无涨跌停/前复权)+ TTL。**复用度高**。
- 详情页**解 gate AI 卡**:`SpotDetail` `market!=='hk'` 才渲染 aside → 改为 hk 也渲染 `AiDecisionCard`(阶段二 gate 的就是这块)。

## 3. 策略信号(港股接策略引擎)

**现状**:阶段二 gate 掉了港股策略(`spot-main-chart.tsx:108/122` `{market !== 'hk' && <StrategyOverlay/Panel>}`),且后端 strategy 端点没注入 hk(单元1「decision-card/strategy 不注入 hk」的边界)。
**要改**:
- 后端:`analysis.py` strategy 端点(strategy-signals / strategy-recommend)的 `_source_for` **注入 hk**(单元1 只给 chan 注入了)→ 港股能回源跑 `strategy_signals`(金叉/RSI/布林,复用,hk kline 已有)。
- 前端:`spot-main-chart.tsx` **去掉 `market !== 'hk'` 两处 gate** → 港股渲染 StrategyPanel/StrategyOverlay(共享组件,自动出信号点+历史列表,接批1)。
- **复用度高**(strategy_signals 引擎 market 无关,hk kline 已通)。

## 4. 分单元(单线 · 一个一个来 · 不堆)

| 单元 | 内容 | 复用/新建 | 轻重 | 碰红线 |
|---|---|---|---|---|
| **单元1 · AI 决策卡** | _SYSTEM_HK + technical/cache/actionable 各 dict 加 hk + 详情页解 gate AI 卡 | 复用 AI 管线 90% | **中** | 无下单 · AI 输出带「仅供参考」(现有) |
| **单元2 · 策略信号** | strategy 端点 `_source_for` 注入 hk + 前端去 2 处 gate | 复用 strategy_signals + 批1 展示 | **中** | 纯展示 · 不下单 |
| **单元3 · 下单(最硬)** | 拆 3a/3b ↓ | | **重** | ★★虚拟引擎 + 二次确认 + 每手股数核官方 |
| · 3a 后端 | ★核 HKEX 每手股数(策展池 18 只)+ fees 加 hk + 按手取整 `floor(qty/lot)*lot` + 后端下单 virtual 端点 hk + VirtualAccount hk 账户 | 复用 place_market_order(虚拟)| 重 | 虚拟焊死 + lot 核官方 |
| · 3b 前端 | SpotOrderPanel +hk(defaultQty 按 lot · 二次确认复用 · T+0)+ 详情页解 gate 下单区 | 复用 SpotOrderPanel + 确认模态 | 中 | 二次确认必经 |

**依赖顺序**:单元1(AI 卡)、单元2(策略)互相独立(都「解 gate + 后端配置」)· 单元3(下单)独立但最硬(每手股数前置)。**建议单线:1 → 2 → 3**(先轻后重,逐个验收)。

## 5. ★★ 红线核对(逐条)

1. **下单只走虚拟引擎,绝不接真实交易(第一红线)**:✅ 复用 `place_market_order`(写 VirtualAccount,全程虚拟,无任何真实券商通道)· 焊死,单元3 不引入任何真实下单路径。
2. **二次确认必经(防误触)**:✅ `SpotOrderPanel` 现成 pending + 「确认下单」模态,港股复用。
3. **每手股数核港交所官方(数据准确性)**:✅ akshare 无可靠 lot 源 → 核 HKEX 官网,下单**先限策展池(lot 核准)**,未核标的 `lot=None` 不可下单(不瞎填误导)。
4. **AI/策略输出带「仅供参考,不构成投资建议」**(项目红线):AI 卡复用现有 disclaimer 口径。

## 6. 多页面 + 产品负责人执行点

**多页面覆盖**(铁律):港股 AI 卡 + 下单只在 `/hk-preview`(SpotDetail market=hk · 阶段二 gate 的 aside 解开)。**解 gate 只改 hk 分支(`market!=='hk'` → 含 hk),cn/us/crypto 零影响**(git diff 守)。
**★ 需产品负责人在服务器执行 / 拍板的点**:
- **DB · 港股虚拟账户**:`VirtualAccount` 按 (user_id, market) 建。要确认 hk 账户怎么来(注册时建 cn/us/crypto 的逻辑是否含 hk · 还是 ensure 自动建 · 还是要 alembic 迁移/数据初始化)。**下单单元(3a)前必须确认,可能需服务器执行迁移或账户初始化**。
- **每手股数核 HKEX**:策展池 18 只 board lot 逐一核港交所官网(人工 · 产品负责人或我核 · 落 hk_pool.py)。

---

## 待产品负责人确认 / 拍板

1. **下单范围**:先限**策展池 18 只**(lot 核 HKEX · 数据准 · 红线稳)· 还是要全市场(lot 难核 · 需 HKEX 批量数据)?
2. **每手股数核法**:策展池 18 只人工核 HKEX 官网(建议)· 还是找 HKEX securities CSV 批量?谁来核(产品负责人 / 我)?
3. **港股佣金/费率**:港股虚拟费率怎么定(佣金 + 印花税 0.1% + 交易费综合一个率,对齐 cn/us 简化口径)?
4. **分单元顺序**:1 AI 卡 → 2 策略 → 3 下单(单线 · 建议)· 确认?
5. **VirtualAccount hk 账户**:下单单元前我先查清建账户逻辑(注册建 vs 自动 ensure vs 迁移),届时报你是否需服务器执行。

> 本轮只调研,未动代码。产品负责人确认范围 + 拍板后,分单元单线做(每单元 feature 分支 + 自测 + 生产验 · 下单单元额外守虚拟红线 + 二次确认 + 每手股数核官方)。
