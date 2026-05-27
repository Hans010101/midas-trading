# 0024 · 通知系统 v2:Telegram 统一 bot + /start 绑定 + 移除飞书

## 状态

**Superseded by 0025**(2026-05-27)· M1-G 已从「通知迁移」升级为「Telegram 迷你交易终端」,完整设计见 **0025**。本文保留为 v1 历史 —— 其 §2/§3 的统一 bot + /start 绑定设计被 0025 复用,G1 代码据此实现并作为 0025 第一期基础。

(原:本文是 0009《推送通知设计》的演进,supersedes 0009 的「用户自带 bot / 双通道」模型。0009 保留为更早历史。)

> 红线不变:虚拟资金 · 推送必带「仅供参考,不构成投资建议」· 推送 emit 绝不阻塞下单主链路。

---

## 1. 现状摸查(实读代码 · 非推测)

### 1.1 配置存储 —— 100% per-user,存 PG,**无 env 凭证**

- `apps/api/app/models/notification.py` · 表 `notification_config`,PK=FK `user_id`,lazy create(跟 `VirtualAccount` 同模式)。字段:
  - `feishu_webhook_url` `String(512) | None`
  - `tg_bot_token` `String(128) | None`
  - `tg_chat_id` `String(64) | None`
  - `trade_alert_enabled` / `price_alert_enabled` `Bool`(server_default true)
  - `created_at` / `updated_at`
- 迁移:`apps/api/alembic/versions/5a98653dd149_notification_config.py`(链中段)。当前 alembic head = `d8e2f4a5c7b9_user_google_oauth.py`。
- `apps/api/app/core/config.py` 的 `Settings` **没有任何通知相关字段** —— 经核实,`FEISHU_WEBHOOK_URL` / `TG_BOT_TOKEN` / `TG_CHAT_ID` 这些**在代码 / .env.example / docker compose 里都不存在**(CLAUDE.md 的「待用环境变量」表是规划,从未落地)。**当前每个用户在设置页手动粘贴自己的 bot token + chat_id**(BYO-bot 模型)。

### 1.2 通道客户端 —— `apps/api/app/services/notifications/`

- **飞书** `feishu.py:23-63` · `async send(webhook_url, payload, ...)` → httpx POST 用户填的 webhook,interactive card。成功 = HTTP 200 且 body `StatusCode==0`。安全模式 = 自定义关键词「点金」(模板里自带)。
- **Telegram** `telegram.py:23-63` · `async send(bot_token, chat_id, text, parse_mode="Markdown", ...)` → POST `https://api.telegram.org/bot{token}/sendMessage`。成功 = HTTP 200 且 body `ok==true`。**纯出站(sendMessage)· 没有任何入站 webhook / getUpdates / /start / chat_id 自动绑定逻辑**(全仓 grep 确认)。token+chat_id 用户手填。
- **邮件** `services/email.py`(Resend)**不是**通知通道(0009 §备注:邮件只管注册/事务,dispatcher 不 import 它)。
- **模板** `templates.py` · `render_feishu` / `render_feishu_test` / `render_telegram` / `render_telegram_test`。每条都嵌「点金 Midas」+「本次为模拟交易,不构成投资建议」。

### 1.3 派发器 —— `dispatcher.py`

- `dispatch(db, user_id, event, *, client=None)`:读该用户 `NotificationConfig`(无行 → 空结果);按 `event.kind` 过滤总开关;然后**逐通道独立**发(一边失败不影响另一边):`feishu_webhook_url` truthy → 发飞书;`tg_bot_token AND tg_chat_id` → 发 TG。返回 `DispatchResult(list[ChannelResult])`。
- `send_test(config, channel, ...)` = 设置页「发送测试消息」按钮后端,单通道。
- **通道是否启用 = 纯 per-user(DB 行存在 + 字段非空)· 无全局配置。**

### 1.4 事件 emit 链路

- **成交(成交通知)**:`services/virtual_trading/engine.py:479` 在 `_record_filled` 末尾(`db.flush()` 后)调 `emit_trade_filled(order.id)`(`services/notifications/emit.py:35-52`)→ 懒建 Celery client → `send_task("tasks.notifications.send_trade_notification", [order_id])`,broker 挂只 log 不抛(保护下单主链路)。worker 侧 `apps/worker/tasks/notifications.py` 拉 order+account → 建 `TradeFilledEvent` → `dispatch`。(注:**只有现货 `_record_filled` emit,perp 成交不 emit**。)
- **价格异动**:`apps/worker/tasks/price_alerts.py` · beat `crontab(minute="*")`(每分钟)→ 扫**全部** `WatchlistItem`(所有用户,无 user 过滤)→ ClickHouse 取两根日 K close → `|pct| >= 5%`(`PRICE_ALERT_THRESHOLD=5.0`)→ Redis dedup key `price_alert:{user_id}:{market}:{symbol}` TTL 300s → `send_task("tasks.notifications.send_price_anomaly_notification", ...)` → 同 `dispatch`。

### 1.5 REST + 前端

- 路由 `apps/api/app/api/v1/notifications.py`(prefix `/notifications`):`GET /config`、`PUT /config`(部分更新 + lazy create)、`POST /test?channel=feishu|telegram`。token GET 时截断 `prefix10...suffix4`。
- 前端 `apps/web/components/settings/notifications-config-section.tsx`(挂在 `app/settings/page.tsx:28`):飞书 webhook 卡 + Telegram 卡(Bot Token 密码框 + Chat ID 文本框,**手动录入**)+ 事件开关 + `TestButton`。API client `lib/api/notifications.ts`,hooks `hooks/use-notifications.ts`。

### 1.6 ADR 0009 状态

`docs/decisions/0009-notification-design.md` · **Approved(2026-05-20)**。核心:独立 `notification_config` 表;飞书关键词「点金」+ TG sendMessage(手填 token+chat_id);异步 emit;价格异动每分钟 ±5% / Redis 5min 去重;3 条 REST;明文存 token(M1 加密)。**0009 里没有任何 /start / 统一 bot 设计** —— 那正是本文要补的。

---

## 2. 目标态与现状的根本差异

| 维度 | 现状(0009 v1) | 目标(0024 v2) |
|---|---|---|
| TG bot | 每用户自带 bot,手填 token+chat_id | **一个 Midas 官方统一 bot**,token 存服务端 env/secret |
| 绑定方式 | 用户手动复制 chat_id 粘贴 | 点「绑定 Telegram」→ 打开 bot → `/start` 自动捕获 chat_id |
| 飞书 | 支持 | **完全移除** |
| 入站 | 无(纯出站) | 需要入站:接 `/start`(webhook 或 long-polling) |
| chat_id 来源 | 用户自填(对应他自己的 bot) | `/start` 时 bot 捕获(对应统一 bot) |

**关键洞察(零回归生命线)**:chat_id 是 **(bot, chat) 对**绑定的。现存用户填的 `tg_chat_id` 对应的是**他们自己的 bot**,**换成统一 bot 后这些旧 chat_id 全部失效**,必须清空 + 引导重新 `/start` 绑定。飞书用户切换后直接失去飞书。→ 这是面向用户的行为变更(决策点 D3)。

---

## 3. Telegram 统一 bot 设计

### 3.1 建 bot

- 产品方用 BotFather 建一个 bot(如 `@MidasTradeBot`),拿到 **bot token**。
- token 存**服务端 secret**(GitHub Secrets → 部署期注入 env `TG_BOT_TOKEN`),**不进前端、不进 per-user DB、不进 git**。
- 这是产品方动作 + 一个新 secret(决策点 D4 / D9)。

### 3.2 /start 绑定流程(deep-link token 方案 · 推荐)

```
用户在设置页点「绑定 Telegram」
  → 后端生成一次性随机 binding_token(短 TTL,如 10 min),存 pending(token → user_id)
  → 前端给出 deep link: https://t.me/MidasTradeBot?start=<binding_token>  (+ 二维码)
用户点链接 → Telegram 打开 bot → 自动发 "/start <binding_token>"
  → bot 后端收到 update(含 message.chat.id + /start 的 token 参数)
  → 用 token 查 pending → 得 user_id;写绑定:notification_config.tg_chat_id = chat.id;删 pending token
  → bot 回「✅ 绑定成功 · 点金 Midas」;设置页轮询/刷新显示「已绑定」
```

- 一次性 token 防盗绑(别人拿不到你的链接就绑不了你的账号)。

### 3.3 入站机制:webhook vs long-polling(决策点 D1)

| | webhook(推荐) | long-polling |
|---|---|---|
| 机制 | Telegram POST update 到 `https://api.midastrade.asia/api/v1/telegram/webhook` | 一个常驻进程循环 `getUpdates` |
| 适配现状 | Caddy 已终结 TLS · 加一条公开路由即可 · 无常驻进程 | 需要新常驻 worker / 进程(Celery 不适合长轮询) |
| 安全 | 设 Telegram `secret_token`(校验请求头)+ 只收已知 bot | 无暴露端点,但要管理轮询进程 |
| 复杂度 | 低(已有 FastAPI + 公网 HTTPS) | 中(进程生命周期 / 重连) |

推荐 **webhook**:基础设施已就位(单 VPS + Caddy + 公网 HTTPS),无需新常驻进程。

### 3.4 绑定关系存哪(决策点 D2)

- **bound chat_id**:复用现有 `notification_config.tg_chat_id`(已存在,String 64)—— 语义从「手填」变「/start 写入」。
- **pending binding token**:两选一 —
  - **Redis**(推荐):`tg_bind:{token} → user_id`,TTL 原生,**零 PG 迁移**。
  - PG 新表 `telegram_binding_token`:持久、可审计,但要迁移 + 清理过期行。
- **反查 chat_id→user**:绑定本身按 token 查,不需要反查;但为防一个 chat_id 绑多个账号,建议给 `tg_chat_id` 加**唯一索引**(需迁移)。

---

## 4. 移除飞书(干净拆除清单)

逐处删除,**不影响 TG / 不影响下单 emit**:

- 删文件:`services/notifications/feishu.py`。
- `dispatcher.py`:删 `feishu` import(L17)、飞书派发分支(L93-102)、`send_test` 飞书分支(L128-140)。
- `templates.py`:删 `render_feishu` / `render_feishu_test` 及其 helper。
- `schemas/notifications.py`:删 `feishu_webhook_url`、`has_feishu` 等字段。
- `models/notification.py`:删 `feishu_webhook_url` 列 → **PG 迁移 drop column**。
- `api/v1/notifications.py`:`POST /test` 的 `channel` 只剩 `telegram`;文档串更新。
- 前端:`notifications-config-section.tsx` 删飞书卡;`lib/api/notifications.ts` + 类型删飞书字段。
- 测试:`tests/api/test_notifications.py`、`tests/services/test_notifications_dispatcher.py`、`test_notifications_clients.py`、`test_notifications_emit.py` 里引用 `feishu_webhook_url` 的用例全部改写/删除。

---

## 5. 现有通知类型迁移(成交 + 价格异动)

emit 链路(engine emit / price_alerts worker / Celery task)**结构不变**,只改 dispatcher 的「怎么发 TG」:

- **改前**:`telegram.send(config.tg_bot_token, config.tg_chat_id, ...)`(per-user token)。
- **改后**:`telegram.send(settings.tg_bot_token, config.tg_chat_id, ...)`(**全局 token** + 用户绑定的 chat_id)。
- 派发条件:`feishu` 整条删;TG 条件从 `tg_bot_token AND tg_chat_id` 变成 **`tg_chat_id` 非空(已绑定)**。
- 模板:只保留 `render_telegram*`。「成交绝不绿色 / 价格异动可用行情色 / 必带免责」规则原样继承。
- `config.py` 新增 `tg_bot_token`(从 env 读,全局),这是**唯一新增的全局配置**。

---

## 6. 数据模型变动 + PG 迁移 + 零回归

### 6.1 PG 迁移(**需要** · 高风险档)

一个迁移(down_revision = 当前 head `d8e2f4a5c7b9`):

1. `DROP COLUMN notification_config.feishu_webhook_url`
2. `DROP COLUMN notification_config.tg_bot_token`(token 移到全局 env)
3. (可选)`tg_chat_id` 加唯一索引(决策点 D2)
4. (可选)新增 `tg_bound_at` / 绑定状态列,或保持「`tg_chat_id` 非空 = 已绑定」的极简语义
5. **数据迁移**:把所有现存 `tg_chat_id` **置 NULL**(旧 chat_id 对应旧 bot,换统一 bot 后失效;不清空会发到错误/失效目标)→ 所有用户需重新 `/start` 绑定。

> 降级路径:迁移要写 downgrade(重新 add 两列,nullable)。但 drop 列会丢数据(旧飞书 url / 旧 token)—— 属**有损迁移**,需产品方知情(决策点 D3)。

### 6.2 零回归考量

- **下单主链路**:emit 仍 fire-and-forget,绝不阻塞;dispatcher 改动只在 worker/异步侧,下单 200 不受影响。✅
- **价格异动 worker**:扫全量 watchlist 的逻辑不变,只是派发目标变;dedup key 不变。✅
- **存量用户**:飞书用户失去飞书、TG 用户旧 chat_id 失效 → **全部需重新绑定** → 必须有 in-app 提示 + 重绑引导(决策点 D3)。这是本次最大的用户感知变更。
- **测试**:现存通知测试大量引用飞书 + per-user token,需同步重写,否则 CI 红。

---

## 7. 分期建议 + 风险点 + 决策点

### 7.1 分期(每期都 = 高风险档:碰已上线通知核心 / PG 迁移 → feature 分支 + 等审 + 单独部署)

| 期 | 范围 | 关键产出 |
|---|---|---|
| **G1** | 统一 bot 接入 + 入站 + /start 绑定(后端) | `config.py` 全局 token;`/telegram/webhook` 路由 + secret 校验;binding token(Redis)+ `/start` 处理 → 写 `tg_chat_id`;不动飞书、不删旧字段(可灰度) |
| **G2** | 派发切换 + 移除飞书 + PG 迁移 | dispatcher 改全局 token;删飞书全链;迁移 drop 2 列 + 清空旧 chat_id;测试重写 |
| **G3** | 前端重做设置页 | 「绑定 Telegram」按钮 + 二维码/deep link + 已绑定/未绑定态 + 解绑;删飞书卡 + 旧手填框;重绑提示 |
| **G4** | 自验 + 真机绑定走查 + ADR 0024 定稿 + 分期部署 | 用真 bot 实测 /start→绑定→下单→收推送;0024 状态改 Accepted |

> 顺序考量:G1 先上(纯新增、可与旧并存)降低风险;G2 才动迁移 + 拆飞书(不可逆);G3 前端跟上;每期独立 PR + review。

### 7.2 风险点

- **R1 有损迁移**:drop 飞书 url + per-user token 不可逆,旧值丢失(可接受,但需知情)。
- **R2 chat_id 失效**:存量 TG 用户必须重绑,否则静默收不到推送 → 必须有显眼重绑提示。
- **R3 webhook 安全**:公开端点必须校验 Telegram `secret_token`;否则可被伪造 update 乱绑。
- **R4 单点 secret**:全局 bot token 泄露 = 所有用户推送可被冒发 → 进 Secrets,不进 git/前端/DB。
- **R5 emit 零回归**:改动须严格限制在异步/worker 侧,绝不让下单路径多一次同步等待。
- **R6 部署期**:迁移 + 删字段那一期,按已收口的部署流程(force-recreate 安全网 + PG 迁移先确认)走。

### 7.3 决策点(最终结论 · 产品方已拍板 2026-05-27)

| # | 决策 | 最终结论 |
|---|---|---|
| **D1** | 入站机制 | **webhook**(`/api/v1/telegram/webhook`)。 |
| **D2** | pending token 存储 / 唯一约束 | **Redis**(`tg_bind:{token}→user_id`,短 TTL,零迁移);`tg_chat_id` **加唯一索引**(防一个 chat 绑多账号)—— 唯一索引属 PG 迁移,**放 G2**;G1 先在应用层做「一 chat 一账号」校验。 |
| **D3** | 存量用户处置 | **接受有损迁移**:清空旧 `tg_chat_id` + 删飞书,所有现存 TG/飞书用户**需重新绑定**。**必须做显眼重绑提示**(设置页横幅 + 推送失败时提示)。(执行在 G2/G3) |
| **D4** | 建 bot | 产品方**已建好 bot、已拿到 token**。token 由产品方自行存入 **GitHub Secrets**,绝不进对话 / 代码 / 前端 / DB。代码侧只从 env 读(见 §3.1 + G1 报告)。 |
| **D5** | ADR 编号 | **新号 0024** supersede 0009。 |
| **D6** | 测试按钮 | **保留**「发送测试消息」,改成测**统一 bot**。 |
| **D7** | 解绑 / 重绑 | 设置页**提供解绑 + 重新绑定**(前端在 G3,后端解绑端点随 G3 接)。 |
| **D8** | 飞书拆除时机 | 按 **G2 一次性删干净**。 |
| **D9** | bot 品牌(用户名/头像/简介) | 产品方稍后定,**G3 做前端时再确认**,本期及 G1 不卡(`tg_bot_username` 配置项留空亦可)。 |
| **D10** | 绑定 UX | 设置页给 **deep-link 按钮 + 二维码 both**(前端在 G3)。 |

> 红线复述:bot 所有文案必带「仅供参考,不构成投资建议」;只推虚拟交易,绝不接真实下单。

### 7.4 G1 实现说明(本期 · 纯新增 · 与旧逻辑并存)

- 后端:`config.py` 全局 `tg_bot_token`(env)、`/telegram/webhook` 路由(Telegram `secret_token` 头校验)、`/telegram/bind-token` 生成一次性 Redis token、`/start <token>` 入站绑定写 `notification_config.tg_chat_id`、启动后台自动 `setWebhook`。
- **G1 不动飞书、不删旧字段、无 PG 迁移**;唯一索引 + 删飞书 + 清空旧 chat_id 全部留 G2。
- webhook secret 由 `SECRET_KEY` 派生(HMAC),不新增第二个 secret。
- 产品方只需在 GitHub Secrets 加 **`TG_BOT_TOKEN`** 一项(详见 G1 交付报告)。

---

## 8. 备注

- 本文不含实现代码,不改任何运行代码 / 界面;只是方案。产品方就 §7.3 决策点拍板后,按 §6 分期落地。
- 0009 v1 的「明文存 token」「M1 defer 项(频率/静默时段/加密)」等仍适用于 v2 的 chat_id 存储考量。
- 邮件(Resend)继续与通知系统分离,不受本次影响。
