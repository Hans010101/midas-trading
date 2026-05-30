# 飞书体验打磨调研 · 扫码绑定 + 常驻菜单

- 类型:**调研结论**(非 ADR · 供产品负责人决定做不做;若决定做再升级为正式任务/ADR)
- 日期:2026-05-30
- 背景:飞书工程(ADR 0032)收官后的体验打磨。同批「绑定码一键复制按钮」已实现
  (`feat/feishu-polish`),本文只覆盖两个**需调研、暂不实现**的点。
- 关联:ADR 0032(多通道 Bot + 飞书接入)、0024(TG 统一 bot · `/start <token>` 绑定基线)

---

## 一、扫码 / 深链绑定(对标 TG 的 `/start <token>`)

### 结论
- ❌ **飞书无法完整复刻 TG「带 token 深链一键自动绑定」** —— 飞书深链不支持携带自定义参数。
- ✅ 可做「**一键打开机器人会话**」(半自动:进会话仍需手动粘贴 token)。

### 关键事实(飞书开放平台官方文档)
- 飞书 AppLink「打开机器人会话」:`https://applink.feishu.cn/client/bot/open?appId=cli_xxx`
  - **只支持 `appId` 一个参数,不支持携带自定义参数(绑定 token 无处可放)**
  - 最低客户端 **3.40.0**;只把用户带进与机器人的会话窗口,**不会自动发消息**
- 对比 TG:`t.me/<bot>?start=<token>` → 打开会话**并自动发送** `/start <token>` → 后端
  从已验签 update 拿 token 自动绑定。**飞书没有等价机制**(applink 是「跳转打开」,
  不是「跳转 + 带参执行」)。

### 可行方案对比(可行性 + 工作量)

| 方案 | 做法 | 体验 | 工作量 | 评价 |
|---|---|---|---|---|
| **A 现状(已优化)** | 复制 token(本批已做)+ 文字引导手动打开应用 | 复制 → 切飞书 → 粘贴 → 发送 | 0(已完成) | 够用 |
| **B 一键打开会话** ⭐ | 加「在飞书中打开」按钮 = `applink…/bot/open?appId=<FEISHU_APP_ID>`,配合已做的复制按钮 | 复制 → 点按钮直达会话 → 粘贴 → 发送 | 前端 ~0.5h(加 `<a>` + 前端拿到 appId) | 省「找应用」一步;token 仍手动 |
| **C 二维码** | applink 编码成 QR,飞书「扫一扫」 | 扫码 → 进会话 → 粘贴 | 前端 ~0.5h(复用 `qrcode.react`) | applink 二维码能否被飞书扫一扫识别需**真机验**;token 仍手动 |
| **D 全自动深链** | —— | 一键全自动 | **不可行** | 飞书 applink 不支持带参,做不到 |

### 推荐
**B(一键打开会话按钮)** —— 低成本、明显改善,与已做的复制按钮组成「复制 token → 一键进
会话 → 粘贴」闭环。需要前端拿到 `appId`(后端在某个 public config 端点暴露 `FEISHU_APP_ID`,
或前端配 `NEXT_PUBLIC_FEISHU_APP_ID`)。**`appId` 是 public 标识(非密钥),可暴露前端;
`app_secret` 绝不出后端。** token 自动化飞书做不到,接受半自动。

### 待产品负责人定
做 B(一键打开会话)还是保持 A 现状?(C 二维码价值不大,因 token 仍需手动粘贴)

---

## 二、飞书机器人常驻菜单(会话左下角自定义菜单)

### 结论
✅ **可做**,且大部分是**飞书后台纯配置**;代码侧只需在现有 webhook 加一个事件分支
(架构几乎白送 —— 复用现成 `handle_inbound`)。

### 关键事实(飞书开放平台官方文档)
- **配置位置:开发者后台(非 API)** → 应用 → 添加应用能力「机器人」→「机器人自定义菜单」
  → 开启 + 配置;发布后等 ~5 分钟生效。
- 菜单项 3 种响应动作:
  1. **跳转指定链接**(桌面 / 移动端各配 URL,或 applink)
  2. **发送文字消息**(菜单文案作为消息发出 · 飞书 V7.22+)
  3. **推送事件**(配一个自定义 `event_key`,点击 → 推事件到我们 webhook)← 我们要用这个
- 推送事件的事件类型:**`application.bot.menu_v6`**(区别于消息事件 `im.message.receive_v1`)
  - 事件体:`event.event_key`(后台配的菜单项 id)+
    `event.operator.operator_id.open_id`(谁点的)

### 怎么接我们的 `handle_inbound`(现成架构白送)
1. **产品负责人在飞书后台**配菜单项(如「📊 行情」「💼 持仓」「🛒 下单」「🔔 告警」),
   每项选「推送事件」+ 设 `event_key` —— **直接复用我们现有 action 命名**(`menu:quote` /
   `menu:order` / `act:positions` / `menu:rules`)。
2. **后端** `api/v1/feishu.py` webhook 加一个 `application.bot.menu_v6` 分支:
   从 `event.operator.operator_id.open_id` 取身份(★ **仍是已验签事件取 open_id,身份红线不破**)
   + `event.event_key` 当 action → 构造
   `InboundMessage(channel="feishu", kind="button", action=event_key)` → 复用 `handle_inbound`
   → `render_for_feishu` → 发卡。
3. 若 `event_key` 直接用现有 action 名,**核心层零改动** —— 菜单点击 ≡ 点了对应按钮。

### 工作量
- 后端:webhook 加 1 个事件分支(~20 行)+ 1~2 个测试(伪造菜单事件 → 走 handle_inbound)· **~1.5h**
- 飞书后台:产品负责人配菜单项(无代码)· ~10min(需飞书企业开发者 / 管理员权限)

### 红线确认(若实施)
- **身份**:open_id 只从已验签事件取(`operator.operator_id.open_id`)· 与现有注入点同理,不破红线。
- **下单二次确认**:菜单 event_key 若指向 `menu:order`,只是进入下单流程第一步;
  `execute` gate 不变(仍只由 `order_confirm` 态的 `ordok` 触发)。

### 待产品负责人定
① 做不做;② 菜单放哪几项(建议复用主菜单:行情 / 持仓 / 下单 / 告警);
③ 后台配置由谁做(需飞书开发者 / 管理员权限)。

---

## 资料来源
- 打开机器人会话(AppLink):open.feishu.cn/document/common-capabilities/applink-protocol/supported-protocol/open-a-bot
- 机器人自定义菜单使用指南:open.feishu.cn/document/client-docs/bot-v3/bot-customized-menu
- 菜单事件类型 `application.bot.menu_v6`:open.feishu.cn 事件订阅文档
