# ADR 0032 · 多通道 Bot 架构 + 飞书接入

- 状态:**Proposed**(待 Claude 审 ReplyModel/零回归/分阶段 + 产品负责人拍板;通过后按阶段实施)
- 日期:2026-05-29
- 关联:0024(TG 统一 bot)、0025(通知 v2 · 移除飞书 per-user webhook · 预留 adapter 插槽)、0009(推送)、0028(降噪/安静时段)
- 决策人:产品负责人(路线一:一步到位做飞书完整交互 bot,并立多通道抽象、为钉钉预留;微信不做)

## 1. 背景与目标

大陆用户 TG 受限,需把现有 TG 全部能力(绑定 / 行情查询 / 下单二次确认 / 告警配置 / 强平·成交通知)做出**飞书对等版**,并把"通道"抽象成通用层,使钉钉将来只是"再加一个适配器"。

现状(见 0032 调研结论):
- **通知侧**已半分层:`dispatcher` + `adapters/telegram.py` 的 `send_event/send_test` 契约就位,注释明写"加飞书=新增 feishu.py 核心层不动"。
- **查询侧**(`services/bot/query.py`)已通道无关(返回 dataclass,无 TG 字符串)。
- **撮合内核**(`order.py` `execute()→OrderResult`、`normalize_symbol`、`quote_price`)通道无关。
- **交互侧 TG 耦合**:`router.py` 返回 `BotReply`、`telegram_ui.py` 12 个 `render_*` 产出 TG `inline_keyboard`、`identity.resolve_user_id(chat_id)` 查 `tg_chat_id`、`api/v1/telegram.py` 解析 TG update + 验签 + `telegram.send`。

目标:**抽象出通道中立的"入站消息 + 出站回复"两个模型**,让业务内核(router 状态机 + order + query)只跟中立模型打交道;每通道实现"传输 + 验签 + 渲染 + 身份/绑定 + token"五件套。**首要约束:TG 行为字节级零回归。**

---

## 2. 通用回复抽象(ReplyModel)+ 入站抽象(InboundMessage)

整个重构的地基。要求:一个出站模型能同时被 TG(`inline_keyboard`)和飞书(interactive card)渲染。

### 2.1 出站 · ReplyModel
```python
@dataclass(frozen=True)
class Button:
    label: str                     # 按钮文案
    action: str | None = None      # 回调动作标识(= 现 callback_data 语义,如 "menu:order")
    url: str | None = None         # 链接按钮(K 线深链);url 与 action 二选一

@dataclass(frozen=True)
class ReplyModel:
    text: str                              # 正文(轻量 markdown 子集 · renderer 决定呈现)
    title: str | None = None               # 标题(TG → *{BRAND} · {title}* 首行;飞书 → card header)
    buttons: tuple[tuple[Button, ...], ...] = ()  # 行 × 列(空 = 无按钮)
    disclaimer: str | None = DEFAULT_DISCLAIMER   # 尾部免责(renderer 追加;None = 不加)
    kind: Literal["text", "card"] = "card" # 呈现风格提示(renderer 可按通道能力降级)
    force_new: bool = False                # 按钮回调默认原地编辑;True 强制发新消息(如成交回执)
```
- **transport(new vs edit)不进 ReplyModel**:由 webhook 层按入站类型决定(message→发新、button→原地编辑),`force_new` 仅作少数例外提示。
- **disclaimer 分层**:不再在 builder 里拼"仅供参考",而是 ReplyModel 带字段、各 renderer 追加(TG 斜体小字 / 飞书 card note)。交易类用「本次为模拟交易,不构成投资建议」,非交易类用「仅供参考,不构成投资建议」(沿用现口径)。
- **action 命名空间保持与现 `callback_data` 完全一致**(`menu:order` / `odir:<dir>` / `ordok` / `ordno` / `rules:toggle:<id>` / `quiet:s+` …)→ 这是 TG 零回归的关键(见 §3)。

### 2.2 入站 · InboundMessage(中立化)
```python
@dataclass(frozen=True)
class InboundMessage:
    channel: str                   # "telegram" | "feishu" | "dingtalk"
    channel_uid: str               # 【已验签事件】里的用户标识(TG chat_id / 飞书 open_id)· 唯一身份来源
    kind: Literal["text", "button"]
    text: str | None = None        # kind=text:用户文本
    action: str | None = None      # kind=button:动作标识(= Button.action)
    reply_ctx: dict = field(default_factory=dict)  # 通道私有透传(TG message_id / 飞书 card 上下文)· 业务层不读
```
- **`channel_uid` 只在各通道 webhook 验签通过后构造**——这是身份红线的物理锚点(见 §6)。

### 2.3 真实例子(同一 ReplyModel,两通道渲染)

**主菜单**
```python
ReplyModel(
  title="迷你终端", text="点下方按钮选择功能 ↓\n\n也可直接发送 /price <代码> 查行情",
  buttons=((Button("📊 行情查询","menu:quote"), Button("📈 K线图","menu:kline")),
           (Button("⭐ 我的自选","act:watchlist"), Button("💼 我的持仓","act:positions")),
           (Button("🛒 下单","menu:order"), Button("🔔 告警规则","menu:rules")),
           (Button("🌙 安静时段","menu:quiet"),)),
  disclaimer="仅供参考,不构成投资建议")
```
- TG renderer → `*点金 Midas · 迷你终端*\n\n...` + 4 行 `inline_keyboard`(callback_data 同 action)。
- 飞书 renderer → interactive card:header="点金 Midas · 迷你终端" + 正文 + 4 行 button 元素(value=action)。

**下单二次确认卡**(红线)
```python
ReplyModel(
  title="下单确认", kind="card",
  text="BTCUSDT · 永续 · 逐仓 20x\n开多 0.5 @ 63,200\n保证金 1,580 USDT · 手续费约 25.28",
  buttons=((Button("✅ 确认下单","ordok"), Button("✖️ 取消","ordno")),),
  disclaimer="本次为模拟交易,不构成投资建议")
```
- 两通道都渲染成"必经确认"两按钮;**执行只由 `ordok` 触发**(见 §6)。

**成交回执**(force_new=True · 异步推送也复用同一 builder)
```python
ReplyModel(title="合约成交", text="📊 BTCUSDT · 永续 · 逐仓 20x\n开多 0.5 · 成交价 63,200 USDT\n名义 31,600 · 手续费 25.28",
           buttons=((Button("⬅️ 返回菜单","menu:main"),),), force_new=True,
           disclaimer="本次为模拟交易,不构成投资建议")
```

**行情卡**
```python
ReplyModel(title="行情", text="NVDA · 美股\n现价 $145.00  +1.2%\n…", buttons=((Button("📈 看K线(网页)", url="https://midastrade.asia/..."),)))
```
- `url` 按钮:TG → inline url button;飞书 → card link button。

---

## 3. ★ TG 现有代码重构的零回归保证(本 ADR 最关键)

### 3.1 重构动作
- `services/bot/router.py`:`handle_command/handle_callback` → 统一 `handle_inbound(db, redis, ch, msg: InboundMessage) -> ReplyModel`。内部状态机(session 步骤、分支)**逻辑一行不改**,只把"返回 `ui.render_X(...)`(BotReply)"换成"返回 `replies.build_X(...)`(ReplyModel)",身份解析换成 `resolve_user_id(db, msg.channel, msg.channel_uid)`。
- `telegram_ui.py` 拆成两半:
  - `services/bot/replies.py`(通道无关 builder):12 个 `render_*` 的**结构决策**(哪些按钮、什么文案)→ 产出 `ReplyModel`。
  - `services/bot/renderers/telegram.py`(TG 专属):`render_for_telegram(reply: ReplyModel) -> (text, keyboard)`,负责 `*{BRAND} · {title}*` 首行、`_tail` 追加 disclaimer、`buttons → inline_keyboard`(callback_data=action / url=url)。
- `api/v1/telegram.py`:解析 TG update → 构造 `InboundMessage(channel="telegram", channel_uid=str(chat_id), kind, text/action, reply_ctx={message_id})` → `handle_inbound` → `render_for_telegram` → `telegram.send/edit_message_text`(edit-vs-new 逻辑不变)。

### 3.2 零回归策略(可证明)
1. **先立 golden 快照、再重构**:重构前,对每个 `render_*` / 每条交互流(绑定回执、主菜单、市场选择、标的输入、方向选择、**下单二次确认**、成交回执、拒单、行情卡、自选、持仓、告警列表、安静时段、限流、未绑定、错误)**抓现状输出快照**(`BotReply.text` 字符串 + `keyboard` JSON),落进 `tests/services/test_bot_golden.py`。
2. **重构后断言字节级一致**:`render_for_telegram(build_X(...))` 的输出必须与旧 `render_X(...)` 的快照**逐字节相同**(text)+ **结构相同**(keyboard JSON,含每个 callback_data)。任一不一致即视为回归,CI 红。
3. **action 命名空间冻结**:所有 `callback_data` 字符串(action)保持不变 → 历史已发出的 inline 按钮、router 的 `if d == "..."` 分支全部不动 → TG 交互行为不变。
4. **下单二次确认红线不弱化**:确认流程(`order_direction` → `order_confirm` → `ordok` 才 `execute`)是 **router 状态机**逻辑,本次只搬"确认卡的渲染",**状态机一行不改**;补一条显式测试:无 `order_confirm` 会话时 `ordok` 不执行、不能从 `order_symbol`/`order_direction` 跳过确认直达 `execute`。
5. **seam 先行、飞书后行**:阶段一**只做 TG 走 ReplyModel 的重构**(无任何飞书代码),上线 + 真机回归确认 TG 不变后,才进飞书阶段 → 飞书代码物理上无法影响已验证的 TG 路径。
6. **真机回归清单**(阶段一验收):TG 上逐条走 绑定 / `/menu` / `/price` / 选市场→输代码→选方向→**确认→成交回执** / 误输引导 / 自选 / 持仓 / 告警查看·启停·一键推荐 / 安静时段 步进——与重构前对照,输出一致。

> 信心来源:router 状态机 + order/query 内核**逻辑不动**,只换"出站类型 + 身份解析签名";TG renderer 用 golden 测试钉死等价输出;callback_data 冻结保证历史按钮兼容。

---

## 4. 飞书适配器四件套设计

### 4.1 webhook 入站(验签 + challenge)
- 新路由 `POST /api/v1/feishu/webhook`(Caddy `api.midastrade.asia` 是无 path 白名单 catch-all,**不需改 Caddy/域名**;回调地址 = `https://api.midastrade.asia/api/v1/feishu/webhook`)。
- **URL 验证握手**:飞书首次配置发 `{"type":"url_verification","challenge":"..."}` → 原样回 `{"challenge":...}`。
- **事件验签**:用飞书 **Verification Token** 校验 + **Encrypt Key** 解密(若开启加密)· 验签通过才构造 `InboundMessage`。
- 订阅事件:`im.message.receive_v1`(收文本)→ `kind="text"`;`card.action.trigger`(卡片按钮)→ `kind="button", action=<button.value>`。`channel_uid = event.sender.open_id`。

### 4.2 消息卡片渲染
- `services/bot/renderers/feishu.py`:`render_for_feishu(reply: ReplyModel) -> feishu_card_json`。
  - `title` → card header;`text` → markdown 元素;`disclaimer` → 末尾 note 元素;`buttons` → action 模块(每个 Button:回调按钮 `value={"action": action}`,url 按钮 `url=url`)。
  - 原地刷新:`card.action.trigger` 回调可返回新 card 实现"原地编辑"(对等 TG `editMessageText`)。

### 4.3 身份 + 绑定
- `notification_config` 加列 **`feishu_open_id`(String 可空 · partial unique)** + 一次**可空加列迁移**(无数据风险,可逆)。
- `resolve_user_id` 泛化:`resolve_user_id(db, channel, channel_uid) -> UUID | None`,内部按 channel 查对应列(`tg_chat_id` / `feishu_open_id`)。旧 TG 调用点改成传 `channel="telegram"`(等价)。
- 绑定复用 bind-token:`POST /{channel}/bind-token`(Redis 机制通道无关,只是绑定成功时写的列不同);飞书侧在事件里带 token 完成绑定,「一人一通道一账号」校验对称。

### 4.4 飞书 token 管理(与 TG 的关键差异)
- 飞书 API 调用需 `tenant_access_token`(App ID/Secret 换取,TTL ~2h)。新增 `services/notifications/feishu_client.py`:**Redis 缓存 token + 提前刷新**(过期前重取),发卡/回卡复用。TG 是直接用 bot token,飞书多这一层。

### 4.5 下单二次确认(飞书卡片 · 红线对称)
- 下单流程在飞书走:选市场 → 输标的 → 选方向 →(router 进 `order_confirm` 会话)→ 渲染**确认卡**(✅ 确认 / ✖️ 取消两按钮,action=`ordok`/`ordno`)→ 点"✅ 确认"发 `card.action.trigger(action=ordok)` → router `_handle_confirm` → `execute`。
- **执行只由 `ordok` 触发**,与 TG 同一 router 分支;飞书侧无法绕过(无 `order_confirm` 会话则忽略)。确认是**所有通道共享的 router 状态机**,新通道天然继承。

---

## 5. 分阶段交付(大任务拆小步 · 每步单独验收 + 合 main)

| 阶段 | 范围 | 风险 | 验收点 | 分支 |
|---|---|---|---|---|
| **一 · 抽象地基(纯重构 · 无新功能)** | ReplyModel + InboundMessage;router→`handle_inbound`返 ReplyModel;telegram_ui 拆 `replies.py`+`renderers/telegram.py`;`resolve_user_id` 泛化(channel 参数,TG 传 "telegram");webhook 改用归一入站/出站 | 中(碰已上线 TG 交互全链路) | **TG 字节级零回归**:golden 测试全过 + 真机逐条回归(§3.6)+ 下单二次确认必经测试 | feat/ch0-reply-abstraction |
| **二 · 飞书通知推送** | `adapters/feishu.py`(send_event/send_test)+ `feishu_client.py`(token 缓存)+ `notification_config.feishu_open_id` 迁移 + dispatcher 多通道分发(按用户绑定的通道集合) | 中(碰 dispatcher · 加列迁移可空可逆) | 飞书收到 成交/强平/价格异动 推送;TG 推送零回归;迁移 up/down/up 过 | feat/ch1-feishu-notify |
| **三 · 飞书交互:绑定 + 行情/查询** | `api/v1/feishu.py`(webhook 验签+challenge)+ `renderers/feishu.py` 卡片 + 绑定流程 + 行情/自选/持仓只读 | 中-大(新通道传输+渲染) | 飞书绑定成功;查行情/自选/持仓 对等 TG;身份隔离测试(open_id 只从已验签事件取) | feat/ch2-feishu-bot-readonly |
| **四 · 飞书下单 + 二次确认 + 告警配置** | 下单流程(选市场→标的→方向→**二次确认卡**→成交回执)+ 告警规则查看/启停/一键推荐 + 安静时段 | 大(碰下单交互 · 红线) | 飞书下单二次确认必经;告警/安静时段 对等 TG;红线三条飞书侧验证 | feat/ch3-feishu-trade |
| (五 · 未来)钉钉 | 加 `renderers/dingtalk.py` + `adapters/dingtalk.py` + `api/v1/dingtalk.py` + `dingtalk_uid` 列 | 中 | 复用全部内核 + ReplyModel,只补适配器 | — |

每阶段 feature 分支、审过 + 验收过再合 main。阶段一不上线前不碰飞书;阶段二/三/四各自独立可回滚。

---

## 6. 红线确认(多通道下同等守住)

| 红线 | 多通道实现 |
|---|---|
| **虚拟资金 · 永不接真实交易** | 撮合内核(`engine`/`perp_engine`/`order.execute`)通道无关、本任务一行不碰 · 任何通道下单都走同一虚拟撮合 |
| **身份只从已验签事件的 channel_uid 取(不从消息文本)** | `InboundMessage.channel_uid` **只在各通道 webhook 验签通过后构造**(TG secret 头 / 飞书 Verification Token);`resolve_user_id(channel, channel_uid)` 是唯一鉴权入口;业务层(router/order/query)永不从 `text` 取身份 · 与 0025 R1 等价 |
| **下单二次确认必经** | 确认是 **router 状态机**(`order_confirm`→`ordok`),通道无关、所有通道共享;`execute` 只由 `ordok` 动作触发,任何通道都无法跳过(无 `order_confirm` 会话则忽略);阶段四补飞书侧"必经确认"测试 |
| 文案免责 | ReplyModel.disclaimer 字段,每通道 renderer 追加(交易类/告警类分层),不漏 |

---

## 7. 决策小结
- ReplyModel + InboundMessage 是地基:业务内核只跟中立模型打交道,通道 = 传输+验签+渲染+身份+token 五件套。
- TG 零回归靠"逻辑不动 + golden 测试钉死 TG renderer 等价 + callback_data 冻结 + seam 先行"。
- 飞书与 TG 的真正差异:**access_token 管理** + **卡片(非 inline_keyboard)** + **验签机制(Verification Token/Encrypt Key + URL challenge)**。
- 钉钉将来 = 再加一套适配器/renderer,内核与 ReplyModel 不动。
- 红线三条在中立层物理对称守住。

> 待审重点:§2 ReplyModel 是否够表达两通道 · §3 TG 零回归是否可信 · §5 阶段拆分是否合理 · §6 红线是否对称。审过 + 产品拍板后按阶段开工。
