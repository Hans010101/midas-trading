# i18n Phase 4 · 后端 AI 双语生成链路 · 接线方案(待核 · 研究先行)

> 目标:用户 `language_pref=en` 时,面向用户的 AI 内容用**英文原生 prompt** 生成 + 过**英文 validator**(i18n-4 已上线)。
> ★红线:**中文路径零变化**(默认 zh·现有用户零感知·和 i18n-4 向后兼容同款标准)。
> ★不碰:前端组件 · **75 条中文 prompt 本体**(分发是加路由不是改 prompt)· dark-mode · 主树。
> 方法:6-agent 只读调研(读干净 origin/main)。全程零改代码。

---

## 一、现状盘点(接线点)

### 1.1 面向用户的 AI 生成入口 = 3 类真 LLM(其余是规则)
| 入口 | 真 LLM? | service / prompt | 端点 | 前端(★多组件多页) |
|---|---|---|---|---|
| **决策卡·技术面**(score/narrative) | ✅ | `agents/technical.py` `_SYSTEM_CN/US/CRYPTO/HK` | `GET /analysis/decision-card` | workbench + cn/us/hk/spot/crypto-preview(5+ 面·AiDecisionCard/CryptoAiCard) |
| **决策卡·交易计划解释**(plan_note) | ✅ | `agents/plan_note.py`(价位是纯规则算·plan_note 只解释) | 同上(workflow 节点4) | 同上 |
| **结构诊断·沙盘** | ✅ | `structure/prompts.py` + `structure/workflow.py` | `POST /structure/diagnose` | /lab/assistant |
| 策略信号/推荐 | ❌ 纯规则 | strategy_signals/recommend | /analysis/strategy-* | → 归**静态 i18n 批**(非本方案) |
| 布林结构分类 | ❌ 分类器 | boll_state | /crypto/boll-structure | → 静态 i18n 批 |

★**排除**:推文/币安广场(X 模块)· 复盘 review_report(admin 面·非海外 C 端·后续)。

### 1.2 LLM 统一入口(chokepoint)
`services/ai/llm.py` · `ainvoke(prompt, system, response_format_json, max_tokens, temperature)` —— **统一 LiteLLM 层**(自动 mock/real·DeepSeek·`llm_model='deepseek-chat'`)。★system prompt 硬编码中文、分散在各 agent(`agents/technical.py` 4 市场 + `plan_note.py` + `structure/prompts.py`)——**没有单一 prompt 分发点,分发要在各 agent 加**(但只是"选哪个常量",不改中文常量本体)。

### 1.3 language_pref 流(★主要管道工作)
- `user.language_pref` 字段 + `/auth/me` 回显 + `PATCH /user/language` **已上线**(i18n-2)。
- ★但**没传到任何 AI 生成层**。端点已天然携带 user(`CurrentUserDep`/`OptionalCurrentUserDep` 返 User 对象)——**无需新依赖**,取 `user.language_pref` 即可。
- 要穿 4 层:**L1 端点取 lang → L2 workflow/service 收 `language='zh'` keyword-only 参 → L3 agent 选 prompt 版本 → L4 validator + cache 加 lang**。每层 ~5-10 行。

### 1.4 validator(i18n-4 已上线)
`validator.py` 6 函数 + `ADVISORY_DISCLAIMER_EN` + `ensure_advisory_disclaimer_en` **已在 main**。★但 **8 处消费方调用都没传 language**(全默认 zh)。en 输出要:调用点传 `language="en"` + 3 主输出节点(narrative/plan_note/conclusion)补 `ensure_advisory_disclaimer_en` 兜底。

### 1.5 缓存(★zh/en 会串)
Redis 决策卡 key = `ai:decision:{market}:{symbol}:{period}:{trading_day}`(`cache.py make_cache_key`)——**无 lang 段 → 中英用户互相覆盖**(英文用户看到中文卡)。必须加 lang。DB 表(ai_analysis_memory / AIUsageLog / IntelligentReview / MarketReport)加 `language` 列(存**实际生成语言**·非用户偏好)。

---

## 二、接线设计(4 层穿参 + prompt 分发 + en 门禁 + 语言锁)

### 2.1 prompt 按语言分发(★零碰中文 prompt 本体)
```python
# agent 里:不改中文常量,只加"选版本"
_SYSTEM = {"zh": _SYSTEM_CN, "en": _SYSTEM_CN_EN}  # zh 命中的永远是【现有未改动常量】
system = _SYSTEM.get(language, _SYSTEM_CN)[market]   # 默认 zh 兜底
```
★`language` 默认 `"zh"` → 命中的永远是**今天逐字节相同的中文常量** = 研究报告"LLM prompt 绝不翻"红线的落地。en 常量是 i18n-5 交付的**新常量**(不改旧的)。

### 2.2 ★语言锁防串台(双层·缺一不可)
DeepSeek 已知 bug(repo Issue #1226:纯英文对话偶回整段中文)——**只靠 prompt 指令挡不住**:
1. **第一层·prompt 内**:英文 prompt 顶部 `[LANGUAGE LOCK] Respond ENTIRELY in English. No Chinese characters under any circumstance.`(i18n-5 已含)。
2. **第二层·Python 兜底**:en 输出后检测 CJK 码点,若含中文 → 降级(重试 / 回退英文模板 / 标记),**不让中文漏到英文用户**。

### 2.3 en 输出过 en validator + 免责兜底
en narrative/plan_note/conclusion 生成后:`rewrite_imperatives(text, language="en")` + `scrub_marketing(..., "en")` + `ensure_advisory_disclaimer_en(text)`。zh 路径调用点不变(默认 zh)。

---

## 三、★中文零变化保证(红线·和 i18n-4 同款)

1. **所有新参 keyword-only + 默认 `"zh"`** → zh 路径不新增任何分支执行、走的还是现有那行代码。
2. **prompt 分发用 dict.get(language, 中文默认)** → zh 命中现有未改动常量,`_SYSTEM_CN/US/CRYPTO/HK` + `PLAN_NOTE_SYSTEM` + structure 中文 prompt **一个字符不动**。
3. **validator zh 路径已在 main 验证一字不变**(test_validator_en 含向后兼容测)。
4. **铁证方法**:① `git diff` 现有中文 prompt 常量 = 空 ② 现有 decision-card/structure 测试全绿(不传 language 默认 zh)③ 端到端真机 zh 用户逐页无变化。

---

## 四、缓存/存储 lang 分 key
| 对象 | 现状 | 改造 |
|---|---|---|
| **Redis 决策卡缓存**(必改·第一版) | `ai:decision:{market}:{symbol}:{period}:{day}` | 加 `:{lang}` · make_cache_key + get/set/delete_cached_card 全加 language 参透传 |
| ai_analysis_memory(DB) | 无 language 列 | 加 language 列(存**生成语言**·命中率按语言拆)· 迁移 |
| AIUsageLog(DB) | 无 language | 加 language 列(成本可按语言归因·但**月预算守卫合并计**·不分语言阈值) |
| IntelligentReview / MarketReport | 无 language | admin 面·后续(非本方案第一版) |

---

## 五、拆刀建议(每刀独立可交付·由易到难)

| 刀 | 范围 | 工作量 | 依赖 |
|---|---|---|---|
| **刀1 · 接线管道**(纯管道·不接任何 en 内容·**zh 零变化**) | L1-L4 穿参骨架:端点取 language_pref → workflow/service/agent 加 keyword-only `language='zh'` → 透传到 validator + cache 加 lang 参。**不接 en prompt·功能等价现状** | **S**(最易) | 无·**是后续所有刀的地基·可独立合并上线零风险** |
| **刀2 · en 决策卡**(technical + plan_note·4 市场) | 接 i18n-5 交付的 `_SYSTEM_*_EN` + `PLAN_NOTE_SYSTEM_EN` + 语言锁 + en validator + 免责兜底 + 缓存 lang 分桶 | **M** | 刀1 + **i18n-5 转成真 prompt 常量(需人工润色)** + en LLM 成本 |
| **刀3 · en 结构诊断**(沙盘) | `structure/prompts.py` 加 `SYSTEM_PROMPT_EN`(三红线英文对等·术语锁)+ en conclusion 过校验 + 诊断缓存 lang 分桶 | **M** | 刀1 + i18n-5 |
| 刀4(可选·延后) · 规则层静态文案 | composite_label(强多/弱多…)/actionable hint/trading_plan 模板 = **静态字符串非 prompt** | **M** | ★**归静态 i18n 批·不夹带进 AI 双语**(actionable.py `_BULLISH/_BEARISH` 中文匹配·误改会串) |

---

## 六、★需 Hans 拍板

1. **第一版接哪几类**:建议 **刀1(管道·必做地基)+ 刀2(en 决策卡·最高价值·5 面主力)** 先上,刀3(结构诊断·红线密面窄)紧随,刀4 归静态批。
2. **英文生成 LLM 成本 + provider**:继续 **DeepSeek**(不换·撞 ADR0003 + 涉钱是单独大决策)· 成本非变量($0.14/$0.28 每 M)· ★但需**确认生产 `DEEPSEEK_API_KEY` 已配**(没配则 en 走 mock 假数据)。
3. **★硬门顺序(不可绕)**:en 红线校验(validator·已 main)+ en 免责兜底 + 语言锁 **必须先于任何 en AI 输出上线**——否则英文卡缺免责/含 should buy 直接踩死红线。
4. **i18n-5 依赖**:en prompt 现在是**草稿**(docs/i18n/·非真 prompt 常量)· 刀2/3 前需把草稿**转成真 prompt 常量 + 人工润色定稿**(可作刀2 的第一步·或单独一刀)。
5. **ai_analysis_memory 的 language 列**:存**生成语言**(非用户偏好·同一用户可切语言·历史反映当时生成语言)。

---

## 七、风险(诚实·按危险度)

1. **★串台(最高危·实锤)**:DeepSeek Issue #1226 偶回中文 → **prompt 语言锁 + Python CJK 码点检测双层缺一不可**。
2. **zh 回归**:prompt 分发若 else 分支不慎改了现有中文常量取用 → 破 zh 红线 · 防线 = **diff 铁证中文常量为空 + 现有测试全绿**。
3. **缓存串**:decision-card key 无 lang → 中英互相覆盖 · **必须 make_cache_key + get/set 全加 lang**。
4. **接缝翻车(项目铁律)**:language 5 层透传,任一层漏传 = 默认 zh **静默降级**(英文用户拿中文·无报错更隐蔽)· 必须**组装期端到端真机 + 英文用户逐页**(workbench + cn/us/hk/spot/crypto-preview,同功能多组件)。
5. **en 免责/红线漏兜**:3 主输出节点都没调 `ensure_advisory_disclaimer_en` · en 上线前逐节点补·漏一处 = 缺免责。
6. **i18n-5 未就位**:en prompt 分支空 · 刀2/3 强依赖 i18n-5 转真常量 + 润色 · 刀1 可先独立上线不阻塞。

---

*调研 6-agent 只读产出(1 路 llm-chokepoint 失败但内容已被 ai-entries/lang-flow 覆盖:llm.py 统一 ainvoke + 中文 prompt 在 agents/·无单一分发点)· 零改代码 · 待 Hans 核方案 → 核过写码(从刀1 管道起·zh 零变化)。*
