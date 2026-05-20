# 点金 Midas · 推送测试自测指南

> M0 收口验证 · 配齐真实凭证后跑一遍验证飞书 / TG 推送链路。

后端 mock 测试已 31 个全过(20 路由 + 11 dispatch / emit)· 这份指南覆盖**真实凭证下的最后一公里 E2E**。

---

## 前置条件

- 全栈已 `docker compose up -d`,API + worker + web 全部 healthy
- 测试账号 `hans@test.com` / `Test123456` 已可登录(README 第 7 步造)
- 浏览器登录该账号 → 进入 `/settings`

---

## 一、配置飞书机器人(~3 分钟)

### 1. 在飞书群拉机器人

任意飞书群 → 设置(齿轮) → 群机器人 → 添加机器人 → 选「自定义机器人」

填:
- 机器人名字:`点金 Midas`(随意)
- 描述:`成交通知 + 价格异动`(随意)
- 头像:点金红色 / 黄色一类(随意)

### 2. **关键:打开安全设置 → 自定义关键词**

输入关键词:**`点金`**(两个字,半角无空格)

**为什么:** 我们的所有消息模板天然带「点金 Midas」字样,所以这个关键词总能匹配到。如果不配关键词,飞书会拒收消息。其他两种安全模式(签名 / IP 白名单)M0 不支持。

### 3. 复制 Webhook URL

样子:`https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx`

### 4. 填入 `/settings`

- 浏览器进 `http://localhost:3000/settings`
- 找到「飞书机器人」卡 → Webhook URL 输入框 → 粘贴
- 点 **保存飞书配置** 按钮
- 应该看到帝王金 toast:`飞书配置已保存`

### 5. 点「发送测试」

- 同一张卡的「发送测试」按钮
- **应该立即收到飞书群消息:**

  ```
  ┌─────────────────────────┐
  │ 点金 Midas · 测试消息    │
  │ ─────────────────────── │
  │ ✓ 飞书机器人配置成功     │
  │                         │
  │ 之后你的成交通知和价格异 │
  │ 动会推到这里。           │
  │ ─────────────────────── │
  │ 本次为模拟交易,不构成   │
  │ 投资建议                 │
  └─────────────────────────┘
  ```
- 同时浏览器顶部应弹帝王金 toast:`飞书测试消息已发送`

**如果失败:** 浏览器会弹中国红 toast,显示具体 `reject_reason`。常见:
- `Key Words Not Found` → 关键词没填或填错(必须是「点金」)
- `Network Error` → webhook URL 拼错了
- `19003` → 机器人已删除 / 不存在

---

## 二、配置 Telegram bot(~5 分钟,需要爬墙)

### 1. 申请 bot token

Telegram 里搜 [@BotFather](https://t.me/BotFather) → 发 `/newbot` → 跟着提示填:
- 机器人显示名:`Midas Notify`(随意)
- 机器人 username:`midas_notify_yourname_bot`(必须 `_bot` 结尾,全局唯一)

BotFather 会返一段:

```
Done! Congratulations on your new bot. You will find it at t.me/xxx_bot.
Use this token to access the HTTP API:
123456789:ABCdefGHIjklMNOpqrSTUvwxYZ012345678
```

记下 token(冒号前后那串)。

### 2. 拿 chat_id

最简单方法:

1. 把 bot 加进任意群 / 创建新群拉它进来
2. 群里随便发一条消息(让 bot 看到)
3. 浏览器访问 `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. 找到 `"chat":{"id":-100xxxxxxx,...}` 里的数字(群 chat_id 通常带 `-100` 前缀)

或者私聊 bot 用同样方法。私聊 chat_id 是正数。

### 3. 填入 `/settings`

- 「Telegram bot」卡 → Bot Token 输入框 → 粘贴 token
- Chat ID 输入框 → 粘贴 chat_id
- 点 **保存 Telegram 配置** → 帝王金 toast `Telegram 配置已保存`

### 4. 点「发送测试」

- 应该立即收到 TG 消息:

  ```
  *点金 Midas · 测试消息*

  ✓ Telegram bot 配置成功

  之后你的成交通知和价格异动会推到这里。

  _本次为模拟交易,不构成投资建议_
  ```

**如果失败:** 中国红 toast 显示原因:
- `Unauthorized` → token 错了
- `chat not found` → chat_id 错了 / bot 没在该群里
- `network error` → 国内直连 TG 不通,需要给 worker 容器配代理(0009 § 9 已知边界)

---

## 三、E2E 验证 · 真实成交通知(~2 分钟)

前提:至少配通一个通道(飞书 / TG 任一)。

### 1. 激活美股账户(如未激活)

`/account` → 美股卡 → 填 `100000` → 激活并保存

### 2. 下单

`/workbench` → 顶 Tab 切到「美股」(symbol 默认 NVDA)→ 点顶部「买入」按钮 → confirm 模态弹出 → 确认买入

预期:
- 浏览器顶部弹帝王金 toast `买入 1 NVDA 已成交`
- 飞书 / TG **几秒内**收到成交通知:

  ```
  点金 Midas · 成交通知
  ────────────────────
  NVDA · 美股
  买入 1 · 成交价 $6.5576
  手续费 $0.0000
  ────────────────────
  本次为模拟交易,不构成投资建议
  ```

如果浏览器看到 toast 但飞书 / TG 没收到,说明 emit 走 broker 没问题但 worker 端 dispatch 出错。查 worker log:

```bash
docker compose -f docker/docker-compose.yaml logs worker --tail=50 | grep notify
```

### 3. 卖出测试

`/workbench` → 顶部「卖出」 → confirm 模态:数量保持 1 → 确认卖出

预期飞书 / TG 收到:

```
点金 Midas · 成交通知
────────────────────
NVDA · 美股
卖出 1 · 成交价 $6.5557
手续费 $0.0000
已实现盈亏 · $-0.0019
────────────────────
本次为模拟交易,不构成投资建议
```

---

## 四、E2E 验证 · 价格异动通知(~5 分钟,触发不可预测)

价格异动是 Celery beat 任务驱动,每分钟扫一次自选股的最近 2 根日 K。**只有真涨跌 ±5%** 才会触发。

### 触发条件(产品负责人决策)

- 自选股里有标的(默认登录后 lazy fill 3 个 demo)
- 最近 2 个交易日 close 跨度 ≥ 5%

### 等候 / 验证方式

- **被动等真异动:** 看 BTC/USDT(波动大),24h 内通常有几次能凑到 5% · `/workbench` 切加密 Tab 看现价跟昨日比
- **主动 mock:** 写一段 SQL 在 ClickHouse 改 K 线值让 pct = 5.5%,等下一分钟 beat 扫到触发(技术复杂,M0 不展开)

### 收到的消息形态

飞书:

```
点金 Midas · 价格异动 (red 或 green header)
────────────────────────────
BTC/USDT · 加密
异动 ↑ +6.32%
现价 105,432.10 USDT · 参考价 99,200.00 USDT
────────────────────────────
本次为模拟交易,不构成投资建议
```

TG:

```
*点金 Midas · 价格异动*

🔴 BTC/USDT · 加密
异动 ↑ +6.32%
现价 105,432.10 USDT · 参考 99,200.00 USDT

_本次为模拟交易,不构成投资建议_
```

**去重保护:** 同标的 5 分钟内不会重复推(0009 § 4)· 想再测得等 5 分钟。

---

## 五、关闭单个通道 / 关闭单个事件类型

`/settings` → 「事件总开关」卡:

- 取消勾「成交通知」 → 保存开关 → 之后下单不会推
- 取消勾「价格异动通知」 → 之后异动不会推
- 想完全停推但保留配置(临时静默):两个都关
- 想换通道:把不要的通道字段清空 → 保存

---

## 六、排查日志位置

| 现象 | 看哪儿 |
|---|---|
| 浏览器没 toast | api 容器日志 `docker compose logs api --tail=50` |
| toast 显示成功但通道没收到 | worker 容器日志 `docker compose logs worker \| grep notify` |
| broker 不通 emit 失败 | api 日志会显示 `[emit] trade filled FAILED order_id=... err=...` |
| 价格异动 worker 没扫 | `docker compose logs worker \| grep price_alerts` 看 beat 触发 |

---

## 七、已知不支持(M0 范围)

- 推送失败 UI 没消息(后端仅 log)· M1 加站内通知中心
- 没自定义模板 / 频率限制 / 静默时段 · M1
- 拒单不会推(产品决策,只推 filled)· M1 用户可选

---

## 八、配置后的对接

完成上面 E2E 验证 = M0 推送链路真实跑通。

剩下的:
- **数据精度审计**(NVDA $6.56 vs 实时 $140)· M1 优先
- **生产部署 + Resend API Key + 真域名 + Google OAuth** · Task 7.1

---

**指南完。**
