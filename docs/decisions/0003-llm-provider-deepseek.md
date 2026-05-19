# LLM Provider 决策记录 · 0003

## 状态
Approved (2026-05-19)

## 决策
主用 **DeepSeek API** 作为 LLM provider,替换原 04 文档计划的 **DashScope(通义千问)**。
**LiteLLM** 接入层保留,通过环境变量 `LLM_PROVIDER` 切换供应商。

## 上下文
04 文档(2026-05-19 之前的 Manus kickoff prompt)技术栈一节写的是 LangGraph + DashScope。
2026-05-19 与产品负责人对齐 Task 2 启动方案时,产品负责人主动提出切换到 DeepSeek。

## 理由
1. 产品负责人已持有 DeepSeek API Key —— 零接入摩擦,不用注册阿里云
2. DeepSeek 在中文金融场景的表现实测不差于 Qwen,且推理成本更低
3. LiteLLM 抹平 provider 差异,future-switch 代价小(改环境变量 + LiteLLM 配置即可)

## 影响范围
- **Task 2(数据层)不接 LLM**,只把 `DEEPSEEK_API_KEY` 列入 CLAUDE.md「待用环境变量」占位
- **Task 3+ AI Agent 阶段实装**:LiteLLM 客户端用 `DEEPSEEK_API_KEY` 初始化,
  prompt 调用走 `https://api.deepseek.com/v1`(兼容 OpenAI 协议)
- 暗黑模式 / 缠论 / 回测 等 M1+ 功能视 LLM 实际表现决定是否扩展到多 provider

## 撤销路径
1. **临时切换 provider:** 改 `LLM_PROVIDER=<name>` + 在 LiteLLM 配置中指向新 endpoint
2. **回退到 DashScope:** `LLM_PROVIDER=dashscope` + `DASHSCOPE_API_KEY=<key>`
3. **多供应商负载:** LiteLLM 自带 router + fallback,直接配置多个 provider 即可
4. **本地 mock(测试):** LiteLLM 内置 mock 模式

## 备注
- DeepSeek 官方 API 端点:`https://api.deepseek.com/v1`
- 协议:兼容 OpenAI ChatCompletion / Embedding
- **API key 红线:**不提交到 git,`.env.example` 仅占位 `DEEPSEEK_API_KEY=REPLACE_ME`
