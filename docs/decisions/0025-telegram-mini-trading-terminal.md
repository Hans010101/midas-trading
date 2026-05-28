# 0025 · Telegram 迷你交易终端(核心层 + 适配层)

## 状态

**Closed**(2026-05-28)· M1-G 全期(G1 / G2a / G2b / G3 / G4 / G5)实现完成并上线 main ·
产品方真机走查(G6:绑定→查询→预警→虚拟下单→告警一键推荐 全链路)通过 · 里程碑验收收口。
14 个决策点(DP1–DP14)见 §11。

> 后续打磨 backlog(M1-G G6 走查反馈 · 不在本里程碑内 · 归打磨期或独立小任务):
> **告警通知频次 / 降噪** —— 9 条推荐规则触发后 Telegram 信息密度偏高,需设计
> 逐规则冷却 / 全局安静时段 / 分指标类型默认冷却 的方案(`alert_rule.cooldown_sec` 已存在,
> 可作为逐规则冷却的起点;另需全局/分类层)。先登记,暂不做。

历史(实施期):14 个决策点拍板后按 §9 分期实施(G1 复用 `feat/m1g-g1-telegram-unified-bot`)。

**supersedes 0024**(0024「通知系统 v2」是把飞书通知迁到 Telegram 的窄方案;M1-G 已升级为「Telegram 迷你交易终端」,范围远大于 0024。0024 仍保留为历史 + 其 §3.1 binding 设计被本文复用。注:0024 + G1 代码目前在未合并分支 `feat/m1g-g1-telegram-unified-bot` 上,本文确认 G1 可直接作为本方案第一期基础 —— 见 §4。)

> 红线(产品 DNA · 不可破):**只虚拟资金交易,永不接真实下单**。bot 内一切下单走现有虚拟账户 + 虚拟引擎。所有行情 / 策略 / 交易输出必带「仅供参考,不构成投资建议」。推送 / 下单 emit 绝不阻塞核心链路。

---

## 1. 范围升级

M1-G 从「通知迁移」升级为「**Telegram 迷你交易终端**」—— 在 Telegram 里把点金的核心能力做深做透:

| # | 能力 | 说明 |
|---|---|---|
| ① | **定时扫描预警** | 按每个用户自己的自选 + 告警规则,周期扫描、命中推送 |
| ② | **交互式行情查询** | bot 里点/输交易对 → 返回该标的核心信息卡 |
| ③ | **inline keyboard 按钮界面** | 数据 / 自选 / 持仓 / 下单 / 策略 / K线 等按钮导航 |
| ④ | **bot 内虚拟下单** | 走现有虚拟账户 + 虚拟交易引擎(红线:绝不真实) |
| ⑤ | **可配置告警规则引擎** | 用户从「数据撑得住的指标清单」勾选规则 + 设阈值 |

**平台范围**:本期**只做 Telegram**,做深。微信不做(平台不开放)。**飞书本期不做,但架构留扩展位**(将来加飞书只新增适配层、核心层不动)。

**统一官方 bot**:产品方已建好,token 已就位(配置方式见 §7)。这点与 G1 一致。

---

## 2. 架构:平台无关核心层 + 平台适配层

### 2.1 关键发现(已核实代码,非推测)

现有所有交易 / 扫描 / 通知服务**都已是纯 `async def f(db, dto(user_id: UUID, ...))` 形式,不依赖 HTTP / session / FastAPI**:

- 现货下单 `virtual_trading/engine.py:place_market_order(db, PlaceOrderRequest(user_id, symbol, market, side, quantity, position_side), get_market_price)` → 返回 `VirtualOrder`(业务失败返回 `REJECTED` 不抛)· 价格 fetcher 注入 · 调用方 commit。
- 永续 `perp_engine.py:open_perp_position / close_perp_position(db, req(user_id, symbol, side, leverage, margin|quantity), get_mark_price)`(杠杆 1–20x)。
- 虚拟账户 `models/virtual.py:VirtualAccount`(per user×market 一行 · lazy create = 激活态 · 不存在则下单 REJECTED「虚拟资金未设置」· 余额用原子 `UPDATE...RETURNING`)。
- 派发 `notifications/dispatcher.py:dispatch(db, user_id, event)`(per-user · 各通道独立失败)。
- 扫描模板 `apps/worker/tasks/price_alerts.py`:beat 每 1min → 遍历全部 watchlist → 查 CH → 判定 → Redis 去重 → Celery → dispatch。

**结论**:核心层 = 把这些现成 service 函数封一层「facade」,由谁(web / bot)驱动都行。Telegram 只是第一个驱动方。

### 2.2 分层

```
┌─────────────────────────────────────────────────────────┐
│  适配层(平台特定)                                        │
│  Telegram adapter:webhook 入站(/start·命令·按钮回调)    │
│    · 出站 sendMessage/editMessageText · inline keyboard   │
│    · 绑定 UX(deep link + 二维码)· 消息渲染(MD/按钮)    │
│  [将来] 飞书 adapter:只实现出入站 + 渲染,core 不动        │
└───────────────▲─────────────────────────────────────────┘
                │ 平台中立接口(结构化入参 / 结构化结果)
┌───────────────┴─────────────────────────────────────────┐
│  核心层(平台无关)                                        │
│  · identity:chat_id↔user_id 解析(适配层提供 chat_id)    │
│  · query:symbol → 核心信息(复用 CH 读 + futures 指标)   │
│  · order:虚拟下单 facade(复用 engine / perp_engine)     │
│  · alert engine:规则定义 + 扫描 + 命中判定(新建)        │
│  · outbound:产出「给哪个 user 发什么结构化消息」          │
└───────────────▲─────────────────────────────────────────┘
                │ 复用,不改
┌───────────────┴─────────────────────────────────────────┐
│  既有 service:engine / perp_engine / dispatcher /         │
│  clickhouse 读 / crypto futures 指标 / watchlist           │
└──────────────────────────────────────────────────────────┘
```

- **抽象边界**:用 Python `Protocol`/抽象基类定义适配层接口(`render_*` / `send` / `parse_inbound`),Telegram adapter 实现之。core 只产出结构化数据(dataclass/Pydantic),不含任何 IM 字符串拼装。
- **outbound 抽象**:现有 `dispatch` 已是「per-user → 多通道」雏形;本期把「渲染」从「发送」中拆出 —— core 给 `NotificationPayload(structured)`,Telegram adapter 渲染成 Markdown,飞书 adapter 渲染成 card。

---

## 3. 告警规则引擎 · 指标可行性(逐项核实 · item 2 诚实结论)

**原则:能进规则清单的指标,后台数据必须撑得住。** 已逐项核对 ClickHouse 表 / 采集 worker / beat(证据见括注)。分三档:

### ✅ 现成可上(已历史存 ClickHouse · 扫描 worker 直接查、不打上游)

| 指标 | 来源 + 频率 |
|---|---|
| 价格 / %变动(日 & 盘中) | `kline` + 实时快照 `cn_spot_snapshot`(3min)/`us_spot_snapshot`(5min)/`crypto_ticker_24h`(10min)/`market_index_snapshot`(2min) |
| 成交量 | `kline.volume/amount` · 各 snapshot 表 |
| **加密 funding rate** | `crypto_funding_rate`(15min · TTL 60d) |
| **加密 OI(及 24h 变动)** | `crypto_open_interest`(5min · TTL 60d) |
| **加密多空比** | `crypto_long_short_ratio`(15min · 含 taker 买卖比) |
| **加密基差 / premium** | `crypto_premium_index`(1min · TTL 仅 7d) |
| 恐贪指数 | `crypto_market_overview.fear_greed`(6h) |
| CN 涨跌家数(市场宽度) | `cn_market_breadth`(A股时段 3min) |
| 板块涨跌 CN/US | `cn_sector_snapshot`(3min)/`us_sector_snapshot`(5min) |
| 指数点位 / % | `market_index_snapshot`(CN+US · 2min) |
| BTC 占比 / 总市值 | `crypto_market_overview`(30min) |

### ⚠️ 需补「计算接入」(数据源有 kline,只是没算/没存 · 扫描时现算 · 成本低)

| 指标 | 现状 |
|---|---|
| MA / MACD / RSI / BOLL | 纯 Python 实现已存在(`services/ai/indicators.py`),但只在 AI 决策卡里按需算、**未存**。扫描 worker 拉 kline 调这些函数即可,无需新数据源。 |
| 缠论买卖点 | `services/analysis/chan.py` 已能算(`/analysis/chan` 实时),**未存** · 每标的每次全量分析**较重** → 建议低频 / 缓存,或仅对自选小集合开放。 |

### ❌ 本期做不了(数据撑不住 · 不进清单)

| 指标 | 原因 |
|---|---|
| **换手率 / 量比** | Sina 无该字段、东财(EM)通道不可达(`schemas/cn_market.py` 已注;backlog #196)· 需新/恢复数据源。 |
| **清算量 / 爆仓(清算)** | **完全没采**(已确认:无 CH 表、`binance_futures_source.py` 无 forceOrder/liquidation 拉取方法;现有 `perp_liquidation.py` 只扫**用户自己的虚拟持仓**强平,与市场清算数据无关)· 需新建 Binance WebSocket `@forceOrder` 订阅 + 新表 + 新 worker,**是一次真集成,不是廉价补丁**。 |

> 给产品方:①✅档 11 项可直接进 M1 规则清单;②⚠️档(MA/MACD/RSI/BOLL/缠论)是否本期纳入由你定(实现成本低但扫描有 CPU 开销);③❌档(换手率/量比、清算量)本期不进清单 —— 清算量若要做需单独立项(决策点 DP3/DP4)。

---

## 4. G1 代码复用评估(item 3)

G1(分支 `feat/m1g-g1-telegram-unified-bot`:统一 bot + `/start` 绑定 + `/telegram/webhook`(secret 校验)+ Redis 一次性 token + 启动自动 setWebhook)在新架构下的定位:

- **本质 = Telegram 适配层的「入站骨架 + 用户绑定」** —— webhook 形态、secret_token 头、`/start` deep link、`sendMessage`、绑定 token 全是 Telegram 特定的,正好属于适配层。
- **接缝正确**:`tg_chat_id ↔ user_id` 绑定(写 `notification_config.tg_chat_id`)恰是 core 与 adapter 的唯一耦合点 —— core 只认 `user_id`,adapter 负责把 `chat_id` 翻成 `user_id`。
- **结论:直接复用,不返工**,作为本方案**第一期基础**。后续仅**扩展**(非推翻):
  - webhook 现在只处理 `/start` → 后续在同一入口**新增分支**处理命令(`/price`、`/menu` 等)+ inline 按钮回调(`callback_query`)。
  - `handle_start` / bind-token / 启动注册逻辑**不变**。
  - 现有「回执后台异步发」机制(BackgroundTask)正好用于按钮/查询响应。
- 小重构(G2 做):把 G1 里「发消息」与「拼文案」初步拆开,为 core/adapter 边界铺路(改动小,不影响 G1 行为)。

---

## 5. 五大能力设计

### 5.1 /start 绑定 —— ✅ G1 已完成(复用)

### 5.2 定时扫描预警(由 §5.6 规则引擎驱动)
- 复用 `price_alerts.py` 扫描模式:beat → 遍历「用户 × 启用的告警规则」→ 查对应 CH 表 → 命中判定 → Redis 去重(key 含 rule_id)→ Celery → core.outbound → Telegram 渲染推送。
- 频率分层:价格/快照类高频(1–3min);funding/OI/多空比中频(5–15min,对齐采集);缠论类低频(如 30min)+ 缓存。
- 成本护栏:每用户规则数上限(DP6)、扫描批量化、复用已存 CH 数据(不每扫一次打上游)。

### 5.3 交互式行情查询
- bot 命令 `/price <symbol>` 或点交易对按钮 → core.query(symbol) → 核心信息卡(现价/涨跌/成交量;加密additionally funding/OI/多空比/基差/恐贪)。
- 数据复用 CH 读 + 现有 crypto futures 指标 service。

### 5.4 inline keyboard 按钮界面
- 主菜单(/menu):`📊 行情` `⭐ 自选` `💼 持仓` `🛒 下单` `🔔 告警规则` `📈 K线`。
- `callback_query` 在 G1 webhook 入口新增分支处理;多步交互的会话态存 Redis(DP7)。
- K线:Telegram 不便渲染交互图 → 返回 web 深链(`/crypto-preview?symbol=` 等)或服务端渲染静态图(后置,DP 可选)。

### 5.5 bot 内虚拟下单(红线:仅虚拟 · DP5 已定)
- **现货**:选标的 → 选方向/数量 → **确认按钮(必经 · 对齐 web confirm 模态)** → core.order 复用 `place_market_order` → 回执。
- **合约(永续)· 复用已上线 M2-C 虚拟永续引擎,不另写合约逻辑**:
  - **参数全走后台预设**:用户在网页设置页按习惯设定「杠杆倍数 / 每次下单名义金额 / 逐仓全仓模式」,bot 下单时直接套用 —— **bot 界面极简:只有「开多 / 开空」按钮,不在 bot 里调参数**。
  - 下单时**后台校验保证金**:够才下,不足则拒绝并提示(走引擎现有原子保证金校验)。
  - **强平照常由 M2-C 强平 worker 自动运转**(底层必须正常工作,否则合约仓位不自洽)· 用户在 bot 端无需关心。
  - **本期 bot 合约仅支持逐仓**(M2-C 现成);全仓 M2-C 引擎暂无、本期不做 —— 但后台预设的「模式」字段**预留位置**,将来 M2-C 补全仓后 bot 加选项即可、不改 bot 结构。
- 授权模型见 §7。账户未激活 / 未设永续预设 → 引导去 web `/settings/wallet` 设置(bot 不碰资金/参数设置)。
- 回执必带 `VIRTUAL·模拟` 字样 + 「仅供参考,不构成投资建议」。

### 5.6 可配置告警规则引擎(核心 · 新建)
- 规则模型(PG 新表 `alert_rule`):`user_id, market, symbol`(null = 适用其全部自选)`, indicator, operator(>/</>=/<=/穿越), threshold, timeframe, enabled, cooldown_sec, created/updated`。
- 指标取值仅限 §3 ✅(+ 经产品方确认的 ⚠️)档。
- 配置入口(DP9):bot 内 inline keyboard 勾选 + web 设置页表单,二选一或 both。

---

## 6. 数据模型 / PG 迁移

### 新增(PG)
- **`alert_rule` 表**(§5.6)· 配套 alembic 迁移(纯加表,低风险)。
- 多步会话态(下单/配规则的对话上下文)→ **存 Redis**(`tg_session:{chat_id}`,短 TTL),**不建 PG 表**(零迁移)。

### 沿用 0024 的迁移(并入本方案 G2 · 不可逆 · 严格审)
- drop `notification_config.feishu_webhook_url` + `tg_bot_token`(token 转全局 env)。
- `tg_chat_id` 加唯一索引(一 chat 一账号)。
- 清空存量 `tg_chat_id`(旧 per-user bot 的 chat_id 对统一 bot 失效)→ 全员重绑 + 显眼重绑提示。

### 复用(不改 schema)
- `notification_config.tg_chat_id`(绑定)· `virtual_account/order/perp`(下单)· `watchlist`(扫描范围)· 全部 CH 行情表(查询/扫描)。

---

## 7. 安全 / 红线 / 授权

- **仅虚拟,绝不真实交易**(产品 DNA)· bot 下单文案带 `VIRTUAL·模拟` + 免责。
- **下单授权模型**(已核实风险):现有 service 函数**不做鉴权**,只信入参 `user_id`;web 的鉴权在 REST 层(session)。bot 内下单时 bot 成为唯一鉴权边界 → **`user_id` 只能从「已通过 secret_token 校验的 webhook update 的 `chat.id`」解析,绝不从用户文本取**;destructive 操作(下单/平仓)**必经 inline 确认按钮**。
- webhook secret_token 校验(G1 已有 · HMAC 派生)。
- 一 chat 一账号(G2 唯一索引兜底)。
- 限流(DP11):bot 命令 / 下单频率限制,防滥用 + 防 Telegram 限流。

---

## 8. 零回归

- 核心层 = 复用现有 service,**不改 web REST、不改引擎逻辑**(只加 facade 调用)。
- 适配层 = 纯新增,不碰 web 前端。
- 飞书移除(G2)按 0024 计划,dispatcher 改动只在异步/worker 侧。
- 下单 emit / 价格异动 worker 链路不变(新告警引擎是**并行新增**的扫描任务,不动旧 ±5% 任务,或择机统一 —— DP)。

---

## 9. 分期建议(每期高风险档 · feature 分支 · 单独审 · G2 含不可逆迁移须严格审)

| 期 | 范围 | 备注 |
|---|---|---|
| **G1** | 统一 bot + `/start` 绑定 + webhook 骨架 | ✅ **已写**(待并)· 复用 |
| **G2** | 核心层抽象 + 告警规则引擎(`alert_rule` 模型 + 规则 CRUD + 扫描 worker)+ 0024 飞书移除/迁移 | 含不可逆 PG 迁移 · 严格审 |
| **G3** | 交互式查询 + inline keyboard 按钮界面(行情/自选/持仓查询) | webhook 扩展 callback_query |
| **G4** | bot 内虚拟下单(确认流程 · 现货[+永续按 DP5]) | 红线最敏感期 |
| **G5** | 前端:设置页绑定 UX(deep link + 二维码)+ 规则配置 UI + 重绑提示 + bot 品牌(D9) | |
| **G6** | 真机走查(绑定→查询→预警→虚拟下单)+ 0025 收尾 | |

---

## 10. 风险点

- **R1 下单授权**:bot 是唯一鉴权边界 → 严格只从 validated webhook chat.id 取 user_id + 确认按钮。
- **R2 红线**:bot 下单绝不能误接真实通道 —— 全程走虚拟引擎,代码评审重点核查。
- **R3 不可逆迁移**(G2):清空旧 chat_id + drop 飞书列 · 须重绑提示到位。
- **R4 扫描成本**:多用户 × 多规则 × 多频率 → 规则数上限 + 批量查 + 复用已存 CH(勿每扫打上游,重蹈 akshare 卡死)。
- **R5 缠论扫描重**:全量分析 CPU 开销 → 低频 + 缓存。
- **R6 Telegram 限流**:统一 bot 给所有用户发 → ~30 msg/s 上限 · 批量推送要排队/限速。
- **R7 会话态**:多步交互存 Redis,注意 TTL + 并发。

---

## 11. 决策点(最终结论 · 产品方已拍板 2026-05-27)

| # | 决策 | 最终结论 |
|---|---|---|
| **DP1** | 分期/优先级 | 按 §9:G2 预警引擎 → G3 查询/按钮 → G4 下单 → G5 前端 → G6 验收。 |
| **DP2** | 技术指标 | **全纳入**告警规则清单:MA / MACD / RSI / 布林带 **+ 缠论买卖点** 都做(缠论低频 + 缓存)。 |
| **DP3** | 清算量/爆仓 | **本期不立项**(不为此新建 Binance 实时订阅)· 登记为**远期可选**(backlog)。 |
| **DP4** | 换手率/量比 | **不做**(数据源不支持 · 等 #196)。 |
| **DP5** | bot 合约下单 | **现货 + 永续都做**;永续复用 M2-C 引擎。杠杆/名义金额/逐仓全仓**全走后台预设**(网页设),bot 只「开多/开空」按钮、不调参;下单后台校验保证金不足则拒;强平照常由 M2-C worker 自动运转(底层必须正常);**本期仅逐仓**,模式字段预留位将来加全仓。详见 §5.5。 |
| **DP6** | 扫描规模 | 采纳推荐:每用户告警规则 **≤ 20 条**;频率分层(价格/快照 1–3min · futures 指标 5–15min 对齐采集 · 缠论 30min)· 批量查 CH 不打上游。 |
| **DP7** | 会话态 | 采纳推荐:多步下单/配规则对话上下文存 **Redis**(`tg_session:{chat_id}` 短 TTL · 零迁移)。 |
| **DP8** | 下单确认 | 采纳推荐:destructive 操作(下单/平仓)**必经 inline 确认按钮**(对齐 web)。 |
| **DP9** | 规则配置入口 | **both** —— 网页设置页 + bot 内 都能配(按 §5.6)。 |
| **DP10** | 飞书扩展位 | 采纳推荐:本期**只留适配层接口、不实现**飞书。 |
| **DP11** | 限流 | 采纳推荐:每用户每分钟 bot 命令 ≤ 20 / 下单 ≤ 10;全局发送排队限速 ≤ 25 msg/s。 |
| **DP12** | G1 复用 | **确认**:G1(已写 · `feat/m1g-g1-telegram-unified-bot`)直接作为第一期基础,不返工。 |
| **DP13** | 旧 ±5% 任务 | 采纳推荐:新引擎上线后**保留旧 `price_alerts` ±5% 并行**(过渡 · 零回归优先),后续阶段末迁入规则引擎收口。 |
| **DP14** | K线呈现 | 采纳推荐:bot 里 K 线用 **web 深链**(本期不做服务端渲染静态图)。 |

> 红线复述:只虚拟、永不真实下单;bot 下单只走虚拟引擎;下单授权 user_id 只从已验证 Telegram 绑定取、绝不从文本猜;危险操作必经确认按钮;一切 bot 输出带「仅供参考,不构成投资建议」。

---

## 12. 备注

- 本文只是方案,不含实现代码、不改运行代码 / 界面。产品方就 §11 决策点拍板后,按 §9 分期落地。
- G1 代码分支 `feat/m1g-g1-telegram-unified-bot` **暂不挑 main**,等本方案定稿 + 确认 G1 符合本架构(§4 建议:符合)后再决定合入。
- 微信明确不做(平台不开放);飞书本期不做,靠 §2 适配层架构留位。
