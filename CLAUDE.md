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
- **终端交易 UI 一律不出现"虚拟/模拟"字样**(后台本就虚拟资金,无需反复提醒,影响体验)·
  虚拟/模拟说明只在官网(landing)做一次统一说明;旧的「VIRTUAL · 模拟」徽章规范已废止(实际从未实现)。
  例外不动:AI 输出/投资免责语(用"仅供参考/不构成投资建议",不含"虚拟"二字,是另一条锁死红线)。
  · ★边界澄清(2026-06-20 · Hans 授权 · commit d69ddf6):landing 官网「虚拟实战」**营销展示块**底部那一行
    免责「⚠ 分析仅供参考,不构成投资建议。所有交易均为虚拟资金模拟。」已按产品决策**移除**。
    ★这只是【landing 营销展示块】的一次性移除;**产品实际 AI / 策略 / 交易【输出】处(决策卡 / AI 分析 /
    策略信号 / 缠论分析等)的免责语仍强制、锁死红线完全不变、一个没动**。未来 session 看到 landing 该处
    无免责 = 有意为之的产品决策,**勿当红线回归擅自加回**。详见 docs/decisions/0011 § 补充 + 0012 § 补充。
- **缠论中枢专用中性色:淡灰蓝 #6482A0(填充 rgba(100,130,160,0.18))**
  · 仅限缠论中枢矩形(震荡区间)· 视觉系统外唯一新增色 · 不得在其他模块使用

## 工作风格
1. 每完成一个功能模块,暂停等我 review,我说"继续"再进下一个
2. 文档不清楚的地方先问,不要凭猜测写代码
3. commit 用中文 message + 任务编号前缀,如 [Task 2.3] xxx
4. 小步提交,每个功能点一个 commit
5. 代码必须用 2025 最新语法,不要 any,不要 Pydantic v1,不要 Pages Router

## 红线
- 不接入真实交易通道
- AI / 策略 / 交易**输出**必带 "仅供参考,不构成投资建议"(指产品实际输出:决策卡 / AI 分析 / 策略信号 / 缠论分析;红线照旧、不可动。唯一例外是 landing「虚拟实战」营销展示块那行已移除——见上「视觉系统 § 例外不动」边界澄清 + docs/decisions/0011·0012)
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
- **自验绝不接会吞退出码的管道**(`命令 2>&1 | tail` 让退出码 = `tail` 的 0,吞掉真实 exit 1)。lint / build / test 必须直接取命令真实退出码:`命令 > 日志; EXIT=$?` 或 `set -o pipefail`,非零即失败、如实报。详见 docs/decisions/0033 翻车。
- **部署成功以三者为准,绝不凭「代码已合 main」就报成功**:① GitHub Actions 状态绿(`gh run watch --exit-status` / `gh run view` conclusion=success)· ② 服务器 `docker compose ps` 容器真重建(CREATED 是本次 + healthy)· ③ 改了显示的话真机抽查。详见 docs/decisions/0033。
- **多页面 / 多市场功能,验收必须真机覆盖【用户实际会用的每一个页面 / 入口】,不能用「后端测试过 + 某一个前端面验到」冒充「全覆盖」。** 动手前先列「该功能应覆盖的所有页面/入口」清单,逐页真机(像用户那样正常访问 · 零 mock · 零特殊构造),缺一不可。
  本 session 翻车:AI 模拟交易第一层(actionable + 一键模拟下单)只接了 `AiDecisionCard`(workbench / cn / us 详情页),漏了 crypto perp 详情页 `/crypto-preview` 用的 `CryptoAiCard`(★同一功能在不同页面 / 市场可能是【不同前端组件】);真机只验了 `/workbench` 就报「三市场跑通」,用户在主力使用面 `/crypto-preview` 看不到 → 典型「报告上线但用户看不到」。根因:① 同功能多组件;② 真机只验一个面 = 给「全覆盖」假象。build 过 + 后端测试过 + 单一前端面验到 ≠ 全覆盖。

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
- **retry 只在最贴 transport 的一层做,不要分层叠加。**
  详见 docs/decisions/0002-data-sources-pitfalls.md § 翻车 8 —— 前端 TanStack Query × 后端 `_retry` 双层叠加 = 44s 卡住用户。任何分布式系统都会撞这个坑,不只是数据源。
- **可选 extra 是隐形坑** · pyproject 必须显式列所有用到的 backend。
  详见 docs/decisions/0002-data-sources-pitfalls.md § 翻车 9/10 —— `pydantic[email]` / `passlib[bcrypt,argon2]` 这类括号写法,在代码用了非 default backend 时必须更新 deps;docker build 阶段加冒烟 import test 提早暴露。
- **SQL `ORDER BY ... LIMIT N` 凡涉及「最新 / 最旧」语义,必须显式 `DESC` + Python reverse,不依赖排序方向的偶然。**
  详见 docs/decisions/0010-data-accuracy-diagnosis.md —— `select_kline` 用了 `ORDER BY ts ASC LIMIT N`,语义是「最早 N 根」而不是「最近 N 根」;`limit=1` 时取到 2018-06 NVDA $3.15(后复权古价),撮合 / 30s 报价 / 价格异动 / 浮盈估值整条链路全错,显示成 NVDA $6.55 / BTC $26K。修法:DB 端 `DESC LIMIT N` + Python `list.reverse()` 还原调用方期待的 ASC 升序契约。任何「最新 / 最近 / 最旧 / 最早」语义的窗口查询都必须走这套显式模式,绝不依赖隐式排序。
- **自验脚本绝不用 `| tail` / `| head` 等吞退出码的管道判断成败 —— 必须直接取命令真实 exit code。**
  详见 docs/decisions/0033-self-verify-exit-code-swallow.md —— `pnpm lint 2>&1 | tail -5 && pnpm build 2>&1 | tail -4` 让管道退出码 = `tail` 的 0,把 `pnpm` 的 exit 1 吞成 0,误报「build 过」;实则 web 镜像 `next build` 因一个未用变量(`minutes` 改文案后失去引用)lint error 失败,合 main 后 update.sh 在 build 步(3/7)退出、回滚到上一稳定版,新代码没真正上线。本地其实也会失败(非环境差异);CI / update.sh 回滚都正常,纯粹是自验吞了退出码。正确写法:`命令 > 日志; EXIT=$?`(redirect 保留退出码)或 `set -o pipefail`,非零即失败、如实报;且部署成功必以 Actions 绿 + docker ps 真重建为准(协作铁律 §2)。

## 待用环境变量(后续阶段才接,当前 Task 不动)

| 变量 | 用途 | 何时接 |
|---|---|---|
| `DEEPSEEK_API_KEY` | LLM provider(主用 DeepSeek,见 docs/decisions/0003) | Task 3+ AI Agent 阶段 |
| `HTTPS_PROXY` | 代理 yfinance / ccxt | 2026-05-19 实测国内直连可用,**暂不接入**,直连失败再启用 |
| `FEISHU_WEBHOOK_URL` | 飞书机器人 webhook | Task 6 推送 |
| `TG_BOT_TOKEN` / `TG_CHAT_ID` | Telegram bot 推送 | Task 6 推送 |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` 或 `RESEND_API_KEY` | 邮箱验证 | NextAuth v5(M0 验收第 2 步) |
| `LLM_PROVIDER` | 切换 LLM 供应商(默认 `deepseek`)| Task 3+ |
