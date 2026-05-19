# 点金 Midas · Claude Code 项目上下文

## 我是谁
项目所有者(非全职开发),.NET/Blazor 背景,做过 CryptoSharp 加密交易系统。
新项目用 Python + Next.js,我做产品决策和 review,Claude Code 做主力编码。

## 项目本质
面向 A 股 / 美股 / 加密三市场的 AI 原生分析终端,**仅虚拟资金交易,永不接真实下单**。
这是产品 DNA,任何场景下不要建议或实现接入真实交易接口。

## 当前阶段
M0 由 Manus 完成初步骨架(实际完成度约 5-10%,只动了 Task 1 / 7 的工程骨架),Claude Code 从这里接手。
M0 验收标准:陌生人能注册 → 看跨市场 K 线 → 建虚拟单 → 收飞书 TG 推送。

## 技术栈(锁定,不要建议更换)
- 前端: Next.js 15 App Router + TypeScript + Tailwind + shadcn/ui + KLineChart Pro
- 后端: FastAPI + Pydantic v2 + SQLAlchemy 2.0 async + Celery
- 数据: PostgreSQL 16 + ClickHouse + Redis
- 数据源: AKShare (A股) + yfinance (美股) + ccxt (加密)
- AI: LangGraph + DeepSeek API(替换原 DashScope,见 docs/decisions/0003)

## 视觉系统(严格执行)
- 主色 中国红 #C8102E
- 辅色 帝王金 #B8860B
- 涨用朱红 #DC143C,跌用墨绿 #0F6E5F(A 股传统)
- 标题 Noto Serif SC,正文 Noto Sans SC,数据 JetBrains Mono
- 白底为主,暖米白卡片 #FCFCF9
- 虚拟交易元素必带帝王金 "VIRTUAL · 模拟" 徽章

## 工作风格
1. 每完成一个功能模块,暂停等我 review,我说"继续"再进下一个
2. 文档不清楚的地方先问,不要凭猜测写代码
3. commit 用中文 message + 任务编号前缀,如 [Task 2.3] xxx
4. 小步提交,每个功能点一个 commit
5. 代码必须用 2025 最新语法,不要 any,不要 Pydantic v1,不要 Pages Router

## 红线
- 不接入真实交易通道
- AI / 策略 / 交易输出必带 "仅供参考,不构成投资建议"
- 不要早期堆功能(暗黑模式 / 客户端 / 缠论 / 回测 都不是当前阶段的事)
- 不要在前端塞 API Key
- 不要不打招呼就改技术栈

## 长会话管理(重要)
- 每完成 1-2 个 Task 就开新 session,把进度摘要带过去
- 不要在一个 session 里跑超过 3 小时
- 重要决策落到 git commit message 和 docs/ 里,不要只活在对话历史

## 参考文档位置
- docs/04-manus-kickoff-prompt.md - M0 启动文档(原始需求,Manus 只执行了 04 的视觉 token + 技术栈选型,Task 1.2 之后全部没动)
- docs/03-midas-project-plan.md - 项目计划 v2
- docs/01-guanchao-tideview-analysis.md - 观潮调研
- docs/02-guanchao-clone-feasibility.md - 克隆可行性

## 协作铁律(优先级最高,任何 Task 都遵守)

### 1. 并行优先
- 任何能并行的操作必须并行(读多个文件 / 跑多条命令 / 装多个包)
- 不要串行做无依赖的事
- 多文件编辑用单次批量调用,不要 N 次单文件来回

### 2. 自验闭环 · 不踢皮球
- 写完代码立即自跑,看实际输出而非"应该工作"
- 遇到错误自己看日志、自己查原因、自己改
- 卡在同一个错误超过 3 次才升级给我
- 不要把验证责任丢给我(例如:"请你跑一下试试" → 错。应该是"我跑了,输出是 X,通过")
- 报告里说"完成"必须等于"实测通过",写完没跑不算完成

### 3. 自主决策 · 事后审计
- 默认自己决策,不要每个小事都问
- 真正需要问的两种情况:① 涉及钱(付费工具 / 真实交易接口);② 多个合理路径且选错代价大(主要技术栈变更 / 数据库 schema 不可逆设计)
- 其他全部自己定,但所有决策落到 commit message 或 docs/decisions/ 里
- Checkpoint 汇报时列出"本阶段自主决策清单"
- 命名 / 文件结构 / 小依赖选择 / 注释风格 / 报错处理 → 全部你自己定

## 多 Task 工作模式(Checkpoint 模式)

「协作铁律」的战术化补充。当一次会话授权连跑多个 Task 时,按这个模式落地。

### 触发条件
- 用户明确说「一次会话连跑」/「只在 N 个节点 review」/「不要每个 sub-task 等我」之类
- 同时给出 N 个里程碑(通常 3-4 个),每个里程碑覆盖一组主题相关的 sub-task

### Checkpoint 划分与命名
- 用大写字母:**Checkpoint A / B / C / D**,按主题分组,不按时间均匀切
- 在 session 开头用 TaskCreate 列出全部 sub-task,让用户能跟进度
- 一个 Checkpoint 内的 sub-task 可以任意顺序、可并行,Checkpoint 之间按依赖排序

### 每个 Checkpoint 的收尾(三步,缺一不可)
1. **自验**:跑真实命令,看实际输出(`ruff` / `mypy` / `pytest` / `pnpm build` / `curl` 端点 / `docker compose ps` healthy)
2. **commit**:1~2 个 commit(主题分组),中文 message + 阶段前缀(`[P0]` / `[Task 1.2]` / `[Task 7.3]` / `[Rules]` / `[Decisions]`),body 多段描述变更 + 测试结果 + 自主决策
3. **tag**:`git tag checkpoint-a` / `checkpoint-b` / `checkpoint-c`,打在该 Checkpoint 的最后一个 commit 上

### 每次 Checkpoint 汇报必含字段
- **本阶段用时**(粗估即可,含构建等待)
- **自主决策清单**(每条一行 + 为什么这么选)
- **新增依赖**(npm / pip 都列出)
- **P1 残留 / 视觉细节没到位 / 下一步建议**

### 禁忌
- ❌ 不要在 sub-task 之间停下等 review(那是 Checkpoint 边界才做的事)
- ❌ 不要写完代码不跑就报「完成」(违反协作铁律 § 2)
- ❌ 不要为了赶进度跳过 docker rebuild / 浏览器验证 —— 没实测证据 = 没完成
- ❌ 不要在 Checkpoint 中段做需要拍板的大方向决策(归到 commit body 或 docs/decisions/)

### 退出该模式(必须停下找产品负责人)
- 用户主动说「暂停」/「停一下」/「等我」/「我看看」
- 同一个错误自验失败 ≥ 3 次(协作铁律 § 2 的红线)
- 遇到协作铁律 § 3 要问的两类决策:① 涉及钱(付费工具 / 真实交易接口);② 多个合理路径且选错代价大(主要技术栈变更 / 数据库 schema 不可逆设计)
- 当前 Checkpoint 已收尾(汇报后**默认继续下一个**,除非用户提前说停)

## 项目铁律(由实战总结)

工程纪律,跟「协作铁律」(工作流)是两件事——这里是实战中踩出来的血泪。
**每条必须引用 docs/decisions/0002 / 0004 / ... 中的某一条具体翻车**,不允许凭空想象。

- **clickhouse-connect 永远传 tz-aware datetime,绝不传 naive。**
  详见 docs/decisions/0002-data-sources-pitfalls.md 翻车 3 —— Python `astimezone()` 对 naive 默认按 OS 本地时区解释,在 CN(+8)环境下会写入偏移 8 小时的 epoch。
- **接缝处必有翻车** · 组装期单独跑端到端实测,模块单测全过 ≠ 集成层通。
  详见 docs/decisions/0002-data-sources-pitfalls.md § F 阶段总结 P1
- **用 framework 默认配置前先读 convention**,不要走默认走到 KeyError 才发现。
  详见 0002 § F 阶段总结 P2
- **Nullable 边界必须显式跨越**(Pydantic `T | None` ≠ DB / CH 列接受 None)。
  详见 0002 § F 阶段总结 P3 + 翻车 6
- **数据流终态用 SQL/工具直接看,别只看 Python 层打印** —— `toUnixTimestamp` /
  `SELECT *` / `clickhouse-client` 是调试存储层问题的金标准。
  详见 0002 § F 阶段总结 P4 + 翻车 3 + 翻车 6

## 待用环境变量(后续阶段才接,当前 Task 不动)

| 变量 | 用途 | 何时接 |
|---|---|---|
| `DEEPSEEK_API_KEY` | LLM provider(主用 DeepSeek,见 docs/decisions/0003) | Task 3+ AI Agent 阶段 |
| `HTTPS_PROXY` | 代理 yfinance / ccxt | 2026-05-19 实测国内直连可用,**暂不接入**,直连失败再启用 |
| `FEISHU_WEBHOOK_URL` | 飞书机器人 webhook | Task 6 推送 |
| `TG_BOT_TOKEN` / `TG_CHAT_ID` | Telegram bot 推送 | Task 6 推送 |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` 或 `RESEND_API_KEY` | 邮箱验证 | NextAuth v5(M0 验收第 2 步) |
| `LLM_PROVIDER` | 切换 LLM 供应商(默认 `deepseek`)| Task 3+ |
