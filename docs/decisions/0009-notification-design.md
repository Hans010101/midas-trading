# 0009 · 推送通知(Notifications)设计

## 状态
Approved (2026-05-20)

## 上下文

Task 6(M0 验收链路第 4 步:陌生人能收飞书 / TG 推送)启动。

**产品负责人已拍板:**

1. **事件:**
   - 成交通知(推 · 异步)
   - 拒单(**不推**,UI 当场有 toast 即可)
   - 自选股价格异动 ±5%(推 · 5 分钟同标的去重)
2. **通道:** 用户在设置页自己配。填飞书 webhook → 推飞书 · 填 TG token+chat_id → 推 TG · 两边都填 → 都推 · 都不填 → 只有站内 toast。**不强制,不默认**
3. **M0 范围:** 成交通知 + 价格异动 + 每通道「发送测试消息」按钮
4. **M0 不做:** 自定义模板 / 频率设置 / 静默时段(defer M1)

**关键铁律(产品负责人复述):**
- 推送 emit **必须异步**,绝不阻塞下单主链路 · 下单要快,推送可以慢
- 成交通知用**帝王金**,**绝不绿色**(避涨跌色冲突)
- 价格异动里行情涨/跌可用朱红 / 墨绿(这里是「行情色」,允许)
- AI / 交易输出必带「仅供参考,不构成投资建议」

## 决策

### 1. 用户配置存储 · 独立 `notification_config` 表(per user lazy create)

```python
# apps/api/app/models/notification.py

class NotificationConfig(Base):
    """每用户一行 · lazy create(用户首次保存配置时 INSERT)。

    跟 0008 v2 VirtualAccount 同模式(lazy create)· 不存在 = 未配置任何通道。
    """
    __tablename__ = "notification_config"

    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,  # 一对一 · user_id 既 PK 又 FK
    )

    # 飞书自定义机器人 · webhook URL
    # 注意:URL 本身是 secret(知道就能推)· M0 明文存,M1 加密
    feishu_webhook_url: Mapped[str | None] = mapped_column(String(512))

    # TG bot
    tg_bot_token: Mapped[str | None] = mapped_column(String(128))
    tg_chat_id: Mapped[str | None] = mapped_column(String(64))

    # 总开关(用户可以保留配置但暂停推送)
    trade_alert_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
    )
    price_alert_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
    )

    created_at, updated_at  # tz-aware UTC,标配
```

**为什么独立表(方案 A)而非塞 user 表:**

| 维度 | 方案 A · 独立表 | 方案 B · user 表加列 |
|---|---|---|
| 「该用户配过通知吗」 | `EXISTS(SELECT 1 FROM notification_config WHERE user_id=?)` | `WHERE feishu_url IS NOT NULL OR tg_token IS NOT NULL` |
| 加密准备(M1 升级)| 单独表加密,user 表不动 | 改 user 表(高敏感字段混进认证表)|
| 单一职责 | auth 表只管 auth | user 表越来越胖(已有 demo_prefilled / age_confirmed)|
| 跟现有模式一致 | 跟 VirtualAccount lazy create 一致 | 不一致 |
| 「查询简单」 | 都是 WHERE user_id=? 一行,无差 | 同 |

**选 A** · 数据库语义自然 + 加密升级路径干净。

### 2. 通道客户端

#### 2.1 飞书自定义机器人

**安全模式 · 自定义关键词 = `点金`**

理由:
- 三种安全模式中,「关键词」最简单(无 signing / IP 白名单配置)
- 我们的消息模板必带「点金 Midas」字样,**天然满足关键词校验**
- 用户在飞书机器人配置时,加关键词 `点金` 即可

**消息格式 · interactive card(JSON):**

```json
{
  "msg_type": "interactive",
  "card": {
    "header": {
      "title": { "tag": "plain_text", "content": "点金 Midas · 成交通知" },
      "template": "wathet"
    },
    "elements": [
      { "tag": "div", "text": { "tag": "lark_md", "content": "**NVDA · 美股**\n买入 10 股 · 成交价 $140.04" }},
      { "tag": "hr" },
      { "tag": "note", "elements": [{"tag": "plain_text", "content": "本次为模拟交易,不构成投资建议"}] }
    ]
  }
}
```

POST URL = `feishu_webhook_url` · `Content-Type: application/json`

成功:HTTP 200 + `{"StatusCode": 0, "StatusMessage": "success"}`

#### 2.2 Telegram bot

**协议:** Bot API `https://api.telegram.org/bot{token}/sendMessage`

**Payload:**
```json
{
  "chat_id": "...",
  "text": "*点金 Midas · 成交通知*\n\n📊 NVDA · 美股\n买入 10 股 · 成交价 $140.04\n\n_本次为模拟交易,不构成投资建议_",
  "parse_mode": "Markdown"
}
```

成功:HTTP 200 + `{"ok": true, ...}`

#### 2.3 Dispatcher

```python
# apps/api/app/services/notifications/dispatcher.py

async def dispatch(user_id: UUID, event: NotificationEvent) -> DispatchResult:
    """根据用户 config 派发到 0~2 个通道,各通道失败独立。"""
    config = await get_config(db, user_id)
    if not config:
        return DispatchResult(channels=[], errors=[])

    # 总开关 + 事件类型过滤
    if isinstance(event, TradeFilledEvent) and not config.trade_alert_enabled:
        return ...
    if isinstance(event, PriceAnomalyEvent) and not config.price_alert_enabled:
        return ...

    sent = []
    errors = []

    if config.feishu_webhook_url:
        try:
            await feishu_client.send(config.feishu_webhook_url, event)
            sent.append("feishu")
        except Exception as e:
            errors.append(("feishu", str(e)))

    if config.tg_bot_token and config.tg_chat_id:
        try:
            await tg_client.send(config.tg_bot_token, config.tg_chat_id, event)
            sent.append("telegram")
        except Exception as e:
            errors.append(("telegram", str(e)))

    return DispatchResult(channels=sent, errors=errors)
```

### 3. 事件系统 · 异步 emit · 绝不阻塞下单

**engine.py 修改:**

```python
async def _record_filled(...) -> VirtualOrder:
    order = VirtualOrder(...)
    db.add(order)
    await db.flush()

    # ★ 异步 emit · 用 Celery delay 丢任务 · 不 await
    from app.services.notifications.events import emit_trade_filled
    emit_trade_filled(order)  # 内部用 Celery delay,不阻塞

    return order
```

**emit_trade_filled 实现:**

```python
def emit_trade_filled(order: VirtualOrder) -> None:
    """非阻塞 emit · 丢 Celery task · 失败不影响下单主链路。"""
    try:
        from celery_app import app as celery_app
        celery_app.send_task(
            "tasks.notifications.send_trade_notification",
            args=[order.id],
        )
    except Exception as e:
        # broker 挂了不算异常情况 · log + continue
        logger.warning("emit trade event failed (broker down?): %s", e)
```

**Celery task 内部:**

```python
@shared_task(name="tasks.notifications.send_trade_notification", bind=True, max_retries=3)
def send_trade_notification(self, order_id: int):
    # 1. 查 order + account
    # 2. 拿 user_id
    # 3. 渲染 TradeFilledEvent
    # 4. dispatch(user_id, event)
    # 5. 失败 → self.retry(exc=e, countdown=2 ** self.request.retries)
    asyncio.run(_send_trade_notification_async(order_id))
```

**关键:**
- `send_task` 走 Redis broker · 网络 IO ~5ms · 不算阻塞
- broker 失败 → log + 主链路继续 · 用户已收 200 filled

### 4. 价格异动检测 · Celery beat 每 1 分钟

```python
# apps/worker/tasks/price_alerts.py

PRICE_ALERT_THRESHOLD = Decimal("0.05")  # ±5%
DEDUP_TTL_SECONDS = 300  # 5 分钟同标的去重

@shared_task(name="tasks.price_alerts.scan_price_anomalies")
def scan_price_anomalies():
    """每 1 分钟扫一次所有用户自选股 · 涨跌 ±5% 触发推送。"""
    asyncio.run(_scan_price_anomalies_async())


async def _scan_price_anomalies_async() -> int:
    # 1. 取所有 WatchlistItem(JOIN user 拿 user_id)
    # 2. group by (symbol, market) · 每标的算一次 pct
    #    · 用日 K close 跟前一日 close 比(0008 § "已知边界" · M0 接受 1 min 延迟)
    # 3. 触发条件:|pct| >= 5%
    # 4. 对每个 user-symbol-market 三元组 · 检查 Redis dedup:
    #    key: f"price_alert:{user_id}:{market}:{symbol}"
    #    存在 → skip · 不存在 → 推 + SET key with TTL=300
    # 5. dispatch 同 trade 路径
    return triggered_count
```

**Redis 去重 key 设计:**
- 跨用户同标的:**不共用 key**(每个用户独立去重 · 因为偏好/阈值未来可能不同)
- 当用户清掉自选股,该 key 24h 后自动过期

**Beat schedule(celery_config.py):**
```python
"scan-price-anomalies": {
    "task": "tasks.price_alerts.scan_price_anomalies",
    "schedule": crontab(minute="*"),  # 每分钟
},
```

### 5. 消息模板规范

| 字段 | 飞书 | TG |
|---|---|---|
| 标题 | interactive card header `点金 Midas · 成交通知` | Markdown `*点金 Midas · 成交通知*` |
| 关键词触发 | "点金"(标题里)| N/A |
| 标的展示 | `**NVDA · 美股**` lark_md | `📊 NVDA · 美股` |
| 数据行 | `买入 10 股 · 成交价 $140.04` | 同 |
| 涨/跌色(价格异动)| 飞书 card template = `red` 涨 / `green` 跌 | TG 用 emoji 🔴 涨 / 🟢 跌(M0 不依赖颜色) |
| 尾部免责 | `note` element `本次为模拟交易,不构成投资建议` | `_本次为模拟交易,不构成投资建议_` |
| 成交色 | header.template = `wathet`(青色 · 帝王金不在飞书 card preset 里,wathet 是最克制的色)| 无色 |

**关于"绝不绿色":**
- 成交通知:**飞书用 wathet(青色)而非 green**;TG 无色
- 价格异动 ↓ 跌:这里是行情色,**允许墨绿/green**(产品负责人特许)
- 价格异动 ↑ 涨:朱红/red

### 6. REST 路由

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/notifications/config` | 当前用户配置(404 if 未配置过 · 返回默认对象)|
| PUT | `/api/v1/notifications/config` | 保存配置(部分更新 · 不传字段保持原值)|
| POST | `/api/v1/notifications/test?channel=feishu\|telegram` | 发送测试消息(用当前已保存的配置)|

**Token 展示:** `tg_bot_token` 在 GET 响应只返前 10 + 后 4 字符(`123456789:AB...CDEF`)· 全文不出后端

### 7. M0 不实装(确认 defer)

| 功能 | Defer 到 |
|---|---|
| 自定义模板 · 用户改文案 | M2 |
| 频率设置(每小时最多 N 条)| M1 · 加 user-level rate limit |
| 静默时段(23:00-08:00 不推)| M1 |
| 拒单也推 | M1 · 用户可勾选 |
| 微信公众号 / 邮件作为通知通道 | M2(邮件已有 Resend,但用于交易通知 = "spam风险",慎重)|
| 站内通知中心(/notifications)| M2(M0 toast 即时反馈即可)|
| Token 加密存储 | M1 · `cryptography.Fernet` · key in env |

### 8. 安全 + 已知边界(M0 接受)

- `tg_bot_token` / `feishu_webhook_url` **明文存**(M0)· secret 暴露限于 DB 凭证泄露的极端场景
- 推送失败仅记 log · 不前端展示("未送达"通知会引发用户焦虑,M0 简化)
- 同标的多用户 = N 次 webhook 调用(无聚合)· N 用户 × 自选股 × 通道 = 1 分钟内最坏 100+ 调用 · 飞书限频 ~100 次/分钟,够用
- 价格异动用日 K close 比较 · **真实 5% 触点可能延迟到下一日**(0008 同款限制 · M0 接受)
- Dispatcher 顺序调通道(非并发)· 单用户两通道 ~1-1.5s · 不影响主链路

### 9. 测试策略(无真实凭证下)

| 测试类型 | 方法 |
|---|---|
| 飞书 client 单元 | `httpx.MockTransport` mock 200 / 400 / network error |
| TG client 单元 | 同上 |
| Dispatcher 路由 | mock client · 验证按 config 选通道 + 失败独立 |
| GET/PUT /config 路由 | pytest TestClient · auth + 部分更新语义 |
| POST /test 路由 | mock httpx · 验证 payload 含「点金 Midas」 |
| 价格异动 worker | mock CH + mock Redis · 验证去重 + 阈值 |
| Engine emit | mock celery_app.send_task · 验证 broker down 不阻塞 |

**真实推送测试:** 留给产品负责人回来配真凭证后做。汇报里**明确标注**「Mock 验证」vs「等真凭证才能测」。

## Checkpoint 切分 · S / T / U

### Checkpoint S · 通知后端 · config + clients + dispatcher + REST

| Sub | 范围 | 估时 |
|---|---|---|
| S1 | notification_config model + alembic migration | 30 min |
| S2 | services/notifications/{feishu,telegram}.py clients · httpx + 模板渲染 | 1.5h |
| S3 | services/notifications/dispatcher.py · per-channel 失败独立 | 1h |
| S4 | services/notifications/events.py · TradeFilledEvent / PriceAnomalyEvent dataclass | 30 min |
| S5 | REST 3 路由 · GET/PUT /config + POST /test · token 展示截断 | 1h |
| S6 | pytest mock httpx · clients + dispatcher + 路由(7-10 case)| 1h |
| S7 | tag `checkpoint-s` | 15 min |
| **小计** | | **~5.75h** |

### Checkpoint T · 事件系统 + 价格异动 worker

| Sub | 范围 | 估时 |
|---|---|---|
| T1 | apps/worker/tasks/notifications.py · send_trade_notification Celery task | 1h |
| T2 | engine.py · _record_filled 末尾异步 emit(emit_trade_filled helper)| 30 min |
| T3 | apps/worker/tasks/price_alerts.py · scan_price_anomalies + Redis 去重 | 1.5h |
| T4 | celery beat schedule 加 scan-price-anomalies(每 1min)| 15 min |
| T5 | pytest · trade emit · price anomaly · dedup · broker down 不阻塞 | 1.5h |
| T6 | smoke test:mock 凭证 + 下单 → 看 Celery log 验证 task 被 dispatch | 45 min |
| T7 | tag `checkpoint-t` | 15 min |
| **小计** | | **~5.75h** |

### Checkpoint U · 通知前端 · 设置页推送配置

| Sub | 范围 | 估时 |
|---|---|---|
| U1 | lib/api/notifications.ts + hooks · useNotificationConfig / useSaveConfig / useSendTest | 1h |
| U2 | NotificationsConfigSection 替换 placeholder · 实装 Feishu + TG 配置卡 | 2h |
| U3 | 测试按钮 · 帝王金 toast 成功 / 中国红 toast 失败 | 45 min |
| U4 | playwright 截图(2 张):设置页 + 测试发送 toast | 45 min |
| U5 | E2E · 注册新用户 → 进 /settings → 填假 webhook → 点测试 → toast 失败 | 30 min |
| U6 | tag `checkpoint-u` + 总汇报 | 30 min |
| **小计** | | **~5.5h** |

**P+Q+R+S+T+U 合计推送实装 ~17h**(略高于估的 15h,因为 Mock 测试要写到位)

## 撤销路径

| 改动 | 撤销路径 |
|---|---|
| **加密 token / webhook(M1)** | `cryptography.Fernet(key=os.environ["NOTIF_ENC_KEY"])` · GET 时 decrypt · PUT 时 encrypt · 加 migration ALTER COLUMN 不动 schema |
| **自定义模板(M2)** | 加 `notification_template` 表(per-user 文案)· dispatcher 渲染时优先用 |
| **支持邮件通道** | NotificationConfig 加 email_alert_enabled · Resend client 已有 · dispatcher 加一路 |
| **WebSocket 实时推送** | 一旦 Task 4-B 实装,价格异动从 worker 扫改成 ws 推 |
| **微信** | 加 webhook 字段 + WeChatClient · 但 limit 比飞书更严 · 可能 M2 |

## 备注

- Task 7.1 上线时的「商务邮件」(注册成功 / 重要更新)不走通知模块,继续走 N4 的 EmailService(Resend)· 两个职能分开:邮件 = 关键事件 / 推送 = 行情决策
- 推送内容里禁用「建议 / 必涨 / 必跌」这类绝对表述 · 用「触发」/「±X%」客观描述
- M0 测试用户(hans@test.com)不会自动配置任何通道 · 用户需手动去 /settings 设
