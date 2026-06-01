# 港股阶段二 范围梳理 · 前端行情/详情页只读展示

> 性质:**纯梳理 · 不动代码**。供产品负责人确认阶段二范围,确认后分单元开工。
> 日期:2026-06-01 · 前置:阶段一数据层已上线(生产 CH:cn 6881 / us 7615 / crypto 17828 / **hk 600**,港股数据真落库 · yfinance 降级走通)。
> 依据:ADR 0034 §7 阶段二「市场维度 ~15-20 处 + 行情/自选/持仓**只读**」· 板块榜单/下单/AI 留阶段三/四。

---

## TL;DR

- 阶段二 = **让港股 K 线在前端真正显示**:港股详情页(看 K 线+缠论)+ 港股行情页(策展池列表入口)+ 市场维度补全。
- ★ **详情页复用度极高**:`SpotMainChart`(K线+缠论+指标)港股**直接可用**(数据已通),只需扩 `market` 类型 `'cn'|'us'→ +hk`。
- ★★ **关键边界**:港股详情页**必须 gate 掉 AI 决策卡 + 下单区** —— `decision-card?market=hk` 后端 technical agent prompt 无 hk 键会 **500**;下单是阶段三(每手逻辑)。阶段二**只「看」(K线+缠论),不 AI、不下单**。
- 半成品分支 `feat/hk-phase1-config` **市场维度部分能并入**(HKD 格式/钱包/自选/搜索/切换器 Tab),但 hk-market 占位逻辑要替换、详情页要新建。
- 工作量 ~2-3 单元,比阶段一轻(复用现货展示)。

---

## 1. 阶段二要做什么(盘点)

| 项 | 现状 | 阶段二做法 |
|---|---|---|
| **港股详情页** `/hk-preview` | ❌ 无 | 新建路由壳(照 `cn-preview/page.tsx` 3 行)+ 复用 `SpotDetail`(扩 hk + gate AI/下单) |
| **港股行情页** `/hk-market` | 占位 coming-soon(config 分支) | 升级为**策展池 18 只简化列表**(名称+最新价+涨跌→点进详情)· 全榜单 `MarketHomePage` 留阶段四 |
| **市场切换器** | config 加了 hk Tab,但 `hk→占位页` | 改:hk → 真实行情页/详情页 |
| **市场维度 ~15-20 处** | 部分在 main(Market 类型/MARKETS)+ config(HKD/钱包/自选/搜索) | 并入 config + 补缺口 |

**市场维度 hk 缺口盘点**(ADR 0034 §4 的 ~15-20 处):
- ✅ 已在 main:`Market` 类型 + `MARKETS`(packages/shared)· hk_pool · 港股日历状态机
- ✅ config 分支已做:HKD 格式(`format-money`/`fees`)· 钱包 hk(`wallet-section`)· 自选 hk(`watchlist-*`)· 搜索 hk(`symbol-search-dialog`)· 切换器 hk Tab
- ❌ 待补:`SpotDetail`/`SpotMainChart`/`SpotHeader` 的 `market` 类型扩 hk · symbols API 返 hk 策展池 · 行情页列表 · 切换器 hk 跳转改向

## 2. ★ 半成品分支 feat/hk-phase1-config 评估(能否用)

**做了什么**(11 文件):占位期前端 —— 让 UI「认识」港股(切换器 Tab + HKD 格式 + 钱包/自选/搜索的 hk 维度)+ hk-market coming-soon 占位页。

| 部分 | 能否用 | 说明 |
|---|---|---|
| HKD 格式(`format-money`/`fees`)· 钱包 hk · 自选 hk · 搜索 hk | ✅ **能并入** | 市场维度只读配置,做对了,阶段二正好要 |
| 切换器加 hk Tab | ✅ 并入 | 但跳转逻辑要改(见下) |
| `market-switcher` 的 `m==='hk' → /hk-market 占位页` | ⚠️ **要改** | 数据已上线 → 改成进真实行情页/详情页(去掉「不进工作台」的占位 guard) |
| `hk-market/page.tsx` coming-soon 占位 | ⚠️ **要替换** | 占位 → 策展池简化行情页 |
| 港股详情页 `hk-preview` | ❌ **没做** | config 分支不含,要新建(复用 SpotDetail) |

**结论**:config 分支**市场维度配置(~一半前端杂活)能并入省事**,但**占位逻辑要替换 + 详情页要新建**。建议:把 config 的市场维度改动 cherry-pick / 并入阶段二分支,占位页 + 切换器跳转重写,不直接整分支合(它是占位期状态)。

## 3. 复用度评估(港股=股票现货,与 cn/us 最像)

| 组件 | 复用度 | 改动 |
|---|---|---|
| **`SpotMainChart`**(K线+缠论+指标) | **~95%** | 只扩 `market: 'cn'|'us' → +hk`(line 43)· **港股数据已通,缠论/K线直接可用** |
| **`SpotDetail`**(详情页编排) | **~80%** | 扩 market 类型 + DEFAULTS 加 hk(00700)+ ★ `market==='hk'` 时 gate AI 卡 + 下单区 |
| **`SpotHeader`** | ~85% | 扩 market 类型 hk + HKD 标签 |
| 详情页路由 `hk-preview/page.tsx` | 新建 | 照 `cn-preview` 3 行(`<SpotDetail market="hk"/>`) |
| 行情页 `hk-market` | 中 | 策展池简化列表(复用列表行组件)· 全榜单 `MarketHomePage` 阶段四 |
| 市场维度(HKD/钱包/自选/搜索) | config 已做 | 并入 |

**总复用度:详情页极高(港股就是股票现货 K 线展示),行情页中(简化列表)。**

## 4. ★ 边界(只读 · 不交易 · 不 AI)

- **港股 = 行情展示 · 只读 · 不可交易**:阶段二只「看」(K线+缠论+指标),**不做下单**(下单是阶段三 · 每手 board lot 逻辑)。
- ★★ **详情页必须 gate 掉两块**(否则炸 / 越界):
  - **AI 决策卡**(`AiDecisionCard`):`decision-card?market=hk` 后端 technical agent `_system_prompt` dict 只有 cn/us/crypto → **market=hk 会 KeyError/500**。港股 AI 是阶段三/四。→ 详情页 `market==='hk'` 时**不渲染 AI 卡**。
  - **下单区**(`SpotOrderPanel`):港股下单阶段三。→ `market==='hk'` 时**不渲染**(或显示「港股交易即将上线」只读提示)。
- **可用**:`SpotMainChart` 的 K线 + **缠论**(`/analysis/chan?market=hk` 纯算法不依赖 prompt + 数据已通 → 港股缠论可用)+ klinecharts 内置指标。
- 复用现有展示组件、不碰交易/AI 红线 · 全程虚拟。

## 5. 分单元建议(独立验收粒度)+ 工作量

| 单元 | 内容 | 复用/新建 | 风险 | 验收点 |
|---|---|---|---|---|
| **单元1 · 后端只读补全**(小) | symbols API 返 hk 策展池(`/symbols?market=hk` → hk_pool)· 确认 `/market/kline?market=hk`(已通)· chan?market=hk 可用 | 小补 | 低 | curl symbols/kline/chan?market=hk 都返数据 |
| **单元2 · 详情页**(中 · 核心) | `SpotDetail`/`SpotMainChart`/`SpotHeader` 扩 hk + ★gate AI 卡/下单 + `hk-preview/page.tsx` + 切换器 hk→详情 | 复用 SpotMainChart ~95% | 中(碰共享组件,守 cn/us 零回归) | 港股详情页看 K线+缠论 · 无 AI 卡/下单 · cn/us 详情页零回归 |
| **单元3 · 行情页 + 市场维度**(中) | hk-market 占位→策展池简化列表 + 并入 config 的 HKD/钱包/自选/搜索 + ★多入口覆盖 | config 并入 + 列表 | 中 | 行情页列表→点进详情 · ★所有 hk 入口真机 |
| (阶段三/四) | 港股下单(每手)· 港股 AI · 全榜单 MarketHomePage | — | — | 后续 |

**工作量**:~2-3 单元,**比阶段一轻**(详情页复用现货展示极高,市场维度 config 半成品省事)。

## 6. ★ 多页面入口清单(验收必须逐个覆盖 · 吸取漏接教训)

港股阶段二该出现的**所有入口**(CLAUDE.md 多页面铁律,逐个真机验):
1. **市场切换器**(顶部 `MarketSwitcher` · 港股 Tab → 进真实页,不再占位)
2. **/hk-market 行情页**(策展池列表)
3. **/hk-preview 详情页**(K线+缠论 · 无 AI/下单)
4. **自选**(`watchlist` · 加港股自选项 · 列表展示)
5. **搜索**(`symbol-search-dialog` · 搜港股标的)
6. **账户/钱包**(HKD 余额只读展示 · config 做了)
7. **workbench 工作台**(★ 待定:港股进不进工作台 K 线流?config 当前「hk 不进工作台」· 阶段二可接 K 线只读,或留阶段三随下单一起 —— **拍板点**)

> 验收铁律:列出上述入口清单 → **逐个真机验**(港股 Tab 点进有内容、详情页 K线显示、自选/搜索能加能搜、cn/us/crypto 在这些入口零回归)· 不许验完不到清单全部就报「全覆盖」。

---

## 待产品负责人确认 / 拍板点

1. **行情页范围**:阶段二 hk-market = **策展池 18 只简化列表**(建议)· 还是直接复用全榜单 `MarketHomePage`(重 · 含指数/板块/5500只 · 建议留阶段四)?
2. **★ 详情页 AI 卡 / 下单 gate 方式**:`market==='hk'` 时**完全不渲染** AI 卡 + 下单区(建议)· 还是显示「港股 AI/交易即将上线」只读占位?
3. **workbench 工作台**:港股阶段二**接不接**工作台 K 线流(只读)· 还是留阶段三随下单一起接?(config 当前 hk 不进工作台)
4. **config 分支并入方式**:cherry-pick 市场维度改动到阶段二分支(建议)· 还是先合 config 再改?
5. **分单元节奏**:单元1(后端只读)→ 单元2(详情页 · 核心)→ 单元3(行情页+市场维度)· 是否这个顺序?

> 本轮只梳理,未动代码。产品负责人确认范围 + 拍板 5 点后,按单元开工(每单元 feature 分支 + 审 + ★多入口真机验 + 合 main)。
