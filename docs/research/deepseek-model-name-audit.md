# DeepSeek 模型名写死排查(P1-4c 块4b · 2026-06-05)

> 背景:实测 DeepSeek `deepseek-v3.2` 已废、现为 `v4-pro` / `v4-flash`;若代码写死旧版本名,
> 调用会 400。本报告**全仓 grep 定位**所有模型名出现处 + 建议改法,**先不改**,等 Hans 定。

## 结论(令人安心)

**全仓零 `deepseek-v3.2`、零 `v4-pro`/`v4-flash`、零任何钉死的版本号。** 唯一的模型名是
**`deepseek/deepseek-chat`**(litellm `provider/model` 格式),且是 **env `LLM_MODEL` 可覆盖的
配置默认值**,不是散落各处的硬编码。`deepseek-chat` 是 DeepSeek 的**稳定别名**(指向其当前
chat 模型),正常不会 400 —— **但它在 DeepSeek 当前 API 上是否仍有效,需 Hans 实测确认**(见声明)。

## 所有出现位置(grep 全仓 apps/ + docs/)

| 文件:行 | 内容 | 性质 |
|---|---|---|
| `apps/api/app/core/config.py:64` | `llm_model: str = "deepseek/deepseek-chat"` | ★ **唯一真·配置默认值**(pydantic settings · env `LLM_MODEL` 覆盖) |
| `apps/api/.env.example:35` | `LLM_MODEL=deepseek/deepseek-chat` | 示例 env |
| `apps/api/app/models/ai_usage.py:30` | `# LiteLLM 用的 model 名(eg. "deepseek/deepseek-chat")` | 注释举例(非代码) |
| `docs/deployment-runbook.md:268` | `LLM_MODEL=deepseek/deepseek-chat` | 部署文档 |
| `docs/research/ai-simulated-trading-feasibility.md:42` | `litellm.acompletion(model="deepseek/deepseek-chat", ...)` | 调研文档引用 |

**实际被调用链用到的只有 `settings.llm_model`**:
- `apps/api/app/services/ai/llm.py:101` → `model=settings.llm_model`
- `apps/api/app/services/ai/workflow.py:148` → `model=settings.llm_model`
- `llm.py:4` 注释:「切换模型零成本(改 env `LLM_MODEL` 即可)」

→ 即:**改模型不需要动代码,改 env `LLM_MODEL` 即可**;config.py 的默认值只是 env 没设时的兜底。

## 建议改法(★ 等 Hans 定 · 本步不改)

**前提**:Hans 实测确认 `deepseek-chat` 别名在当前 DeepSeek API 上是否仍有效。
- **若 `deepseek-chat` 仍有效**(大概率,DeepSeek 一贯保留此别名指向最新)→ **无需改任何代码**;
  生产 env `LLM_MODEL` 设成什么就用什么。建议保持别名(自动跟随 DeepSeek 升级,免再踩版本废弃)。
- **若要钉到具体新模型**(如 v4-pro/v4-flash)→ **优先改生产 env `LLM_MODEL`**(零代码改、零部署风险);
  litellm 的 DeepSeek 模型名格式确认后填(如 `deepseek/deepseek-chat` 或 DeepSeek 文档给的新 model id)。
- **若别名已废需改默认值** → 一并更新 3 处文案保持一致:
  `config.py:64` 默认值 + `.env.example:35` + `docs/deployment-runbook.md:268`(注释/文档同步,免误导)。

★ litellm 注意:DeepSeek 在 litellm 里走 `deepseek/<model>`(provider 前缀 `deepseek/`)。改 model id 时
保留 `deepseek/` 前缀(否则 litellm 不知走哪个 provider)。具体 `<model>` 取值以 DeepSeek 官方
+ litellm 支持列表为准(Hans 实测一次 acompletion 即可验证不 400)。

## 声明 vs 实测
1. **我没调 DeepSeek API**:无法确认 `deepseek-chat` 别名在当前(2026-06)是否仍解析有效 ——
   这正是任务说的「v3.2 已废、现 v4-pro/v4-flash」需 Hans 实测的事(跑一次 `llm.py` 的 acompletion
   看是否 400 即可)。本报告只确认**代码没写死任何废版本号**(没有 v3.2),用的是别名 + env 可覆盖。
2. **grep 范围**:apps/ + docs/(.py/.ts/.tsx/.md/.env/.yml)。前端(apps/web)未发现任何 DeepSeek 模型名
   (模型只在后端 AI 服务用,前端不碰 · 符合「不在前端塞 API/模型配置」红线)。
3. **不改**:按约定本步只排查 + 给建议,改 env/默认值等 Hans 定。
