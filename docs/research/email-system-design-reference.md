# 点金 Midas · 邮件系统 · 可移植设计参考

> 面向:**要在新系统里实现同类邮件能力的开发者**。
> 写法:重点讲**设计思路 + 架构决策 + 为什么这么设计 + 踩过的坑**,不是罗列点金代码。
> 方法:7 镜头只读调研(架构 / 分类触发 / 内容生产 / 可靠性 / 合规送达 / 配置开关 / 踩坑)。
> 与同批的《TG 通知系统设计参考》是姊妹篇 —— 那篇讲 IM 即时推送,这篇讲邮件;两套系统在点金里**刻意分家**(见 §1)。

---

## 0. 一句话总纲

**邮件 = 一个刻意做薄的传输层 + 各业务线自持模板 + 与 IM 通知分家。** 核心发送层只有一个文件、三个函数,用 httpx 裸调 Resend HTTP API;可靠性/收件人/多渠道协调这些决策全部上提到业务层,传输层永远只回答一句话:「把这封 HTML 发到这个地址」。

贯穿始终的三条哲学:
1. **传输层薄、策略上抛** —— 底层只做「能发就发,发不了就抛 typed exception」,重试/隔离/降级由调用方按业务重要性各自决定。
2. **事务邮件 vs 群发邮件二分** —— 两类走**完全不同的失败契约**(事务失败不阻塞主流程 + 靠幂等补发自愈;群发逐人隔离 + 统计 + 幂等)。
3. **送达性在配置层解决,不在代码层** —— 发件域名验证 + SPF/DKIM 是第一件事;代码永远只是一个 HTTP POST,不碰签名/MIME。

---

## 1. 整体架构

### 1.1 发送链路:一个薄传输层,全 async,无队列无 SDK

```
业务代码  ──直接调──▶  services/email.py  ──httpx.AsyncClient POST──▶  Resend HTTP API
(注册端点 / 周报广播 / 工单)   3 个薄函数                         https://api.resend.com/emails
```
`email.py` 只有三个几乎同构的函数:`send_verification_email`(纯 HTML)· `send_report_email`(HTML + PDF 附件)· `send_email`(通用 HTML)。全部 `httpx` 裸 POST Resend REST,**无 SDK、无重试、无队列、无 adapter 抽象**。

### 1.2 用什么:Resend HTTP API + httpx 裸调(不用 SMTP、不用 SDK)

| 决策 | 理由 |
|---|---|
| **Resend HTTP API**(非 SMTP) | 免费 100 封/天 · API 干净(单端点 `POST /emails`,body 就是 `from/to/subject/html/attachments`)· 比 SMTP 少一堆信封/MIME 配置 |
| **httpx 裸调**(非 Resend SDK) | httpx 项目本已依赖 · 少一个 SDK = 少一层版本耦合 + 少一个供应链面(★还避开点金实测的「可选 extra 隐形坑」,见坑 8)|
| **撤销路径明确** | 换 provider(Postmark/SES/SMTP)只改这一层的 endpoint + header + body 映射,业务层零改 |

### 1.3 凭证 + dev 降级

凭证纯 env:`RESEND_API_KEY` · `EMAIL_FROM`。★**无 key 时 dev 降级「模拟投递」**:每个发送函数第一步读 key,没配就 `logger.warning(收件人 + verify_url)` 后 `return` —— 不报错、不阻塞,开发者从日志复制 URL 手动继续。本地/CI 零外部依赖即可跑通注册全流程。这是把「外部服务不可用」降级成「可观测的 no-op」而非「硬失败」。

### 1.4 ★邮件为什么独立于 IM(TG/飞书)通知的 dispatcher/adapter

点金的 IM 通知有一套 `dispatcher → adapter` 抽象(见姊妹篇),但 **`adapters/` 下只有 `telegram.py` + `feishu.py`,没有 email adapter**。邮件是完全独立的一条链路。为什么不把邮件做成 dispatcher 的一个 channel:

| 维度 | 邮件 | IM 推送 |
|---|---|---|
| **收件人寻址** | 裸邮箱字符串(注册必填、恒非空) | 绑定了 chat_id/open_id 的用户(需 `dispatch(user_id, event)` 查绑定再投递) |
| **内容形态** | 富 HTML + 附件(PDF/图 base64) + 退订链接 | 短文本 + 按钮 |
| **发件约束** | 已验证域名 + SPF/DKIM | bot token |
| **语义** | 正式送达 / 存档 | 即时提醒 |

> ★可移植原则:**通知渠道抽象要按「收件人如何被确定」+「内容形态」分层,不是所有出站消息都塞进一个 dispatcher。** 硬把邮件塞进 adapter 会让接口被迫容纳附件/HTML/退订等 IM 用不到的维度,抽象反而变脏。

### 1.5 「周报同时发邮件 + TG 提示」在哪协调

协调点**不在传输层、也不在 dispatcher**,而在业务的**广播编排层**的 per-user 循环里:
```python
for user in subscribers:                          # 查订阅表拉出的收件人
    try: await send_report_email(user.email, ...)  # 邮件:全文 + PDF 附件(走 email.py)
    except: email_failed += 1                       # 逐人 try/except 隔离
    try: await dispatch(user_id, WeeklyReportSentEvent)  # IM:只发「已发至邮箱」轻提示(走 dispatcher→adapter)
    except: notify_failed += 1
```
两条链路各自 try/except、逐人逐渠道隔离,**在业务层汇合而非在基础设施层耦合**。

---

## 2. 邮件的分类与触发

按【触发模式 × 收件人确定方式】天然分成**三大类**:

| 类 | 邮件 | 触发 | 收件人 | 失败契约 |
|---|---|---|---|---|
| **① 事务性** | 注册验证 / 重发验证 | 事件驱动(端点内即时 `await`) | 单人(payload 里的 email) | **不阻塞主流程**(注册照常成功,靠 `/resend` 补发) |
| **② 周期/营销** | 市场周报(HTML + PDF) | Celery beat 周日 21:00 + admin 手动 send-now | 查订阅表群发(`weekly_report_enabled=true`) | **逐人隔离** + year+week 幂等 |
| **③ 内部通知** | 工单/退款 · 智能复盘日/周/月报 | 事件(建单即发) / 定时 | 固定客服箱 / `role=admin` 群发 | **不阻塞建单**(工单已进 DB 是第一位) |

**关键设计原则:**
- **三类失败语义不同**(见上表末列)—— 这是整个可靠性设计的骨架(详见 §4)。
- **收件人筛选是铁律** —— 群发只发已订阅/已授权的人,筛选下沉到 SQL(`WHERE weekly_report_enabled=true`),不在发送循环里判断(不会漏)。
- **一次性 token 表** —— 验证 token 用 `secrets.token_urlsafe(48)`、24h 有效,存独立 `verification_token` 表(带 **`purpose` 枚举**),consume 时校验 `expires_at` 后失效。token 与邮件投递**解耦**:token 先落库,邮件失败不影响 token 有效性,可 `/resend` 重发。
- **无密码重置邮件** —— M0 决策裁剪(找客服),至今未实装。★但 `verification_token` 的 `purpose` 枚举为它预留了扩展位,加个 `reset` purpose 复用现成表即可。
- **防用户枚举** —— `/resend-verification` 对不存在的邮箱也返 202(不泄露账号是否存在)。★验证/重置类端点都应这样。

---

## 3. ★邮件内容生产

### 3.1 零模板引擎:f-string 纯函数「模板即代码」

**没有 Jinja2**(pyproject 里根本没这依赖)。所有 HTML 都是 Python f-string 直接拼,每个邮件类型一个 `def _xxx_html() -> str` 纯函数。理由:邮件 HTML 结构固定、量小、且最终要被内联进 JSON body,模板引擎带来的模板文件管理 + 转义层对这个规模是负资产;纯函数反而更可测、更透明。
> ★可移植结论:**小系统的事务邮件用「模板即代码」纯函数完全够用,不必上模板引擎。**

### 3.2 ★邮件 HTML 的两条兼容铁律(与网页 HTML 最大的工程差异)

1. **CSS 必须 100% inline** —— 写成每个元素的 `style=""` 属性,**绝不用 `<style>` 标签或外链**。因为 Gmail/Outlook/QQ 邮箱会**剥离 `<head><style>` 和外部样式表**,只有元素上的 `style=''` 才被稳定渲染。视觉一致靠**复用 hex 常量约定**而非共享 CSS。
2. **多栏布局用 `<table>` 而非 flex/grid** —— Outlook 用 **Word 排版引擎**,不支持 flex/grid/float。周报「▲走强 / ▼走弱」双栏就是 `<table cellpadding=0 cellspacing=0>` + 两个 `<td valign=top width=50%>`。

### 3.3 附件:Resend `attachments` base64(极简,无 multipart)

Resend 附件契约 = `[{filename, content(base64)}]`,content 是 base64 字符串直接内联进 JSON body —— **无 multipart、无上传步骤**。两种处理策略:
- **工单图片** —— 内存里 base64 编码直接发,**发完即弃,绝不落 DB / 磁盘 / OSS**(隐私 + 省存储)。
- **周报 PDF** —— 要留存可回溯,**先存对象存储(OSS)**再发送时下载回 bytes → base64。★同步 SDK(oss2)的 `put/get` 都包 `asyncio.to_thread` 不阻塞事件循环。

### 3.4 中文 PDF:reportlab 自带 CID 字体(免 bundle .ttf)

服务端生成中文 PDF 用 reportlab 自带的 **`UnicodeCIDFont('STSong-Light')`** —— CMap 随 reportlab 包发布,**免在 Docker 镜像里装 `fonts-noto-cjk` 之类系统字体或外挂 .ttf**,镜像更小、无字体缺失/豆腐块风险。注册用模块级 `_font_registered` 标志保证进程内只注册一次。
> ★可移植结论:**服务端生成中文 PDF,reportlab CID 字体是零依赖首选。**(注意:STSong-Light 是简体 CID 字体,繁体/生僻字可能缺字形。)

### 3.5 富内容周报的完整生产链路

```
运营上传成品(md + 精排 PDF)
  → pypdf 提取 PDF 文本(扫描件/无文本层 → 显式抛 422,不静默)
  → 解析 md:frontmatter(YAML)+ 固定 ## 标题正则切分(导语/核心结论/行业强弱/下周关注)
      · frontmatter 缺关键字段 → 硬失败 422;正文标题缺失 → 软降级记 missing
  → 填「定稿邮件模板」得 HTML 摘要(完整精排在 PDF)
  → 原始 PDF 存 OSS(weekly-dispatch/ 前缀,避开 report-materials/ 的 7 天 lifecycle)
  → 发送时从 OSS download → base64 → Resend attachments
```
★内容侧最终方案是**「运营上传成品、系统只做搬运 + 分发,不改写内容」**(早期的 AI 生成周报代码全保留但已停用)。理由:成品质量由人把控,系统保证免责固定不可省。

### 3.6 用户输入一律 `html.escape`

工单描述/联系方式、周报提取项、报告正文都是不可信文本,拼进 HTML 前一律转义 —— **任何把用户输入渲进邮件 HTML 的地方都要 escape**(防注入到收件箱)。

---

## 4. ★可靠性设计

核心是一个清晰的**「事务邮件 vs 群发邮件」二分**,两类走完全不同的失败契约。发送层极薄(三个函数,无 SDK、无重试、无队列),把「可靠性策略」的决定权全部上抛给调用方。

| | **事务邮件**(注册验证) | **群发邮件**(周报) |
|---|---|---|
| **失败处理** | `try/except` 吞异常只 log,**注册照常 commit 成功** | **逐人 `try/except` 隔离**,单人失败 `continue`,不影响其他人、不阻止 `status=sent` |
| **自愈** | 一次性 token 24h 有效 + `/resend-verification` 补发端点(天然幂等) | admin 手动「立即发送」重发 |
| **幂等** | token consume 后失效 | year+week DB 唯一约束 + 发送前再查 `status=='sent'` 跳过 |
| **可观测** | log | 返回统计四元组 `(email_sent/email_failed/notify_sent/notify_failed)` 给 admin 回显 |

**幂等三件套(定时 + 手动双触发必备):** ① 业务唯一键 DB 约束(year+week 一周一行)② 发送前再查状态哨兵(`status==sent → skip`)③ 定时任务只发 `scheduled` 状态、无则安静跳过。

> ★**点金没做、大规模系统必须补的两件事:**
> - **无重试无死信** —— 失败即丢,补发责任交给人(`/resend` / admin 重发)。点金规模可接受。
> - **无退信(bounce)处理** —— 没接 Resend bounce webhook,失效邮箱会一直占订阅位、每周被计入 failed 但没人清理。**大规模必须补 bounce webhook + 失效地址抑制列表**(硬退信反复发会拉低域名信誉)。

---

## 5. 合规与送达

走**务实最小闭环**路线,不追求完整 CAN-SPAM/RFC 8058,而是抓住三件真正影响送达的事:**发件域名信誉、退订可见、免责固定**。

### 5.1 ★发件域名(送达性地基 · 最大的坑)

**必须用已验证的自有域名**(`support@midastrade.asia` / `noreply@midastrade.asia`),**严禁用 Resend 测试域 `onboarding@resend.dev`** —— 测试域是 Resend 的共享未验证发件人,发到 Gmail 会被拒/进垃圾箱。DKIM/SPF **外包给 Resend 托管**:Resend 生成 DNS 记录、运营在域名商加几条 TXT(SPF+DKIM)、状态变 Verified 后 `EMAIL_FROM` 改成本域地址即可 —— **代码层完全不碰签名**。

### 5.2 退订:v1 极简版

周报邮件底部一个「退订」超链接,**直接指向账户设置页**(`/account/alerts`),用户登录后手动关订阅开关。退订 = 翻转 `weekly_report_enabled` 布尔位,复用现成的配置端点,零新代码。★**退订永远无门槛**(设 `false` 任何人都允许,是设计红线)。

### 5.3 免责:代码强制注入 + 多层兜底

周报邮件正文底部有固定 `DISCLAIMER` 常量,PDF 渲染时若内容缺免责**再补一行**(双保险),报告内容在生成阶段已过 `validate_advisory` 清营销违规词。**免责不依赖运营记得写,而是代码强制注入。**

### 5.4 ★已知缺口(新系统若量大必须补)

- **无 `List-Unsubscribe` 头**(RFC 8058 一键退订)—— 2024 起 Gmail/Yahoo 对批量发件人(>5000/日)**强制要求**,否则被限流甚至拒收。点金因量小暂缺。
- **无 DMARC 强制**(只强调 SPF+DKIM)—— 现代反垃圾闭环需 DKIM 对齐 + DMARC 策略。
- **无 bounce webhook / 无投诉率监控 / 无发送限流** —— Resend 有 webhook 能回传退信/投诉,点金完全没接。

---

## 6. 配置与开关

围绕两个雷区做设计:**防「测试环境误发真实用户」** 和 **防「向未请求的人群发」**。

### 6.1 ★防误发核心 = 凭证缺失即静默降级(而非环境判断)

每个 send 函数首行判 API key,没配就 `log + return` 不真发。**一招同时覆盖 dev / CI / 生产误配三种场景** —— 就算某人误在生产没配 key,也是「不发(安全)」而非「发错」。比 `if IS_DEV` 更稳。
> ⚠ 注意:这套**没有收件人白名单**(如「测试环境只发 @自己域名」),万一测试环境误配了真 key 就会真发。想更保险应叠加一层 allowlist 或 dry-run 开关。

### 6.2 防群发 = opt-in 订阅(三层默认 false + 查询层过滤)

周报订阅 `weekly_report_enabled` 在 model `server_default` / Pydantic 默认 / 查询三层都默认 `false`,广播只 `JOIN NotificationConfig WHERE weekly_report_enabled IS TRUE`。**把「谁能收」的裁决下沉到 SQL,而非发送循环里判断(不会漏)。** 从源头杜绝「给没订阅的人发信」—— 既是合规底线,也保护发件域信誉(未请求邮件 = 高投诉率 = 域名进黑名单)。

### 6.3 全局 kill-switch = 人工闸门状态机

周报**不自动生成、不自动群发**:admin 上传成品 → `uploaded` → 点「计划发送」→ `scheduled` → 周日 21:00 定时任务**只发 `scheduled` 的**(无则安静跳过,连提醒都不发),或 admin 点「立即发送」当场发。**状态机本身就是 kill-switch:默认 `uploaded` 卡住不发**,取消计划 `scheduled→uploaded` 可 21:00 前撤回改稿。

### 6.4 内部/诊断邮件从 SQL 限权

智能交易复盘是内部诊断工具,收件人**直接在 SQL `WHERE role=='admin'`** 限定,从数据源头杜绝误发给普通用户,比运行时过滤更不易错。

---

## 7. ★踩坑清单(可移植警示)

| # | 坑 | 根因 | 怎么避 |
|---|---|---|---|
| **1** | **发件域名(最大送达坑)**:`onboarding@resend.dev` 发不到 Gmail,`_from_addr()` 默认还回退到它 → 生产漏配 `EMAIL_FROM` env 就**石沉大海还查不到原因** | 未验证域名 SPF/DKIM 不通过被收件方拒/丢垃圾箱 | 上线前先在 Resend 验证自有域名 + DNS 配 SPF/DKIM(+建议 DMARC),`EMAIL_FROM` 用本域;★**建议把已验证域做成不依赖 env 的安全默认** |
| **2** | **样式错乱**:`<style>` 标签/外链 CSS 被 Gmail/Outlook 剥离;flex/grid 在 Outlook 失效 | 邮件 HTML 沙盒不支持顶层/外部样式;Outlook 用 Word 引擎 | 所有 CSS 写成元素级 `style=""` inline;多栏用 `<table>` 不用 flex/grid |
| **3** | **附件编码/大小**:Resend `content` 必须是 base64 字符串(`.decode('ascii')`)非原始 bytes;附件大小/数量 Resend 不会友好报错 | Resend 附件契约 | 附件先在**应用层限数量/大小**(如图 ≤5MB × ≤3 张),再 base64 |
| **4** | **中文豆腐块**:PDF 用默认拉丁字体渲中文出豆腐块 | reportlab 默认字体无中文字形 | 注册 `UnicodeCIDFont('STSong-Light')`(CMap 随包,免 bundle .ttf) |
| **5** | **群发拖垮整批**:for 循环串行 await,任一 raise 中断后续所有人 + 报告卡未发态 | 未隔离的批量发送 | 每人 `try/except` 独立计数,单点失败 `continue`;不阻止 `status=sent` |
| **6** | **幂等重复发**:定时任务 + 人工点击重复触发同一周报群发 | 无哨兵 | year+week 唯一约束 + 发送前再查 `status==sent` 跳过 + 人工闸门(`scheduled` 才发) |
| **7** | **dev 误发真实用户** | 无保护时本地测试会真调 Resend | 无 `RESEND_API_KEY` 时静默 no-op 只打 warning(含验证链接供手动继续) |
| **8** | **隐形依赖坑**(0002 §9/§10 实测翻车):Pydantic v2 `EmailStr` 需可选 extra `email-validator`;passlib argon2id 需 `argon2_cffi` 后端 | 可选 extra 默认不装,本地不启整套时不暴露,**docker build 后 api 容器 restart loop** | pyproject **显式列全所有非默认 extra**;docker build 阶段加冒烟 import test 提早暴露 |
| **9** | **循环 import**:`email.py` 被 report/auth 依赖,`report/send` 又反向需要 `email.send_report_email` | 双向依赖 | 在**函数体内延迟 import**,而非模块顶部 |

---

## 8. ★可移植性总结

### 8.1 最小核心(约 60 行薄传输层 · 直接抄 · 与点金业务零耦合)

`services/email.py` 的三函数同构骨架:
```python
def _api_key() -> str | None: return os.getenv("RESEND_API_KEY") or None

async def send_html(*, to, subject, html, attachments=None) -> None:
    key = _api_key()
    if not key:                                    # ① dev 无 key 降级:log 打链接,不报错
        logger.warning("RESEND 未配置 · 模拟投递 · to=%s", to); return
    body = {"from": _from_addr(), "to": [to], "subject": subject, "html": html}
    if attachments: body["attachments"] = attachments   # ② 附件 = [{filename, content(base64)}]
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(RESEND_ENDPOINT, headers={"Authorization": f"Bearer {key}"}, json=body)
            r.raise_for_status()
    except Exception as e:                          # ③ 失败归一化成 typed exception,策略上抛调用方
        raise EmailDeliveryError(str(e)) from e
```
这套 **薄传输层 + 三约定(无 key 降级 / 附件 base64 / 失败归一化异常)** 是任何 Resend 邮件系统的地基。

### 8.2 值得抄(跨项目通用原则)

1. **「事务邮件 vs 群发邮件」二分及其两套失败契约** —— 事务失败吞异常 + 靠幂等补发端点自愈;群发逐人 `try/except` 隔离 + 返回 sent/failed 统计。
2. **邮件 HTML 两条兼容铁律** —— 100% inline CSS + `<table>` 多栏(而非 flex/grid)。
3. **模板即代码** —— 小系统的事务邮件用纯函数拼 HTML,不必上模板引擎;用户输入一律 `html.escape`。
4. **幂等三件套** —— 业务唯一键 DB 约束 + 发送前查状态哨兵 + 定时任务 already-sent 分支。
5. **送达性在配置层解决** —— 已验证自有域名 + SPF/DKIM(踩过 `onboarding@resend.dev` 发不到 Gmail 的坑)。
6. **防误发 = 凭证缺失即静默降级** + **防群发 = opt-in 默认 false + 查询层过滤**。
7. **reportlab CID 字体**零依赖生成中文 PDF;**同步 SDK 一律 `asyncio.to_thread`**。
8. **通知渠道抽象按「收件人如何确定」分层** —— 邮件不塞进 IM 那种按用户绑定投递的 dispatcher,分成两个系统比强行统一更干净;多渠道协调放**业务广播层**而非基础设施层。

### 8.3 点金特有(不必带走)

- 中国红 `#C8102E` + 帝王金 + Noto Serif SC 品牌 HTML 模板(换成你自己的视觉)。
- **「不构成投资建议」免责红线 + PDF 兜底**(金融合规特有)。
- 阿里云 OSS(oss2)存 PDF 的 `weekly-dispatch/` 前缀避 lifecycle 那套(换成你的对象存储)。
- 周报「运营上传 md + PDF → pypdf 提取 → frontmatter + 固定标题解析 → 填模板」这套为「人工精排 + 系统分发」运营模式定制的流水线。
- 邮件与 IM 的「商务邮件 vs 行情推送」职能分离(取决于你是否也有 IM 推送支线)。
- **Resend 是可换的**(0006 撤销路径:改传输层 endpoint + body 映射即可切 Postmark/SES/SMTP)。

### 8.4 ★上线前送达/合规清单(点金隐含未成文 · 新系统应显式化)

- [ ] 选托管邮件 API(Resend/Postmark/SES),**加自有域名**
- [ ] DNS 配 **SPF + DKIM**(+建议 **DMARC** 策略)· 等状态 Verified
- [ ] `EMAIL_FROM` 用自有域,**永不用 provider 测试域**发生产邮件
- [ ] 订阅 **opt-in 默认 false** + 收件人查询层过滤
- [ ] 免责/合规声明**代码强制注入** + 多层兜底
- [ ] 退订链接可见(量大则补 **`List-Unsubscribe` 头**)
- [ ] 群发**逐人隔离** + 幂等键
- [ ](量大)接 **bounce/投诉 webhook** + 失效地址抑制列表
- [ ] 防误发:**无 key 降级** +(建议)测试环境收件人 **allowlist / dry-run**
- [ ] 依赖:pyproject **显式列全** `email-validator`/argon2 等可选 extra + docker 冒烟 import test

---

## 9. 与《TG 通知系统设计参考》的关系(姊妹篇速查)

| | **邮件系统(本篇)** | **TG/IM 通知(姊妹篇)** |
|---|---|---|
| 传输 | httpx 裸调 Resend HTTP API | httpx 裸调 Telegram Bot API |
| 抽象 | 薄传输层(3 函数),**无 dispatcher/adapter** | dispatcher(编排)+ adapter(per-channel)五层链路 |
| 收件人 | 邮箱字符串(注册必填) | 绑定的 chat_id/open_id(需 resolve) |
| 触发 | 事件(验证)/ 定时(周报)/ 手动 | 事件(成交)/ 定时(告警扫描) |
| 内容 | 富 HTML + PDF 附件 | 短文本 + emoji + 按钮 |
| 可靠性共性 | **主链路不阻塞 · 逐人失败隔离 · 幂等 · 无 key/降级** | 同(fire-and-forget · ChannelResult 隔离 · 边沿状态机) |
| 协调点 | 业务广播层 per-user 循环里两条腿并行 | —— |

两篇共享的可移植内核:**传输层薄 + 失败隔离 + 幂等 + 凭证缺失降级 + 主链路零阻塞。** 差异全在「收件人寻址」和「内容形态」—— 这正是它们被拆成两个系统的原因。

---

*7 镜头只读调研产出(架构 / 分类触发 / 内容生产 / 可靠性 / 合规送达 / 配置开关 / 踩坑)· 全程零改代码 · 面向"在新系统实现同类邮件功能"的开发者。行号/函数名佐证见各镜头原始调研,可按需深挖。*
