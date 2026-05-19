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
- AI: LangGraph + DashScope (通义千问)

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
