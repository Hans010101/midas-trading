# 0028 · 告警通知频次 / 降噪 · 设计方案

## 状态

**Closed**(2026-05-28)· N1 + N2 + N3 + N4 全期完成并上线 main · DP9 网页 + bot 双通道闭环 ·
产品方真机走查(N4)通过 · 降噪 ADR 收口。10 个决策点(DP1–DP10)见 §6。

> **实施进度**(收口):
> - **N1 后端**(commit `7b40173`)· 边沿触发状态机 + dispatcher quiet 拦截 + price_alerts 改造 + 阈值轻调 + 紧急豁免 ClassVar · pytest 26 项
> - **N2 网页**(commit `e946876`)· `/settings → 告警安静时段` section · GET/PUT `/notifications/config` 暴露 quiet_hours 4 字段 + zoneinfo 校验 · pytest 16 项(含 6 越界 parametrize)
> - **N3 bot**(commit `cc52cff`)· 主菜单 [🌙 安静时段] + render_quiet_hours 6 按钮 + 起止小时 mod 24 步进 · 时区切换留网页 · pytest 21 项(★ 含 2 个跨用户隔离 + 10 个边界 parametrize)
> - **N4 走查**(2026-05-28)· bot 6 按钮 / 网页 section / quiet 时区 / 边沿触发(`alert_rule:state:*` 不卡死)/ 推送通路(下午 16:53 实证)· **全部通过**
>
> ★ 关键观察:N4 走查期间产品方"数小时无告警"现象,经 worker 日志查实 `scan_alert_rules` /
> `scan_price_anomalies` 每分钟健康跑、`triggered=0`、无 `dropped_quiet`、`alert_rule:state:*` 为空 ——
> **N1 边沿触发降噪生效的正常表现**(不再刷屏)· 不是故障。
>
> 后续 backlog(不在本 ADR 内):
> - N5(D 聚合 digest)· 看 N1-N3 长期效果再评估
> - render_main_menu 文字部分老旧(G3 时代只列 4 功能)· 并入下次碰 bot 时一起修
> - 强平 / 成交 TG 通知接入(`TradeFilledEvent` 豁免机制就绪但 emit 入口未接)· 降噪收口后评估

承接:M1-G G6 真机走查反馈("9 条推荐规则跑起来后 TG 信息密度偏高、有刷屏感")。
触发:ADR-0025(M1-G G2b 告警引擎)+ ADR-0026(M1-G G5 9 条推荐规则)上线后的体验缺陷。

> 🔴 红线(贯穿):全程虚拟资金、虚拟教学;告警只是策略提示,绝不构成投资建议、绝不
> 自动下单。本期改的是用户体验层(噪音控制),引擎核心(求值 / 推送链路)不动。

---

## 1. 现状摸查(精确到字段 + 任务)

### 1.1 数据模型

`apps/api/app/models/alert_rule.py`(0025 G2b):
- `cooldown_sec`:`Integer, server_default 300`(5 分钟)· 用户可配范围 60–86400s(schema 限)
- 其余:`user_id / market / symbol / indicator / operator / threshold / timeframe / enabled / created_at / updated_at`
- **无字段**:无"上次触发状态"、无"上次触发时间"、无"最近触发值"

`apps/api/app/models/notification.py`:
- `NotificationConfig`:`tg_chat_id / trade_alert_enabled / price_alert_enabled`
- **无字段**:无安静时段、无全局降噪开关、无聚合偏好

### 1.2 扫描机制(`apps/worker/tasks/alert_scan.py` · 0025 DP6)

- Celery beat 每 **1 分钟**触发 `tasks.alerts.scan_alert_rules`
- 按指标 `category` 频率分层(`_CATEGORY_INTERVAL_MIN`):
  - `price` / `volume` / `technical`:**1 分钟**
  - `market_structure`:3 分钟
  - `crypto_deriv` / `crypto_global`:5 分钟
  - `chan`:30 分钟
- 单次扫描遍历所有 `enabled=True` 规则 · `evaluate_rule(ctx, rule)` 求值 · 命中即推
- **去重(关键)**:Redis key `alert_rule:{rule_id}` TTL = `rule.cooldown_sec` · **只有 dispatch.any_sent 后才写 key**(失败重试友好,副作用:dispatch 抖动期间可能重推)

### 1.3 去重机制的本质(刷屏根因)

**当前是 time-based dedup(时间窗口去重),不是 edge-triggered(状态过渡触发)**:
```
现状:每 cooldown_sec 推一次(只要值持续在阈值内)
应有:值"未触发→触发"状态切换时推一次,持续触发期间不重推,
      值离开区间(回到未触发)后再次进入才再推
```

### 1.4 老 ±5% 任务(`apps/worker/tasks/price_alerts.py` · 0009 §4)

- Celery beat 每 **1 分钟**触发 `tasks.price_alerts.scan_price_anomalies`
- 扫所有 `WatchlistItem` · `|change_pct| ≥ 5%`(基于昨日 close)即推
- Redis key `price_alert:{user_id}:{market}:{symbol}` TTL **300s 硬编码**
- 走独立 task `tasks.notifications.send_price_anomaly_notification`(不走新引擎)
- DP13(0025)决定:与新引擎**并存,不替代**

### 1.5 推荐规则刷屏诊断(9 条 · 0026 §4.2)

| # | 规则 | category | 扫描间隔 | 刷屏风险(★ 越多越严重)|
|---|---|---|---|---|
| 1 | `crypto/fear_greed lt 20`(极度恐慌)| `crypto_global` | 5 min | ★★★ 指数日变化小,一旦进入极端区间会持续几天 → 每 5min 推 = **~288 次/日** |
| 2 | `crypto/fear_greed gt 80`(极度贪婪)| `crypto_global` | 5 min | ★★★ 同上,对称 |
| 3 | `cn/cn_breadth_up_ratio lt 30`(A股普跌)| `market_structure` | 3 min | ★★★ 普跌日内可能稳定 → 每 3min 推 = **~480 次/日** |
| 4 | `us/NVDA rsi_14 gt 70`(超买 · 1d)| `technical` | 1 min | ★★★★ 日 K RSI 进区间后稳定,**每 cooldown(默认 5min)推一次 = ~288 次/日**;1min 扫描频率本身不致命,因 cooldown 兜底,但 cooldown 太短 |
| 5 | `us/NVDA rsi_14 lt 30` | 同上 | 1 min | ★★★★ |
| 6 | `cn/600519 rsi_14 gt 70` | 同上 | 1 min | ★★★★ |
| 7 | `cn/600519 rsi_14 lt 30` | 同上 | 1 min | ★★★★ |
| 8 | `crypto/BTC rsi_14 gt 75` | 同上 | 1 min | ★★★★ |
| 9 | `crypto/BTC rsi_14 lt 25` | 同上 | 1 min | ★★★★ |

**结论**:6 条 RSI 规则刷屏最严重(每个超买/超卖区间持续期 = 数百条推送);3 条全局/市场结构次之但持续期可能更长。

---

## 2. 降噪策略选项(逐条列 · 取舍 · 复杂度)

### A · Edge-triggered(状态过渡触发)· 🌟 **根治方案**

**做法**:为每条规则记录"上次状态"(triggered / not_triggered),只在状态从 `not_triggered → triggered` 时推一条;状态变成 `triggered` 后,即使值持续在阈值内、即使 cooldown 已过,也**不再推**;直到值离开阈值区间(回到 `not_triggered`),下次再进入区间才再推。

**实现**:
- 新增表 `alert_rule_state(rule_id PK, last_triggered_at, last_value, last_state)`(或 Redis 持久化);
- `evaluate_rule` 返回 `(triggered, value)`;worker 对比 `last_state`,只在 `not_triggered → triggered` 边沿派发;同时更新 `last_state`。
- Cooldown 退化为"最小重复间隔"护栏:即使边沿触发,也保证两次推送间隔 ≥ cooldown_sec(防 mark 抖动跨阈值反复跳)。

**取舍**:
- ✅ 根治"指标卡阈值内反复推"问题 · 一次进入 = 一条推送
- ✅ 与逐规则冷却 / 安静时段 / 聚合**兼容**,是基础设施
- ⚠️ 改了告警语义 · 用户认知需更新(从"提醒还在条件内"到"提醒进入条件")
- ⚠️ 需要小表 / Redis 持久化"上次状态" · DB 迁移(新表 1 张)or Redis 持久化(不需迁移)
- ⚠️ Worker 失败 / 重启后需保证状态正确 · 用 Redis `SET NX` 等机制

**复杂度**:**中** · 改动集中在 worker(`alert_scan.py`),引擎求值逻辑不动

### B · 逐规则冷却(已有 · 默认值收紧)

**做法**:`cooldown_sec` 字段已有,只是默认 300s 太短。改为:
- 默认 `cooldown_sec = 86400`(24 小时)·  让"超买超卖卡日内"自然每日最多 1 条
- 用户仍可配(60–86400s 上限不变)

**取舍**:
- ✅ 零代码改动(仅改 `server_default` + 一个迁移 · 已有用户保留个性化值)
- ✅ 立竿见影:即使不做 A,刷屏量从"每日 ~288 次"降到"每日 ≤1 次"
- ⚠️ 用户**会错过"指标二次离开后重新进入"的合法重复触发**(因为 cooldown 内还没清,即便离开再进入也压住了)· 这是 time-based 的死结
- ⚠️ 不解决根因(只是把窗口拉大);若产品方想要"再次进入再推"语义,必须做 A

**复杂度**:**极低** · 改 `server_default` + 数据迁移(可选回填)

### C · 全局安静时段

**做法**:`NotificationConfig` 加 `quiet_hours_start / quiet_hours_end`(每日,用户本地时区或 UTC)· dispatcher 在 quiet 窗口内**直接吞掉推送**(不重试不缓存,符合 time-based 语义)。

**取舍**:
- ✅ 用户体感最直观的开关("我晚上不想被打扰")
- ✅ 实现简单 · 改 `dispatcher.py` 加一个时间窗口判断
- ⚠️ 时区:存 UTC HH:MM 还是用户本地时区 · 后者需要前端拿 `Intl.DateTimeFormat().resolvedOptions().timeZone` 存到用户档(待 DP3 拍板)
- ⚠️ 紧急告警(例如缠论买点)是否豁免 quiet · 本期不分级(可后续)

**复杂度**:**低** · `NotificationConfig` 加 2 字段 + dispatcher 加 if + 前端配置 UI

### D · 同类聚合 / Digest 推送

**做法**(参考 CryptoSharp"告警聚合 Top X"):在 N 分钟窗口内,把同用户多条告警**缓存到 Redis**,窗口结束(或攒够 K 条)统一推一条 digest("过去 5 分钟内你有 3 条告警:① NVDA RSI 超买 ② 600519 RSI 超买 ③ A股普跌")。

**取舍**:
- ✅ 体验最好(用户读一条 digest 即可了解全局)
- ✅ 跟 A 正交(A 解决重复,D 解决多规则同时触发)
- ⚠️ 实现复杂:需要 Redis ZSET buffer + 独立 flush worker(beat 任务 / Celery countdown)+ 模板渲染聚合消息
- ⚠️ 用户期望"实时性"的告警(比如缠论买点)做了聚合后会延迟 N 分钟,需分级豁免
- ⚠️ 失败重试 / 落库流水更复杂(目前 dispatch 是"派完即忘")

**复杂度**:**中–高** · 本期建议先不做,作为 P2 跟进项

### E · 调整推荐规则默认阈值

**做法**:在 `RECOMMENDED_ALERT_RULES`(0026 §4.2)里把阈值收紧:
- `fear_greed lt 20 → lt 15`(只在更极端时报)· `gt 80 → gt 85`
- `RSI gt 70/lt 30 → gt 75/lt 25`(US/CN);`crypto BTC RSI gt 75/lt 25 → gt 80/lt 20`
- `cn_breadth_up_ratio lt 30 → lt 25`

**取舍**:
- ✅ 让"一键应用"出来的默认就不那么吵 · 用户不需要立刻动配置
- ✅ 零运行代码改 · 改常量 + 现有用户可选择"重新应用"(覆盖式 apply 可在 G5 升级)
- ⚠️ 阈值是 ADR-0026 拍过板的 · 调整需产品方再次拍板
- ⚠️ 不解决"卡在新阈值内还是会刷屏"的根问题(治标不治本)

**复杂度**:**极低** · 只改 `recommended.py` 常量

### F · 按 `category` 的分层默认冷却

**做法**:`cooldown_sec` 默认值改成"按指标 category 分层":
- `crypto_global` / `market_structure`(慢变指标):默认 21600s(6h)
- `technical`(日 K RSI 类):默认 86400s(24h)
- `price` / `volume`(快变):默认 1800s(30 min)
- `chan` / `crypto_deriv`:默认 3600s(1h)

**取舍**:
- ✅ 比"全规则统一默认"更合理(快变 vs 慢变区别对待)
- ✅ 用户仍可覆盖
- ⚠️ 在 schema / route / 前端"创建规则"流程需查 registry 取 category 来填默认 · 略增加耦合
- ⚠️ 若做了 A(edge-triggered),F 的价值降低(因为已经不会刷屏)

**复杂度**:**低** · 改"新建规则时填默认 cooldown"的逻辑

---

## 3. 推荐组合 + 理由

**P0(本期必做)= A + C + E** · "edge 根治 + 安静时段 + 阈值轻收紧":
- **A**:从语义上根治"卡阈值内反复推",一次进入 = 一条推送 · 与 0025 现有冷却机制兼容
- **C**:加全局安静时段,用户对降噪最直观的开关(夜间静音)
- **E**:把推荐默认阈值轻微收紧,减少"刚进阈值就触发"的边缘场景

**P1(可选纳入)= B 或 F** · "再加冷却兜底":
- 即使做了 A,仍保留 cooldown_sec 作为护栏(防 mark 抖动跨阈值反复)
- 默认值用 F 的分层(比 B 全规则统一更精准)

**P2(后续)= D** · "聚合 digest"
- 体验最好但成本最高 · 等 A + C 上线观察用户反馈再决定是否做
- 做之前要拍板紧急豁免分级

**老 ±5%(price_alerts)的处理**:
- 该任务自带 5min 硬编码 dedup · 跟新引擎是独立链路 · 建议:
  - C(安静时段)也覆盖它(dispatcher 层统一拦截)
  - 暂不做 edge-triggered(代价大、收益小、是基础 demo 体验)
  - 长远迁移到新引擎(把"涨跌幅 ±5%"做成 `price_change_pct ≥ 5` 的内置规则)· **不在本期**

---

## 4. 数据模型变动 / PG 迁移 / 零回归

### 4.1 新增

**A · 状态表**(若选 DB 而非 Redis):
```
alert_rule_state (
  rule_id BIGINT PRIMARY KEY REFERENCES alert_rule(id) ON DELETE CASCADE,
  last_state VARCHAR(16) NOT NULL DEFAULT 'unknown',   -- triggered / not_triggered / unknown
  last_triggered_at TIMESTAMPTZ,
  last_evaluated_at TIMESTAMPTZ,
  last_value NUMERIC(20,8)
)
```
迁移:`create_table` 纯新增、可逆 drop。

**或 Redis 持久化**(更轻):
- `alert_rule_state:{rule_id}` = JSON `{"state":"triggered","at":...,"value":...}`(无 TTL · 持久态)
- 不需迁移
- 缺点:Redis 重启 / 故障会丢状态 → 首次扫描会再次推送(可接受)

→ 选 Redis 持久化更轻、零迁移、零回归;DB 表更可靠但需要迁移。**待 DP1.x 拍板**(产品方选 robust 还是 lean)

### 4.2 修改

**C · NotificationConfig 加字段**:
```sql
ALTER TABLE notification_config 
  ADD COLUMN quiet_hours_start SMALLINT,   -- 0-23 (NULL=禁用)
  ADD COLUMN quiet_hours_end   SMALLINT,   -- 0-23
  ADD COLUMN quiet_hours_tz    VARCHAR(64) DEFAULT 'Asia/Shanghai';
```
全可空 + 默认值;现有用户保持原行为(quiet_hours 全 NULL = 禁用,跟当前一致 = 零回归)。
迁移可逆。

**B/F · alert_rule.cooldown_sec 默认值**:
- 现有用户已显式设值,保留;
- `server_default` 改值 / 改"创建时按 category 填默认"
- 现有规则不动 = 零回归

**E · recommended.py 常量调整**:
- 不改库 · 不影响现有规则;
- 用户重新"一键应用"才会建新阈值规则(且去重逻辑会跳过已存在 key)
- 老用户不动 = 零回归

### 4.3 零回归考量

| 场景 | 现状 | 加 A 后 | 加 C 后 |
|---|---|---|---|
| 老用户既有规则(无 quiet)| 每 cooldown 推一次 | edge 触发后不重推,直到值离开 | 不在 quiet 窗口的部分行为同 A;quiet 窗口内被吞 |
| 老用户既有规则(用户自配 cooldown=3600)| 每 1h 推一次 | edge 触发后不重推;再次进入 + cooldown 过期才推 | 同 A + quiet 覆盖 |
| 价格 ±5% 任务 | 5min dedup 不变 | 不影响(A 只改新引擎)| 走 dispatcher → 受 quiet 拦截 |

---

## 5. 配置入口

**对齐 0025 DP9("both")精神** · 网页 + bot 都能配:

### 5.1 网页(`/settings`)

- 已有"消息推送配置"section:
  - 加 **安静时段**:开关 + 时段 picker(本地 24h)+ 时区(默认 `Asia/Shanghai`)
- 已有"告警规则配置"section:
  - 在每条规则行加"冷却"显示(已有 cooldown_sec 字段)· 让用户能看到 / 编辑

### 5.2 Bot

- 已有 `/rules` 命令(0025 G5):新增子命令 / 按钮
  - 🆕 `quiet:set` / `quiet:off`:切换安静时段(交互式或固定 22:00–08:00 + 时区跟绑定时取)
  - 已有 `rules:toggle:{id}`:仍可启停单规则
- 推荐保持简单 · 网页是主配置面,bot 是快速开关

### 5.3 配置渠道一致性

- 所有配置走 PG(单一事实源)· 网页 PUT / bot POST 都改 DB
- 引擎只读 DB · 立即生效(下次 beat tick 时拉到)
- 与 0009/0024 的现有 NotificationConfig 模型完全兼容(只是加字段)

---

## 6. 决策点 · 最终结论(产品方拍板 · 2026-05-28)

> 10 个决策点全部拍板,结论如下。本表是 N1 实现的契约。

| # | 决策 | **最终结论** | N1 落地 |
|---|---|---|---|
| **DP1** | 核心策略组合 | **P0 = A 边沿触发 + C 安静时段 + E 阈值轻调**;P1(分层默认 F)/ P2(聚合 D)本期不做,看 P0 效果再说 | 本期 |
| **DP2** | edge-triggered 状态存储 | **Redis 持久化**(零迁移)· 重启丢状态时首次扫再推一次(可接受) | 本期 |
| **DP3** | 默认冷却 | **沿用合理默认**(`cooldown_sec` 不改 server_default · 边沿触发已根治"卡阈值反复推",冷却只作护栏防 mark 抖动) | 不动 |
| **DP4** | 安静时段默认 | **默认开启 · 23:00–07:00**(用户可调时段、可关) | 本期 |
| **DP5** | 安静时段时区 | **用户所在时区**(主力东八区 · 默认 `Asia/Shanghai`)· 后续 N2 前端注册流程可改写真实时区 | 本期默认 Asia/Shanghai |
| **DP6** | 推荐规则阈值(E) | **轻调**:fear_greed 20/80→**15/85**;A股 breadth 30→**25**;US/CN RSI 70/30→**75/25**;crypto BTC RSI 75/25→**80/20**(保持规则意义,不动太狠) | 本期 |
| **DP7** | 现有用户 `cooldown_sec` 是否回填 | **不回填 · 边沿触发对所有现存规则生效**(含老用户旧规则 · 不强改用户已配的阈值/冷却) | 本期(语义自动覆盖) |
| **DP8** | 聚合 digest(D) | **本期不做** · P0 效果观察后再决定 | 不做 |
| **DP9** | 老 ±5%(price_alerts)| **也改成边沿触发**(同 A 机制 · 它也是 time-based 重复推的)+ 受 quiet 拦截 | 本期 |
| **DP10** | 紧急豁免 | **强平等关键事件不受安静时段限制**("钱相关的通知不能因夜间静默而漏")· 本期建立 quiet_exempt 机制 + 标记 `TradeFilledEvent`(钱相关);`PriceAnomalyEvent` / `AlertTriggeredEvent` 不豁免 | 本期 |

**结论提炼(给 N1 实现期当宪法用)**:
- 边沿触发:Redis state key 无 TTL · 持久态 · 状态机 4 种过渡(详 §2.A) · cooldown 退化为护栏 · 涵盖新告警引擎和老 price_alerts
- 安静时段:默认 23:00–07:00 / Asia/Shanghai / 开启 · 用户可调可关 · dispatcher 一处拦截 · `TradeFilledEvent` 豁免
- 阈值轻调:仅改 `RECOMMENDED_ALERT_RULES` 常量,已有用户已建规则不动

---

## 7. 实施分期建议(产品方拍板后)

按 DP1 选 ① 推荐:

**N1 · 后端 edge + quiet + 默认调整**(后端为主)
- A:Redis 持久化"上次状态"(DP2 ①)或新 `alert_rule_state` 表(DP2 ②)
- 改 `alert_scan.py`:增加状态对比 + 边沿触发 + cooldown 退化为最小间隔护栏
- C 数据模型:`notification_config` 加 `quiet_hours_start/end/tz`(迁移)
- 改 `dispatcher.py`:quiet 窗口内吞掉推送
- E:改 `recommended.py` 阈值常量
- 测试:edge 边沿测试 + 卡阈值不重推 + quiet 拦截 + 现有用户零回归

**N2 · 前端 quiet 配置 + 规则页冷却字段可见**
- `/settings` 推送配置加 quiet picker + 时区显示
- 规则配置 section 显示并可编辑 `cooldown_sec`

**N3 · Bot quiet 快速开关**(可选)
- `/rules` 菜单加 quiet 开关

**N4 · 真机走查 + 24h 观察**
- 让用户在生产环境跑一天 · 验证刷屏量

**N5(后续 · 视效果)· D 聚合**:若 P0 不够,做 digest。

---

## 8. 风险点 + 测试覆盖

### 风险

- **A 状态漂移**:Redis 故障 / worker 重启时丢状态 → 首次扫再推一次(选 DP2 ② DB 表可降低概率)
- **C 时区错位**:用户在不同设备/时区登录,quiet 窗口和预期不符 → 用户档写时区(DP5 ①)
- **E 阈值收紧**:用户配的规则不变,只影响"一键应用"(预期内)
- **零回归红线**:任何选项的"不做"分支都需保证 `cooldown_sec` 仍按现有 300s 工作

### 测试覆盖

- **edge 边沿测试**:同规则连续扫 5 轮值进入区间 → 只触发 1 次;再扫 5 轮值离开 → 0 触发;再 5 轮进入 → 触发 1 次
- **cooldown 护栏**:在 edge 已触发后即使值离开再进入,在 cooldown 内仍被吞
- **quiet 拦截**:在 quiet 窗口内触发 → dispatcher 不发(但 alert_rule_state 仍可更新 · 或不更新 · DP 待定)
- **现有用户回归**:已有规则 + 无 quiet 设置 → 行为同 0025 G2b(无差异)

---

## 9. 一句话总结

**根因是 time-based dedup 不是 edge-triggered;主推 A+C+E(edge 触发 + 安静时段 + 阈值轻收紧),其他选项作为护栏与可选项,P0 之后看效果再决定是否做 D(聚合)。**
