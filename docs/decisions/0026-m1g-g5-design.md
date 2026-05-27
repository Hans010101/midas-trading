# 0026 · M1-G G5 设计方案(后台预设 + 告警规则配置 + 默认推荐规则 + bot 品牌)

## 状态

**Draft · 待产品方审**(2026-05-27)· 0025 §9 G5 的详细设计 · 仅方案,不含实现代码。

承接:0025(Telegram 迷你交易终端)· G1/G2a/G2b/G3/G4 均已上线 main。G5 是 0025 §9
的收尾实现期(下一期 G6 = 真机走查 + 0025 收尾)。

> 红线(贯穿):全程虚拟资金,bot 下单只走虚拟引擎;一切输出带「仅供参考,不构成投资
> 建议」;不碰已上线引擎核心(只新增调用入口 / 接入点)。

---

## 0. 范围(0025 §9 G5)

| # | 子项 | 形态 |
|---|---|---|
| 1 | **后台预设配置** | 网页设置页配 bot 下单默认参数(杠杆 / 名义额 / 逐仓)· **新表 + 迁移** |
| 2 | **bot 下单改读用户预设** | G4 现用安全默认常量 → 接入用户预设(`order.py` 单一接入点) |
| 3 | **告警规则配置 UI(网页)** | 从 20 个指标配规则、设阈值(复用 G2b CRUD,前端纯新增) |
| 4 | **告警规则默认推荐方案** ⚠️ | 开箱即用的一套推荐规则(产品方审重点 · §5) |
| 5 | **bot 内告警规则配置** | DP9「both」的 bot 侧:查看 / 启停 / 一键应用推荐(轻量,非全量编辑) |
| 6 | **bot 品牌(D9)** | 头像 / 简介 / 命令菜单确认(多为 @BotFather 配置) |

---

## 1. 后台预设配置(bot 下单默认参数)

### 1.1 新建存储表 `bot_order_preset`(per-user · lazy)

跟 `notification_config` 同模式:`user_id` 既 PK 又 FK,行不存在 = 用默认值。

| 列 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `user_id` | UUID PK · FK→user.id ondelete CASCADE | — | 一用户一行 |
| `perp_leverage` | Integer | `3` | 永续杠杆 · 校验 1–20(对齐引擎 MIN/MAX_LEVERAGE) |
| `perp_notional_usdt` | Numeric(20,4) | `100` | 永续每单名义额(USDT)· margin = 名义/杠杆 |
| `perp_margin_mode` | String(16) | `'isolated'` | **本期固定逐仓**;字段预留,将来 M2-C 补全仓后加 `'cross'` |
| `spot_notional_cny` | Numeric(20,4) | `10000` | A股每单名义额(CNY) |
| `spot_notional_usd` | Numeric(20,4) | `1000` | 美股每单名义额(USD) |
| `created_at` / `updated_at` | DateTime(tz) | now() | — |

> 默认值与 G4 的 `order.py` 常量(`DEFAULT_PERP_LEVERAGE=3` / `DEFAULT_PERP_NOTIONAL_USDT=100`
> / `DEFAULT_SPOT_NOTIONAL cn=10000 us=1000`)**完全一致** —— 用户没配 = G4 行为零变化。

### 1.2 PG 迁移(纯新增 · 可逆)

- `down_revision = a7b8c9d0e1f2`(当前 head · G2b 的 alert_rule;G3/G4 无迁移)。
- `upgrade`:`create_table('bot_order_preset', …)`。`downgrade`:`drop_table('bot_order_preset')`。
- 纯加表,不碰任何现有表 / 数据 —— 风险等级同 G2b 的 alert_rule。

### 1.3 REST(新增 · CurrentUserDep)

- `GET /bot-preset` → 返回用户预设;无行则返回**默认值**(不 lazy-create,读不写)。
- `PUT /bot-preset` → upsert · 校验:`1 ≤ perp_leverage ≤ 20`、各名义额 `> 0`、`perp_margin_mode ∈ {isolated}`(本期)。

### 1.4 网页 UI

设置页(`/settings`)新增 **「Bot 下单默认参数」section**(`BotOrderPresetSection`):

- 永续杠杆:数字输入 / slider(1–20)。
- 永续每单名义额(USDT)。
- A股每单名义额(CNY)、美股每单名义额(USD)。
- 逐仓模式:显示「逐仓」+ disabled「全仓(即将支持)」—— 对齐 DP5 模式预留位。
- 保存按钮(成功帝王金 toast / 失败中国红)· 视觉系统合规 · 带「下单全程 VIRTUAL·模拟」说明。

---

## 2. bot 下单接入用户预设(唯一接入点)

G4 的 `app/services/bot/order.py` 现在从模块常量取参数。G5 改为读用户预设:

- 新增 `async def _load_preset(db, user_id) -> PresetValues`:查 `bot_order_preset`,无行 →
  回退到现有默认常量(dataclass)。
- **接入点(仅这几处,引擎仍零改动)**:
  - `build_preview()`:算名义 / 杠杆处 → 用 `_load_preset`。
  - `_exec_perp()`:`leverage` / `margin = 名义/杠杆` → 用预设。
  - `_resolve_spot_order()`:开仓名义 → 用预设(按市场取 cny/usd)。
- **零回归**:无预设行 = 默认常量 = G4 现行行为;有预设 = 用其值。下单引擎、确认流程、限流、
  身份校验全不变。
- `order.py` 的函数签名已带 `db` + `user_id`,接入不需要改 router / 引擎,改动局限在 `order.py` 内。

---

## 3. 告警规则配置 UI(网页 · 复用 G2b CRUD)

G2b 已上线接口(直接复用,后端零改动):
- `GET /alert-rules/indicators`(20 指标目录 · 公开)、`GET /alert-rules`、`POST`、`PATCH /{id}`、`DELETE /{id}`。

设置页新增 **「告警规则」section**(`AlertRulesSection`):

- **指标选择**:按分类分组展示 20 指标(价格 / 成交量 / 技术 / 缠论 / crypto 衍生 / crypto 全局 /
  市场结构),每个带 label + 适用市场 + 是否需 symbol(来自 indicators 目录的元信息)。
- **添加规则表单**:选指标 → 市场(+ per-symbol 指标需 symbol,带 Cmd/Ctrl+K 同款搜索)→
  算子(> / ≥ / < / ≤)→ 阈值 → timeframe(技术 / 价格类)。前端按目录元信息动态显隐 symbol / timeframe。
- **规则列表**:启用/停用 toggle(`PATCH enabled`)、删除(`DELETE`)、显示「指标 算子 阈值」。
- **DP6 上限 20 条**提示(满 20 禁用「添加」)。
- 新增 `lib/api/alert-rules.ts` + `hooks/use-alert-rules.ts`(TanStack Query · retry 0)· 纯前端。

> 指标数量更正:0025 提到「17 个指标」,**registry 当前实为 20 个**(G2b 全 DP2 落地后的数,
> 以代码 `REGISTRY` 为准)。UI 按目录接口动态渲染,不硬编码数量。

---

## 4. ⚠️ 告警规则【默认推荐方案】(产品方审重点)

### 4.1 设计原则

1. **少而精,防告警疲劳**:推荐集控制在 ~9 条以内,只覆盖最普适的「超买超卖 + 情绪极值 +
   市场转弱」。规则越多噪音越大,新手反而更懵。
2. **优先无需 symbol 的市场级 / 全局指标** —— 真·开箱即用,不依赖用户自选。
3. **per-symbol 规则绑现有 3 个预填 demo 自选**(`BTC/USDT` / `NVDA` / `600519`)—— 与
   watchlist 预填一致,用户有直观对象;可随时改 / 删。
4. **避开与旧 `price_alerts ±5%` 重复**(DP13 旧任务仍在跑)→ 默认**不**加「价格涨跌幅 ±5%」。
5. 阈值用业界经典值;crypto 波动大,RSI 用更极端的 75/25。

### 4.2 推荐规则集(提案 · 共 9 条)

**Tier 1 · 全局 / 市场级(无需 symbol · 自动适用)**

| 市场 | 指标(key) | 算子 | 阈值 | 理由 |
|---|---|---|---|---|
| crypto | 恐贪指数 `fear_greed` | `<` | `20` | 极度恐慌区,历史常对应阶段性底部 → 「别人恐惧时关注」 |
| crypto | 恐贪指数 `fear_greed` | `>` | `80` | 极度贪婪,过热 / 回调风险 → 「别人贪婪时谨慎」 |
| cn | A股上涨家数占比 `cn_breadth_up_ratio` | `<` | `30` | 仅 <30% 个股上涨 = 普跌、情绪转弱,大盘级风险提示 |

**Tier 2 · per-symbol(绑 3 个 demo 自选 · RSI 超买超卖)**

| 标的 | 市场 | 指标 | 算子 | 阈值 | timeframe | 理由 |
|---|---|---|---|---|---|---|
| NVDA | us | `rsi_14` | `>` | `70` | 1d | 经典超买线 |
| NVDA | us | `rsi_14` | `<` | `30` | 1d | 经典超卖线 |
| 600519 | cn | `rsi_14` | `>` | `70` | 1d | 同上 |
| 600519 | cn | `rsi_14` | `<` | `30` | 1d | 同上 |
| BTC/USDT | crypto | `rsi_14` | `>` | `75` | 1d | crypto 波动大 → 75/25 更稳 |
| BTC/USDT | crypto | `rsi_14` | `<` | `25` | 1d | 同上 |

> **更精简的备选**(若产品方嫌 9 条多):只留 Tier 1 的 3 条 + 给用户自选**第一个**标的配
> RSI 70/30 两条 = 5 条。两套都列出,产品方挑(DP-G5-2)。

### 4.3 种入方式(DP-G5-3)

- **方案 B(推荐)· 用户主动「一键应用推荐规则」**:告警页放一个按钮 → 调
  `POST /alert-rules/apply-recommended`(新增端点,内部用后端常量 `RECOMMENDED_ALERT_RULES`
  批量创建,跳过已存在 / 超 20 上限的)。**无需用户表加标志位、无额外迁移**,尊重用户选择。
- 方案 A · 注册后自动种入(类似 watchlist 预填 demo):需要 user 加 `alert_rules_seeded`
  布尔列(+ 一个小迁移),且「自动给用户建规则」更激进。
- 方案 C · both。
- **建议 B**;A/C 由产品方定。`RECOMMENDED_ALERT_RULES` 作为代码常量(单一事实源,bot 与
  网页共用)。

---

## 5. bot 内告警规则配置(DP9 "both" 的 bot 侧)

bot 全量规则编辑(20 指标 × 算子 × 阈值,纯 inline 键盘)交互很重。G5 建议 bot 侧做**轻量**版,
重编辑留网页:

- 🔔 告警规则(G3 现为「请去网页配置」占位)→ G5 改为:
  - **查看**当前规则列表(指标 / 算子 / 阈值 / 启停)。
  - **启停** toggle(`PATCH enabled`)。
  - **一键应用推荐规则**(调同一 `apply-recommended`)。
  - (可选)**删除**单条。
- **不在 bot 里做**全量「新建任意指标规则」(留网页,体验更好)· 复用 G3 的会话态 + inline 键盘模式。
- DP-G5-6:bot 侧到底做到「查看+启停+推荐」还是再加「简单新建」,产品方定。

---

## 6. bot 品牌(D9)

名称 **「点金 Midas」已定**。其余确认项(多为 @BotFather 配置,产品方做):

| 项 | 建议 | 谁做 |
|---|---|---|
| 头像 | 用 M1-C 印章 logo(篆书「点金」朱文方印)· 中国红底 | 产品方 @BotFather `/setuserpic` |
| 简介(description / about) | 「点金 Midas · AI 多市场分析终端(A股/美股/加密)· 全程虚拟资金,仅供参考不构成投资建议」 | 产品方 @BotFather |
| 命令菜单(/ 提示) | `/start` 绑定 · `/menu` 功能菜单 · `/price <代码>` 查行情 | 代码侧 `setMyCommands`(可选 · 见下)或 @BotFather `/setcommands` |

- **代码侧可选增强**:在 `register_webhook_if_configured()`(启动期)顺带调一次
  `setMyCommands`,让命令菜单随代码同步、免手动 @BotFather 维护。小改动,DP-G5-5 定要不要做。

---

## 7. 数据模型变动 / PG 迁移 / 零回归

### 数据模型 / 迁移
- **新增 1 张表 `bot_order_preset`**(§1.1)· 纯新增可逆迁移(down_revision = `a7b8c9d0e1f2`)。
- 告警推荐规则:**不需新表**(复用 `alert_rule`;推荐集是代码常量 + 批量 INSERT)。
- 若选种入方案 A:user 加 `alert_rules_seeded` 列(+1 小迁移)。选 B 则**不需要**。

### 零回归
- 后台预设:无预设行 = 默认常量 = G4 行为;引擎、确认、限流、身份校验不变。
- 告警 UI:复用 G2b 接口(后端零改动),前端纯新增 section。
- bot 品牌:@BotFather 配置 + 可选 `setMyCommands`(不影响现有 webhook)。
- 不碰 G1–G4 已上线逻辑、不碰交易 / 通知引擎、不碰网页下单主链路。
- 自验门:ruff / mypy / pytest(后端)+ tsc / lint / build(前端)+ 迁移 up/down/up。

---

## 8. 决策点(产品方逐条拍板)

| # | 决策 | 选项 / 默认建议 |
|---|---|---|
| **DP-G5-1** | 后台预设默认值 | 杠杆 3 · 永续名义 100 USDT · A股 10000 CNY · 美股 1000 USD —— 是否合适? |
| **DP-G5-2** | 默认推荐规则集 | 采纳 §4.2 的 9 条?还是精简 5 条版?哪些开 / 关 / 调阈值? |
| **DP-G5-3** | 推荐规则种入方式 | **B 一键应用(建议)** / A 注册自动种入(+1 迁移)/ C both |
| **DP-G5-4** | bot 头像 / 简介 | 用印章 logo + 上述简介文案?(产品方 @BotFather 执行) |
| **DP-G5-5** | 命令菜单 | 代码侧 `setMyCommands`(随代码同步)还是 @BotFather 手配? |
| **DP-G5-6** | bot 内告警配置深度 | 查看+启停+一键推荐(建议)/ 再加 bot 内简单新建 |
| **DP-G5-7** | 后台预设 UI 落位 | 放 `/settings`(与通知/配色同页)还是 `/settings/wallet`(与资金同页)? |

---

## 9. 实施拆分建议(G5 真正开工时)

1. 后端:`bot_order_preset` 模型 + 迁移 + `GET/PUT /bot-preset` + pytest。
2. 后端:`RECOMMENDED_ALERT_RULES` 常量 + `POST /alert-rules/apply-recommended` + pytest。
3. 后端:`order.py` 接入 `_load_preset`(零回归测试:无预设=默认)。
4. 前端:`BotOrderPresetSection` + `AlertRulesSection` + api/hooks · tsc/lint/build。
5. bot:🔔 告警规则轻量配置(查看/启停/推荐)+ 命令菜单(可选)。
6. 自验 + push feature + 交付报告(高风险档:含迁移 → 逐行审 + 等审再挑 main)。

> 本文仅方案。产品方就 §8 决策点拍板后,按 §9 落地。
