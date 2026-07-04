# 点金 Midas · TG 通知系统 · 可移植设计参考

> 面向:**要在一个新系统里实现同类 IM 通知能力的开发者**。
> 写法:重点讲**设计思路 + 架构决策 + 为什么这么设计 + 踩过的坑**,不是罗列点金代码。
> 方法:7 镜头只读调研(架构 / 分类触发 / 身份绑定 / 可靠性 / 交互命令 / 配置开关 / 踩坑)。
> 语言/框架无关的原则会明确标出;点金特有(交易/全虚拟/东八区/跨境 VPS)的会标"不必带走"。

---

## 0. 一句话总纲

**这套系统的骨架 = 事件驱动 + 异步队列 + 多层适配 + 单一派发门面。**
业务代码只"emit 一个事件",剩下的"发给谁 / 什么时候 / 走哪个渠道 / 怎么渲染 / 怎么重试 / 怎么降噪"全部收敛在一条链路里,每一层职责单一、可单测、加渠道不改内核。

贯穿始终的三条哲学:
1. **业务与传输解耦**——主链路(下单/业务)绝不被通知拖垮,通知 best-effort。
2. **身份推导而非声明**——"谁在操作"只从系统能独立验证的凭证推导,绝不信任消息内容。
3. **本地能 ≠ 第三方能**——TG 是你控制不了的、跨境的、有自己解析器和重试的黑盒,别假设它像 `curl` 一样宽容。

---

## 1. 整体架构

### 1.1 接入方式:Webhook(不是 Polling)

**结论:webhook。** 启动期(lifespan startup)后台异步调 `setWebhook` 注册一个公网 HTTPS 端点,TG 有 update 就 POST 过来。

**为什么 webhook 而非 polling:** ① 实时(无轮询延迟)② 无常驻进程(polling 要养一个后台循环)③ 资源省(被动接收 vs 主动定时查)④ 与 FastAPI 天然集成(就是加一个 POST 路由)。

**注册的工程细节(可直接抄):**
- **失败 fail-soft**:注册在启动后台任务里做,失败只 log 不阻塞应用启动(TG 暂时不可达不该拖垮整个服务)。
- **幂等**:`setWebhook` 可重复调,重复注册自动覆盖旧的。
- **URL 从配置拼**、必须 HTTPS(TG 硬要求)。

### 1.2 出站(推送)链路:五层解耦

```
业务层         emit_trade_filled(order_id)          ← 只丢一个事件,~5ms,不阻塞
   ↓ Celery send_task
消息队列       Redis broker (CELERY_BROKER_URL)      ← 生产者写,worker 消费
   ↓ worker 进程
Worker 任务    @shared_task(max_retries=3, 退避2/4/8s) ← 从 DB 重构对象,调 dispatcher
   ↓ dispatch(db, user_id, event)
派发层         dispatcher.dispatch()                 ← ★核心编排:发谁/哪些渠道/时段/开关
   ↓ 逐渠道
适配层         adapters/telegram.py / feishu.py      ← 事件→该渠道文案,失败隔离成 ChannelResult
   ↓
传输层         notifications/telegram.py send()      ← httpx 裸 POST Bot API,失败抛异常
   ↓ httpx.AsyncClient
           https://api.telegram.org/bot{token}/sendMessage
```

**各层职责与为什么这么分:**

| 层 | 职责 | 关键设计 |
|---|---|---|
| **emit** | 业务触发点。只 `send_task` 丢队列,不碰 token / 渲染 | ★fire-and-forget:broker 挂了只 log 不抛;★**在事务 commit 之后 emit**(否则"通知发了但事务回滚"=幻影成交) |
| **broker** | 任务队列(Redis) | 让"业务动作快、推送慢"物理分离 |
| **worker task** | 异步执行体。查库 + 重构对象 + 调 dispatcher | ★重试只在这一层做(见 §4) |
| **dispatcher** | **平台无关**编排:查用户配置 → kind 订阅开关 → 安静时段 → 逐渠道发 | 所有通知源复用同一套"发不发"逻辑,不散落到上游;通道失败独立成 `ChannelResult` 绝不抛 |
| **adapter** | 平台适配:事件 → 该渠道文案 → 调 transport | 加飞书/钉钉 = 加一个 adapter,dispatcher 一行不改 |
| **transport** | 最贴 API 的一层:`httpx` 裸调 `sendMessage`/`sendPhoto`/`editMessageText` | 无业务逻辑,纯 HTTP 包装,失败抛 `TelegramApiError` 给上层 catch |

### 1.3 用什么库:httpx 裸调 Bot API(不用框架)

**不用 `python-telegram-bot` 之类框架,直接 `httpx.AsyncClient` POST Bot API。** 理由:① 轻量(框架庞大,只用 sendMessage/sendPhoto/editMessageText/answerCallbackQuery 几个方法)② 完全可控(timeout、error handling、retry 策略自己定)③ 与 FastAPI+Celery 异步栈无缝。
> ★可移植判断:如果新系统只用少数几个 Bot API 方法,裸 httpx 比引框架更划算;要用到会话管理/复杂 update 类型时再考虑框架。

### 1.4 凭证管理

| 凭证 | 存哪 | 说明 |
|---|---|---|
| **Bot Token** | 环境变量(`.env`) | 单个全局统一 bot(旧的"每用户自带 bot"已废弃,见 §7 坑7) |
| **Webhook Secret** | **由主 SECRET_KEY 经 HMAC-SHA256 派生**(取 48 位) | ★一源多用:不新造第二个密钥;`setWebhook` 注册和入站头校验用同一个 |
| **Chat ID** | DB `notification_config.tg_chat_id`(每用户一行) | 用户绑定时写入(见 §3) |
| **Admin 告警 Chat** | 环境变量(可选) | 运维/熔断告警发给 admin,未配则不发 |

### 1.5 入站与出站是两条独立链路

```
出站:业务 emit → Celery → worker → dispatcher → adapter → TG API      (单向推送,异步无时间压力)
入站:TG → POST /webhook → secret校验 → 解析update → 路由             (交互,必须同步快速回 200)
        ├─ /start <token>  → 绑定逻辑
        └─ /menu·/price·裸代码·按钮 → bot router → 查询/下单 → 回复
```
分开的理由:① 认证方式不同(入站靠 webhook secret,出站靠用户配置)② 时序不同(入站必须秒回 200 防 TG 重试风暴,出站异步)③ 业务不同(入站交互式,出站单向)④ 可独立扩展。

---

## 2. 通知的分类与触发

### 2.1 分类:frozen dataclass 事件树 + StrEnum kind(单一事实源)

**不用裸 dict / 字符串,每类通知一个 `@dataclass(frozen=True)` 事件类**,字段即契约。一个事件对象同时喂给"bot 富回执""worker 异步推送""多通道渲染",文案/字段只有一处定义。

```python
class NotificationKind(StrEnum):
    TRADE_FILLED = "trade_filled"; PRICE_ANOMALY = "price_anomaly"
    ALERT_TRIGGERED = "alert_triggered"; PERP_FILLED = "perp_filled"
    LIQUIDATION = "liquidation"; ...

@dataclass(frozen=True)
class TradeFilledEvent:
    quiet_exempt: ClassVar[bool] = True          # ★钱相关:不受夜间安静时段拦截
    kind: Literal[NotificationKind.TRADE_FILLED] = NotificationKind.TRADE_FILLED
    symbol: str = ""; side: Literal["buy","sell"] = "buy"; pnl: float | None = None

NotificationEvent = TradeFilledEvent | PriceAnomalyEvent | AlertTriggeredEvent | ...  # 联合类型
```

点金的 9 类事件:现货成交 / 永续成交 / 强平 / 价格异动(±5%)/ 自定义告警规则命中 / 做T全景 / 做T转换 / 周报已发 / 周报未上传(仅 admin)。

**★最漂亮的一招:`quiet_exempt: ClassVar[bool]`** —— 把"是否受夜间免打扰拦截"编进**类型系统**而非散落在 `if event.kind in [...]` 里。钱相关(成交/强平/资金费)=True(半夜也不能漏),市场噪音(价格异动/告警)=False。新增事件时作者被**强制**显式声明豁免与否,不会忘。dispatcher 只需 `getattr(type(event), "quiet_exempt", False)` 一行判定。
> ★可移植:任何"某些通知紧急、某些可静默"的系统都该这样把业务语义下沉到类型。

### 2.2 触发:两种范式,按"有无确定性业务事件"二分

| 范式 | 用在 | 机制 | 判据 |
|---|---|---|---|
| **事件驱动** | 交易成交 / 强平 | 业务代码在 `commit` 后 `emit` 事件 | 能在代码里精确捕捉到"刚发生了 X"(下单成交) → 零延迟零轮询、天然不漏不重 |
| **定时扫描** | 价格异动 / 告警规则 / 做T推送 | Celery beat 每分钟扫 ClickHouse 快照 | 只能观测"连续状态穿越阈值"(RSI>70、±5%),没有离散事件点 → 只能周期观测 |

### 2.3 ★定时扫描的灵魂:边沿触发状态机(降噪根治)

定时扫描的致命问题是**刷屏**。点金最初用"时间窗去重(cooldown 内不重发)",结果 **RSI 卡在超买区每 5 分钟推一条、一天 288 条**(9 条规则叠加彻底刷屏)。

**根治 = 边沿触发(edge-triggered)状态机**:Redis 存每条规则的持久态 `not_triggered/triggered`,**只在 `not_triggered → triggered` 状态跳变那一刻推一次**,持续触发期不重推,值回落再进才再推。cooldown 从"去重主力"降级为"防 mark 价抖动反复跨阈值"的护栏。

```python
curr = "triggered" if rule_hit else "not_triggered"
prev = await redis.get(f"alert:state:{rule_id}")            # None=首次
if prev == "triggered" and curr == "not_triggered":
    await redis.set(state_key, "not_triggered"); continue   # 复位,不推
if curr != "triggered" or prev == "triggered":
    continue                                                # 持续态,不推
if await redis.get(cool_key):                               # cooldown 护栏
    continue
disp = await dispatch(db, rule.user_id, event)
if disp.any_sent:
    await redis.set(state_key, "triggered"); await redis.set(cool_key, "1", ex=cooldown)
elif disp.dropped_quiet:
    await redis.set(state_key, "triggered")   # ★被安静时段吞掉也要写状态,否则下轮反复空转
```
> ★可移植:**凡"阈值告警"类系统必撞刷屏坑,这是通用根治方案。** 状态存 Redis 而非 DB 表是 lean 取舍(零迁移;代价是 Redis 重启丢状态多推一次,可接受)。

### 2.4 消息组装:渲染层与事件层分离

- **推送类**(单向、精简)走 `templates.render_telegram(event)`——按 `isinstance` 分派到 per-event 渲染函数,统一品牌头「点金 Midas · X」、统一金额/价格格式化(固定 2 位 vs 动态精度,单一事实源)、**统一用 emoji 标方向(🔴/🟢/📈/📉)而不依赖颜色**(见 §7)。
- **交互类**(双向、按钮)走通道中立的 `ReplyModel`(title/text/按钮行列/disclaimer 字段)→ 每通道一个 renderer 渲成 TG `inline_keyboard` 或飞书 interactive card。

---

## 3. ★用户身份与绑定(最值钱的可移植安全设计)

### 3.1 一句话原则:身份是**被推导**出来的,永远不是**被声明**出来的

"谁在操作"这个问题的答案,**唯一地锚定在【已通过传输层验签的 webhook 事件体里那个平台原生 uid】上**,任何用户可控的文本一律不采信。

### 3.2 三段信任链

1. **绑定阶段**——一次性短 TTL token 把 IM 侧 `chat_id` 和系统侧 `user_id` 建映射:
   - 登录态后端生成随机 token 存 Redis(`tg_bind:{token} → user_id`,TTL 10min),拼成 `t.me/bot?start=<token>` **deep link**。
   - 用户点开 → IM 自动发 `/start <token>` → webhook 拿 token 反查 `user_id` 写绑定。
   - **一次性 token = 防盗绑**(别人拿不到你的链接就绑不了你的账号);**短 TTL = 限泄露窗口**;成功即 consume。
   - ★注意:token 是 **peek(不删)+ 全部校验通过后才 consume** 两步,不是 get-and-delete 一步——中途失败 token 仍有效可重试。
2. **入站阶段**——webhook 先验签(TG:`X-Telegram-Bot-Api-Secret-Token` 头 + `hmac.compare_digest` 常量时间比较;飞书:Verification Token + 可选 AES 解密 + 签名)。**只有验签通过的事件体里的 `chat.id`/`open_id` 才被信任,这是身份的唯一注入点。**
3. **业务阶段**——核心层 `resolve_user_id(channel, channel_uid) → user_id`,把平台 uid 翻成系统 user_id;之后所有下单/查询/改配置只吃这个 `user_id`。

### 3.3 ★红线:核心业务函数签名**物理上不接受** chat_id / uid 参数

```python
# 只有最外层 router 这一层调:
user_id = await resolve_user_id(channel, verified_channel_uid)
# 下游所有业务模块函数签名【只收 user_id】,收不到 chat_id / target_uid:
async def place_order(db, *, user_id: int, market, symbol, side): ...
async def update_quiet_config(db, *, user_id: int, ...): ...
```
**这不是"约定不要传",而是"结构上没法传"。** 把安全性从"每个 caller 的自觉"降维成"类型签名的必然"——新加的 caller 不可能漏、不可能越权改到别人的数据。

> ★这跟点金**交易系统 REST 鉴权同源**:REST 里 `user_id` 只从 Bearer session token 反查、端点签名绝不接受前端传入的 `user_id`;bot 只是把凭证来源从 token 换成"已验签 webhook 的 chat_id",鉴权边界思想一模一样。**新系统若已有 token 鉴权的 REST,加 IM bot 时直接套用同一原则,不要为 bot 破例。**

### 3.4 会话态只存"意图",不存"身份"

多步交互(选标的→选方向→确认)跨多个 webhook 请求。会话(Redis)**只存 `{step, market, symbol, direction}`,绝不存 user_id**;每次确认都从当前请求的**已验签 channel_uid 重新解析身份**。→ 会话被串改最多让你对**自己**的账号下错单,永远改不到别人。

### 3.5 一 chat 一账号:应用层查 + DB partial 唯一索引双层

防一个 TG 绑多个系统账号(否则推送/身份串)。应用层先查"该 chat_id 是否已被别人绑",DB 再加 **partial unique index `WHERE tg_chat_id IS NOT NULL`** 兜底并发。partial 是关键——允许多个用户都"未绑定(NULL)",只对非空值唯一。

---

## 4. ★可靠性设计

哲学:**「主链路绝不被通知拖垮,通知本身尽力而为」。** 拆成两条独立轴:【投递不阻塞业务】+【投递不刷屏用户】。

### 4.1 投递不阻塞:fire-and-forget + 重试只在一层

- **emit fire-and-forget**:业务只往 broker 丢任务(~5ms),broker 挂了只 `log` 不抛(用户已看到下单成功,漏一条通知远比卡住下单可接受)。
- **★重试只在最贴 transport 的一层(Celery task)做**:`max_retries=3` + 指数退避 2/4/8s。**上层(emit/dispatcher/前端)一律不叠加重试。**
  > ★血泪教训:前端 retry × 后端 retry 双层叠加 = 用户等 44s 才见错误。**分层重试的时长是【相乘】不是相加。** 规则:选定一层(通常最贴网络调用那层)做退避,其余所有层显式设 0。

```python
def emit_trade_filled(order_id: int) -> None:      # ★commit 之后调用
    try:
        _celery.send_task("tasks.notifications.send_trade_notification", args=[order_id])
    except Exception as e:                          # noqa: BLE001 — broker 挂了不拖垮下单
        logger.warning("[emit] failed order_id=%s err=%s", order_id, e)
```

### 4.2 投递不刷屏:边沿状态机(见 §2.3)+ 安静时段

安静时段(quiet hours)在 dispatcher **单点拦截**,钱相关事件用 `quiet_exempt` 声明式豁免(见 §2.1)。

### 4.3 多通道失败隔离

两通道(TG/飞书)都绑则都发,**任一失败 catch 成 `ChannelResult(ok=False, error=...)` 数据、绝不向上抛异常**。把"失败"建模成数据而非异常——① 一个通道挂不拖累另一个 ② 不触发 Celery 无谓重试 ③ 上层用 `any_sent`/`any_error` 做决策(如边沿状态机只在 `any_sent` 时才写 `triggered`)。

### 4.4 渐进降级

TG 发图(K 线 PNG)失败 → **自动回退发文本 + 网页链接**。核心信息(去哪看)保证送达,富媒体(图)尽力而为。"别让用户啥都收不到"。

### 4.5 频控与熔断——注意哪些是"规模/风险才需要"

- **频控**:Redis 固定窗口计数 + **fail-open**(Redis 异常时**放行**)。限流是"防滥用护栏"不是"安全边界",不该因 Redis 抖动把正常用户挡外面(且下单有引擎保证金校验兜底、全程虚拟)。`fail-open vs fail-closed` 取决于"挡错代价 vs 放错代价"。
- **熔断**:**只做在"连续失败 = 平台封号"的高风险外发**(如 X/Twitter 自动发推,连续失败 3 次熔断 + 撤销排队任务 + TG 提醒 admin)。**普通用户 TG 通知不做熔断**——用户失败是**每人独立**的(A 的 chat 失效不代表 B),没有系统性传染,做熔断反而误伤,Celery 的 `max_retries` 已够。

---

## 5. 交互命令(bot 作为迷你终端)

### 5.1 三类入站 + 一条有序 dispatch 链

支持:① 斜杠命令(`/start` `/menu` `/price`)② 自由文本(裸代码/中文名秒查)③ 按钮回调(inline + 常驻 reply keyboard)。

**核心:不把它当"命令解析器",而当"优先级有序的 dispatch 链 + Redis 短期会话态状态机"。** `_handle_text` 是一条**严格有序的 if 链,顺序本身就是语义**:
```
常驻键盘按钮文字(「📊 行情」) ── 必须最先拦截,否则被当中文股票名去搜
  → /start coin_<SYM> 深链 ── 必须在主菜单 /start 之前分流
  → 命令(/menu·/price)
  → 会话态续输(处于 order_symbol/order_direction 态)
  → 自由文本启发式(疑似代码 / 疑似中文名 / 落兜底提示)
```
顺序被注释**显式锁死为红线**(如"★必须在 `_looks_like_name` 之前"),并有单测守卫,防后人乱插分支引回归。

### 5.2 多步会话态存 Redis(不建 PG 表)

对话上下文是易失的、5 分钟就该丢的临时状态。`setex(300s)` 存 `{step, market, symbol, direction}` JSON——天然自过期、零迁移、并发安全。router 是这个状态机的**无状态转移函数**:读当前 step → 处理本步 → 写下一步 → 返回该步 `ReplyModel`。每步校验前置 step(下单执行只在 `step==order_confirm` 才跑)。

### 5.3 自由文本:轻量纯函数启发式分流

`_looks_like_symbol`(单 token/≤15 字符/仅字母数字斜杠)→ 扫库判市场;`_looks_like_name`(含非 ASCII 中文)→ 名称搜索;像句子的落 `build_hint` 推回菜单。**纯函数,天生可单测。**
> ★坑:裸代码别"猜"市场("btc"猜成美股查不到)——改成**扫库判定**(统一 upper 后探 `XXX/USDT` + 美股 `XXX`,命中即出)。"本地/直觉能 ≠ 真实存在"。

### 5.4 两种键盘并用

- **inline keyboard**:卡片内导航 / 多步流程(`callback_data` 精确路由,如 `qk/qo/qr:market:symbol`)。
- **reply keyboard**(`is_persistent`):输入框上方常驻快捷菜单(行情/K线/持仓/自选/下单),任意状态一键发起高频动作。
- ★坑:**一条消息只能挂一种 markup**(inline 和 reply 不能同发)→ reply-kb 单独发一条、只在"绑定成功"和"裸 /start"两个时机设置(否则刷屏)。reply-kb 点击 = 一条**普通 text 消息**,所以其按钮文字必须在 dispatch 顶部精确拦截(见 §5.1)。

### 5.5 危险操作(下单)= 三件套锁死

**会话 step gate + 二次确认按钮 + 唯一执行点**:`execute` 只在检测到 `order_confirm` 会话态才跑;任何通道、任何 callback 都无法从前面的 step 跳过确认直达成交;确认时**重新解析身份**(见 §3.4)。「危险操作既要身份可信、也要状态机可信」——两道门。

---

## 6. 配置与开关(通知策略层)

### 6.1 单一 dispatch 门面 + 三层正交策略

**所有通知源只 `emit` 事件,一个 `dispatch(user, event)` 按固定顺序做过滤**,过滤逻辑不散落到上游:
```
渠道未绑 → 静默跳过 ┃ kind 订阅开关关 → 丢弃 ┃ 在 quiet 窗口且非豁免 → 丢弃 ┃ 否则逐渠道发
```
三层**正交、互不耦合**:
- **【收哪些】** per-user kind 订阅开关:`NotificationConfig` 每用户一行、每种事件一个布尔列(`trade_alert_enabled` / `price_alert_enabled` / `weekly_report_enabled` / …)。列级开关比一个 JSON blob 更好加 partial 索引和 SQL 过滤。
- **【什么时候】** per-user 安静时段:`quiet_hours_enabled/start/end/tz`。
- **【哪个渠道】** 按用户绑没绑决定:`tg_chat_id` 非空发 TG、`feishu_open_id` 非空发飞书,都绑都发。

### 6.2 安静时段的工程细节(可直接抄)

- 跨夜/时区/禁用全收进**一个纯函数** `_hour_in_quiet_window(hour, start, end)`,dispatcher 和老代码共用单一事实源:
  - 跨夜(`start > end` → `hour >= start OR hour < end`);
  - **`start == end` 定义为"禁用"**(想全天静默用真跨夜窗口 + `enabled=True`,想关闭用 `enabled=False`)——避免语义歧义。
- **时区存 IANA 名 per-user**(默认 `Asia/Shanghai`),用 stdlib `zoneinfo.ZoneInfo(v)` 尝试构造来校验合法性(非法则 422),不自维护白名单;存 IANA 名而非 UTC offset 能正确处理夏令时。

### 6.3 配置单一事实源:落 DB

网页 `PUT /notifications/config` 和 bot 按钮**都写同一张 `NotificationConfig` 表**,引擎只读、下次 beat tick 自动拿到新值。不存在两套状态。
- PUT 用 **"None 字段 = 不动"** 的局部更新语义(前端只传要改的字段)。
- ★bot 侧配置**绝不回调自己的 REST**(self-loopback 徒增一跳还可能鉴权打架)——直接走同款 model 写 DB。
- **lazy-create**:首访无行时返默认对象、写时才 INSERT(不为每个注册用户预建配置行,GET 不用返 404)。

### 6.4 两类更高层开关

- **全局 env kill-switch**(如 `dott_push_live` 默认 `False` = 影子模式,只 `logger` 不真发)——某功能一键回退到"不真发"**不用改代码/回滚**(紧急刹车)。
- **per-user Redis feature flag**(默认 OFF、每轮 worker 读最新 → 改开关即时生效)——适合 admin 频繁开关 / per-user 灰度,零迁移。key 用 `None → 全局兼容旧全局开关`(向后兼容巧法)。
- ★极性别搞反:默认 ON 用 `!= "0"`(未设视为开)、默认 OFF 用 `== "1"`(未设视为关)。

### 6.5 广播类(周报/做T)的订阅开关一物二用

`*_enabled` 列既是 dispatch 的"发不发"门,**又是广播时圈定收件人的 SQL WHERE 条件**(`WHERE enabled=true AND tg_chat_id IS NOT NULL`,避免全表遍历),再逐人 dispatch 二次确认(双保险,发送前再查 Pro 资格)。订阅类默认 `false`(opt-in,不给存量用户群发未请求的消息),核心告警类默认 `true`。
> ★坑:默认极性要在 model `server_default` + Pydantic 默认值 + `default_config_response` **三处对齐**,否则"未配置用户"在 GET/dispatch/lazy-create 三条路径行为不一致。

---

## 7. ★踩坑清单(可移植警示——最值钱的部分)

母题:**「本地/受控环境能 ≠ 真实第三方环境能」。**

| # | 坑 | 根因 | 怎么避 |
|---|---|---|---|
| **1** | **TG legacy Markdown 转义(最贵)**:`parse_mode="Markdown"` 遇 LLM 输出的 `**粗体**`/`### 标题`/`---` 返 **400 can't parse entities**,错误被 catch 吞掉 → **静默 `sent=0`**(邮件正常,极难定位) | legacy Markdown 解析器不认 `**`/`###`(那是标准 Markdown/MarkdownV2);受控模板安全(作者不放裸符号 + 大量 emoji),但任意/LLM 文本一进同一发送链路就炸 | **分流,不是写完整转义器**:受控模板走 `Markdown`;**任意/LLM 内容一律 `parse_mode=""` 纯文本 + 轻量去符号**(`**x**`→x、`### x`→x、`- x`→`· x`)。或写全套 MarkdownV2 转义器(转 15 个保留字 `_*[]()~\`>#+-=|{}.!`),二选一,**别在同一链路混用** |
| **2** | **sendPhoto 跨境拉图**:传 `photo=<公网URL>` 让 TG 国外服务器回拉香港 VPS,**本地 `curl` 200,真机收到的是 fallback 文本** | TG 服务器跨境拉香港 VPS 超时/失败(墙/跨境网络),不是画图错;断点精确在"画图之后、TG 收图之前" | **不让第三方服务器回拉你的资源**:后端自拉图片 `bytes` 走 `multipart` 上传;发图是增强,**失败必回退文本链接**别让用户啥也收不到 |
| **3** | **webhook 是公开端点可被伪造** | IM webhook 天然是不可信输入,不校验就能伪造 update 触发绑定/下单 | secret_token **`hmac.compare_digest` 常量时间比较**(防时序侧信道);secret 由主 SECRET_KEY 派生;user_id 只从已验签 channel_uid 解析(连只读查询也走同一解析) |
| **4** | **webhook 解析失败回 5xx → TG 重试风暴** | TG 对非 2xx 的 update 会 at-least-once 反复重试同一条 | 解析失败/未知 update/缺 chat_id **一律回 `{"ok":true}` 200 静默丢弃**;只有 secret 校验失败回 403;真正业务全丢 `BackgroundTasks` 异步做,webhook 本体永远快速回 200 |
| **5** | **retry 分层叠加 = 44s 卡死** | 前端 retry × 后端 retry,时长相乘 | 重试只在最贴 transport 一层做 + 指数退避,其余层显式 `retry=0`(见 §4.1) |
| **6** | **告警刷屏(RSI 卡区间日推 ~288 条)** | 混淆 **time-based dedup(时间窗去重)** 和 **edge-triggered(状态过渡触发)**;cooldown 只控"重发间隔",控不了"值持续卡在阈值内" | 边沿状态机(`not_triggered→triggered` 才推)+ cooldown 退化为抖动护栏 + 安静时段(钱相关 `quiet_exempt` 豁免)(见 §2.3)。**别一上来就写 cooldown 以为够了** |
| **7** | **换统一 bot 时旧 chat_id 全失效** | `chat_id` 是 `(bot, chat)` 对的标识,**不是全局用户 id**;换 bot 后旧值全失效,不清空会发到失效目标、用户静默收不到还不知道 | 迁移时把旧 `tg_chat_id` 置 NULL + 强制全员重绑 + **显眼重绑提示**(设置页横幅 + 推送失败时提示),否则是静默回归 |
| **8** | **飞书事件 open_id 结构不统一** | 菜单事件 open_id 藏在嵌套 `operator.operator_id.open_id`,card 事件是扁平 `operator.open_id` | 按事件类型**分别写解析函数**,不能一套代码套所有事件,否则拿到 None 静默失败 |
| **9** | **AI/动态内容合规** | LLM 生成的推送可能含买卖祈使/缺免责 | 发出前过 **fail-closed 合规门禁**(缺免责/含买卖祈使词直接 `raise` 拒绝,**不静默改写**)。点金特有但"动态内容发出前经纯函数守卫、拒绝而非改写"的模式可移植 |

---

## 8. ★可移植性总结

### 8.1 最小核心(直接抄,任何语言/IM 平台都成立)

1. **五层解耦骨架**:`emit(fire-and-forget) → broker → worker(重试在此) → dispatcher(平台无关编排) → adapter(per-channel 渲染) → transport(裸 HTTP)`。加渠道 = 加一个 adapter,内核不动。
2. **事件 = frozen dataclass 树 + 枚举 kind**,单一事实源;紧急/静默语义用**类属性(如 `quiet_exempt`)编进类型**。
3. **身份推导而非声明**(§3):身份只从已验签事件的平台 uid 解析;**核心业务函数签名物理上只收 `user_id`,不收 `chat_id`/`uid`**——把越权从"自觉"降维成"类型签名的必然"。这是全篇最值钱的一条。
4. **主链路零阻塞**:业务 `commit` 后 fire-and-forget 丢队列,broker 失败只 log;重试只在最贴 transport 一层(时长相乘教训)。
5. **多通道失败隔离**:失败建模成 `ChannelResult` 数据而非异常。
6. **单一 dispatch 门面 + 三层正交策略**(收哪些 / 什么时候 / 哪个渠道),配置落 DB 单一事实源。
7. **webhook 安全五件套**:secret 常量时间校验 / 解析失败回 200 防重试 / user_id 只从已验签 uid / 危险操作二次确认 gate / 限流 fail-open。
8. **绑定**:一次性短 TTL Redis token + deep link + 一账号一 chat(应用层查 + DB partial 唯一索引)。

### 8.2 值得抄(中型系统)

- **边沿触发状态机降噪**(§2.3)——凡"阈值告警"必撞刷屏,这是根治方案。
- **有序 dispatch 链 + Redis 短 TTL 会话态**(§5)——bot 交互路由骨架,顺序即语义 + 注释锁死防回归。
- **两种键盘并用 + 富文本 parse_mode 分流策略**(接 TG 第一天就要定)。
- **全局 env kill-switch + per-user Redis flag** 两级开关(刹车 + 灰度)。

### 8.3 点金特有(不必带走)

- **熔断只做在"连续失败 = 平台封号"的高风险外发**(X 自动发推);普通用户通知不做熔断。
- **全虚拟交易**背景下的 `fail-open` 频控取舍(放错代价极低);有真实副作用的系统要重估。
- 东八区默认时区、香港 VPS 跨境、AI 合规门禁(缠论/免责红线)、做T/周报等业务专属通知类型。

### 8.4 上手顺序(给新系统开发者)

1. 定义**事件 dataclass 树**(带 `quiet_exempt`)→ 2. `emit`(Celery `send_task` 包装)→ 3. worker task(查库重构 + 调 dispatcher)→ 4. **dispatcher**(三层过滤 + 逐渠道 + 失败隔离)→ 5. adapter(事件→文案)→ 6. transport(httpx 裸调)→ 7. 配置 DB model + 网页/bot 双写 → 8.(可选)webhook 入站 + 绑定 + bot router。
**先跑通"单渠道单向推送"(1→6),再加身份绑定/入站交互(§3/§5),最后加降噪/开关(§2.3/§6)。**

---

*7 镜头只读调研产出(架构 / 分类触发 / 身份绑定 / 可靠性 / 交互命令 / 配置开关 / 踩坑)· 全程零改代码 · 面向"在新系统实现同类 IM 通知"的开发者。行号/函数名佐证见各镜头原始调研,可按需深挖。*
