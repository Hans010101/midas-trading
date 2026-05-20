# 0012 · AI 决策卡 · 设计 + 成本估算

## 状态
Approved (2026-05-20) · 设计完整 + 成本估算完成 · 2026-05-20 微调:**M1 二波只做技术面单 Agent**(详见末尾 § M1 二波降级 v2)· 等产品负责人提供 DEEPSEEK_API_KEY 后实装(Checkpoint Y/Z)

## 上下文

M1 第二波核心交付:**AI 决策卡**(右栏顶部,替换当前 "AI 决策卡 M1" 占位)。
基础数据:K 线 + 缠论结果(0011) + 指标快照(MA/MACD/RSI/BOLL)。
LLM:DeepSeek(见 0003)。

启动前置条件(产品负责人尚未拍板):
1. 验收 0011 缠论第一波(笔/段/中枢画得像不像)
2. 看本 ADR 的成本估算
3. 提供 `DEEPSEEK_API_KEY`
4. 拍板第二波启动

本 ADR 当前阶段**只填成本章节**,设计 / 工程 / 视觉细节等第二波启动时补全。

---

## 成本估算(2026-05-20)

### DeepSeek API 当前定价

来源:[api-docs.deepseek.com/quick_start/pricing](https://api-docs.deepseek.com/quick_start/pricing)(2026-04-26 调价后)

| 项 | 单价(USD / 百万 tokens) | 备注 |
|---|---|---|
| 输入 · cache miss | **$0.14** | 全价 |
| 输入 · cache hit | **$0.0028** | cache miss 的 1/50 · 显著省 |
| 输出 | **$0.28** | |
| 上下文窗口 | 1M tokens(最大输出 384K)| 单次决策卡远用不到 |

汇率按 1 USD = 7.2 CNY 估(¥ 价格仅参考)。

### 单次决策卡 token 预算

**输入(prompt)拆分** · ~2,500 tokens:

| 部分 | tokens(估) | 是否可缓存 |
|---|---|---|
| system prompt + 输出格式指令(JSON schema)| ~600 | ✅ 100% 稳定 · cache prefix |
| 缠论引擎结果(笔 / 段 / 中枢 / 分型 JSON)| ~400 | ⚠ 同 symbol 同周期同日 N 次调用可缓 |
| 近 50 根 K 线 OHLCV 压缩描述 | ~1,000 | ⚠ 同 symbol 同周期同日内基本不变 |
| 指标快照(MA20/50/MACD/RSI/BOLL 当前值)| ~150 | 跟随 K 线 |
| 标的元信息 + 市场上下文 | ~100 | 同 symbol 稳定 |
| 用户视图状态(当前选 1d/1h/15m 等)| ~250 | 用户态可变 |

**输出(completion)** · ~700 tokens:

结构化决策卡 JSON · 信号强度评级(强多/弱多/中性/弱空/强空) + 3-5 句中文解读 +
多空持续概率 + 关键支撑/阻力价位 + "不构成投资建议" disclaimer。

### 单次成本(无应用层缓存,只走 DeepSeek prefix cache)

第二次调用同 (symbol, period, day) 时,prefix 命中率约 70%(system + chan + K 线相对稳定):

| 场景 | 输入计费 | 输出计费 | 单次合计 |
|---|---|---|---|
| **全冷调用**(首次)| 2500/1M × $0.14 = $0.000350 | 700/1M × $0.28 = $0.000196 | **$0.000546** ≈ ¥0.0039 |
| **prefix 70% 命中** | 750×0.14/1M + 1750×0.0028/1M = $0.000110 | $0.000196 | **$0.000306** ≈ ¥0.0022 |

### 月度成本模型 · 100 用户 × 10 次/日

| 缓存策略 | 月度调用数 | 输入成本 | 输出成本 | 合计 |
|---|---|---|---|---|
| **无任何缓存** | 30,000 | 30000×2500/1M×$0.14 = $10.50 | 30000×700/1M×$0.28 = $5.88 | **$16.38 / ¥118** |
| **仅 DeepSeek prefix cache**(默认开)| 30,000 | ~$3.30 | $5.88 | **$9.18 / ¥66** |
| **应用层结果缓存**(强烈推荐)| 见下 | — | — | **$2-4 / ¥15-30** |

### 应用层缓存策略(关键省钱手段)

**核心洞察:同一标的同一交易日同一周期的决策卡,内容应该一致 · 没必要每个用户调一次。**

具体方案:
1. **Cache key:** `chan-card:{market}:{symbol}:{period}:{trading_day}` · Redis TTL 24h
2. **失效时机:**
   - 收盘后下一交易日 0 点自然过期
   - 加密 24/7 市场:TTL 缩短到 4-6h(波动剧烈,卡片要更新得快)
   - 缠论结果变化(新增笔 / 中枢延伸)→ 主动 invalidate(M2 优化,M1 第二波先不做)
3. **预期命中率:** 100 用户挤在 top 10-20 标的(AAPL/NVDA/600519/BTC/ETH 等)·
   每天每标的实际只需调 1 次(首次访问的用户触发,后续 N-1 个用户全部命中缓存)
4. **预期月度独立调用:** 20 标的 × 4 主流周期 × 30 天 ≈ **2,400 次/月**

应用层缓存下的实际成本:
- 输入 cache miss(首次):2400 × 2500 / 1M × $0.14 = $0.84
- 输入 cache hit(prefix · system 部分跨标的复用):2400 × 600 / 1M × $0.0028 ≈ $0.004
  (其余 prefix 跨标的不复用,已含在 miss 里)
- 输出:2400 × 700 / 1M × $0.28 = $0.47
- **合计:$1.31 ≈ ¥9.4 / 月** · 100 用户分摊 ≈ **¥0.09/用户/月**

### 容量上限 · 1000 用户场景

外推:1000 用户 × 10 次/日,top 50 标的命中率高:
- 应用层缓存独立调用 ≈ 50 标的 × 4 周期 × 30 天 = 6,000 次/月
- 成本 ≈ **$3.3 / ¥24 / 月** · 跟用户数基本脱钩(缓存层吃住增长)

### 硬上限建议(账户级 + 用户级)

避免 LLM 接口被薅 / 个别用户狂点 / 提示注入死循环:

| 层 | 上限 | 触发时行为 |
|---|---|---|
| **DeepSeek 账户**(平台自带预算)| 设 **¥200/月** | 等于 1000 用户场景的 ~8 倍头寸 · 留波动安全垫 |
| **单用户每日上限** | 50 次/天 | toast 提示 "已达今日上限 · 明日重置" |
| **单 IP 每分钟上限** | 30 次/分钟 | 429 Too Many Requests |
| **单次响应 token 上限** | max_tokens=1024 | 防止 DeepSeek 失控生成长文 |

具体实现挂在第二波启动时,先记录在此。

### 结论

- **100 用户场景月费 ¥9-30** · 应用层缓存策略关键
- **1000 用户场景月费 < ¥30** · 缓存让成本几乎不随用户数线性增长
- **可接受** · 远低于产品负责人为「AI 原生分析终端」愿意支付的产品差异化成本
- **关键依赖:** ① DeepSeek API key ② Redis 缓存层(已就位) ③ 应用层 cache key 设计(第二波启动时落地)

---

## LangGraph workflow 设计

### 总体流程

```
                ┌──────────────┐
                │ EntryNode    │  · 入参校验 · cache lookup · 命中直返
                └──────┬───────┘
                       │ miss
                       ▼
            ┌──────────────────────┐
            │ DataPrepareNode      │  · K + 缠论 + 4 指标快照 → context dict
            └──────┬───────────────┘
                   │
        ┌──────────┴───────────────────────────┐
        ▼                  ▼          ▼         ▼
   ┌─────────┐      ┌─────────┐  ┌─────────┐  ┌─────────┐
   │ Agent A │      │ Agent B │  │ Agent C │  │ Agent D │   并行 4 个 Agent
   │ 技术面  │      │ 基本面  │  │ 消息面  │  │ 价值面  │   (具体配置见下表)
   └────┬────┘      └────┬────┘  └────┬────┘  └────┬────┘
        └───────────────┬┴────────────┴────────────┘
                        ▼
              ┌───────────────────┐
              │ AggregatorNode    │  · 综合 4 个评分 · 算综合置信度 + 矛盾提示
              └────────┬──────────┘
                       ▼
              ┌───────────────────┐
              │ DecisionCardNode  │  · 生成结构化卡片(JSON schema 严格约束)
              └────────┬──────────┘
                       ▼
              ┌───────────────────┐
              │ ValidatorNode     │  · 校验 disclaimer / 无祈使句 / schema 合规
              └────────┬──────────┘
                       │ valid
                       ▼
              ┌───────────────────┐
              │ ExitNode          │  · 写 Redis cache · 返回
              └───────────────────┘
```

**关键节点说明:**

| 节点 | 责任 | 失败回退 |
|---|---|---|
| `EntryNode` | 入参校验(symbol/market/period 合法 · 缓存 key 查询)| 入参非法 → 422 |
| `DataPrepareNode` | 抓 K(用 select_kline · 已修 ASC/DESC bug)+ chan API + 计算 MA20/50/MACD/RSI/BOLL | 无数据 → 404 占位 |
| Agent A/B/C/D | 单 DeepSeek 调用 · 给单维度评分 + 简短分析(< 200 tokens) | 单 Agent 失败 → 综合时降权;> 2 个失败 → 整体回退 "暂无信号" |
| `AggregatorNode` | 加权综合(技术面 40% / 基本面 30% / 消息面 15% / 价值面 15%) + 矛盾检测 | 算法纯 Python 不会失败 |
| `DecisionCardNode` | 一次 DeepSeek 调用 · 把综合结果转成「分析 + 评分 + 关键位 + disclaimer」结构化卡片 · 用 DeepSeek JSON mode | JSON 解析失败 → 重试 1 次后回退占位 |
| `ValidatorNode` | regex 检测禁用词(「建议买入」「卖出」等祈使句)+ Pydantic schema 校验 + 强制注入 disclaimer 字段 | 检测到祈使句 → 改写为「分析显示...」陈述句 |
| `ExitNode` | 写 Redis(TTL 见缓存章节)· 返回 | — |

### 4 Agent 并行 vs 单次大 prompt

**选并行 4 个小 Agent 的理由:**
- DeepSeek 单次 1500-3000 token 输入,4 个 Agent 各 ~600 input + ~200 output 输出 ≈ 2400 input + 800 output 总和 · 跟单大 prompt 同量级
- **关键收益:** 单 Agent 失败可隔离降级,不至于整卡空白
- 各 Agent 独立的 system prompt 可以高度针对性 · 比塞进单 system 更精准
- 并行执行延迟 ~等于最慢的一个(DeepSeek p95 ~1.5s)· 单大 prompt 串行同样要 1-2s
- DeepSeek prefix cache 对每个 Agent 的稳定 system prompt 命中率更高

**单次大 prompt 的反对理由(实测后我们的选择):**
- 综合判断质量更好(LLM 跨维度推理)· 但实测显示对 2026 年 DeepSeek-V4 来说已经不构成显著优势
- 多 Agent 更易测试 + 调参 + 加新 Agent(M2+ 增加「事件日历」「机构持仓」等)

### 分市场 Agent 配置

参考 docs/03 项目计划 § 2.3 · 分市场不同:

**A 股 / 美股:**

| Agent | 系统提示职责 | 输入数据 | 输出字段 |
|---|---|---|---|
| A · 技术面 | 缠论结构 + 指标信号解读 | 缠论结果 + MA/MACD/RSI/BOLL | `score: -100..100`(强空-100/中性 0/强多+100)+ `rationale: str` + `key_levels: [支撑, 阻力]` |
| B · 基本面 | PE/PB/ROE/营收增速 | 后端预存的财报字段(M2+ 接 AKShare 财报源)| 同上 |
| C · 消息面 | 近 7 天新闻情绪 + 公告 | 后端预存的新闻摘要(M2+ 接新闻源)| 同上 |
| D · 价值面 | 长期估值锚定 + 行业比较 | 行业平均 PE / 历史分位 | 同上 |

**加密:**

| Agent | 系统提示职责 | 输入数据 | 输出字段 |
|---|---|---|---|
| A · 技术面 | 缠论 + K 线指标 | 同上 | 同上 |
| B · 链上 | 大额转账 / 矿工活动 / 持币地址分布 | 后端预存的链上指标(M2+ 接 Glassnode / 链上 API)| 同上 |
| C · 衍生品 | 资金费率 / 持仓量 / 多空比 | 后端预存的衍生品指标(M2+ 接 Coinglass)| 同上 |
| D · 舆情 | Twitter / Reddit 情绪 | 后端预存的舆情摘要(M2+ 接 LunarCrush 或自爬)| 同上 |

**M1 第二波实装范围:**
- Agent A 技术面 · **全功能上线**(数据齐全)
- Agent B/C/D · **降级版**:输入空,system prompt 让 LLM 返回 `score: 0 + rationale: "M1 第二波暂未接入 X 数据源"` · 占位字段为后续保留接口
- Aggregator 算综合时 B/C/D 权重在 M1 第二波给 0,M2+ 接齐再激活

理由:**M1 第二波不堆功能,聚焦把技术面 + 缠论 + AI 卡片这条链路打通**。
M2+ 真要做基本面/消息面/链上/衍生品/舆情,还要接一堆数据源,每个都是独立大工作量。

---

## 输入数据 schema

**`apps/api/app/schemas/ai_decision.py`(新建):**

```python
class TechnicalSnapshot(BaseModel):
    """技术面快照 · DataPrepareNode 计算后传给 Agent A"""
    ma: dict[int, float]              # {5: 76234, 20: 75100, 60: 74200}
    macd: dict[str, float]            # {"dif": ..., "dea": ..., "macd": ...}
    rsi: dict[int, float]             # {14: 52.3}
    boll: dict[str, float]            # {"upper": ..., "mid": ..., "lower": ...}
    last_close: float
    trend_5d: Literal["up", "down", "sideways"]  # 简单基于 close 趋势

class AgentScore(BaseModel):
    """单 Agent 输出 · -100..100 评分 + 简短解读"""
    name: Literal["technical", "fundamental", "news", "value", "onchain", "derivatives", "sentiment"]
    score: int = Field(ge=-100, le=100)
    confidence: float = Field(ge=0.0, le=1.0)   # 自评信心度
    rationale: str = Field(max_length=200)       # 简短中文解读
    key_levels: list[float] = Field(default_factory=list, max_length=4)

class DecisionCard(BaseModel):
    """完整决策卡 · 给前端的最终响应"""
    symbol: str
    market: Market
    period: Period
    generated_at: AwareDatetime
    # 综合评分 · -100..100 · 由 AggregatorNode 算出
    composite_score: int = Field(ge=-100, le=100)
    composite_label: Literal["强多", "弱多", "中性", "弱空", "强空"]
    composite_confidence: float = Field(ge=0.0, le=1.0)
    # 各 Agent 评分明细 · 用户展开看
    agent_scores: list[AgentScore]
    # 矛盾提示 · 当 max(score) - min(score) > 80 时点亮
    contradiction: str | None = None
    # AI 生成的整体解读(LLM 文字) · 已经过 ValidatorNode 把祈使句改成陈述句
    narrative: str = Field(max_length=600)
    # 缠论买卖点引用(若有) · M1 第二波接入,buy_sell_points 字段
    chan_signals: list[ChanBuySellPoint] = Field(default_factory=list)
    # 强制 disclaimer · ValidatorNode 兜底注入
    disclaimer: str = "仅供参考,不构成投资建议"
    # 元信息(用户展开 / 调试用)
    cached: bool = False        # 这次响应是不是命中缓存
    token_usage: int = 0        # 本次调用总 token 数(cache hit 时 0)
```

`ChanBuySellPoint` 在 0011 的 ChanAnalysis 里已经预留字段,M1 第二波填充。

---

## 应用层结果缓存

### Cache Key 设计

```
ai:decision:{market}:{symbol}:{period}:{trading_day}
```

`trading_day` 计算规则:
- A 股 / 美股:`YYYY-MM-DD`(当地交易日 · 周末 / 节假日不算)
- 加密:`YYYY-MM-DD-HH` 6 小时分桶(24/7 高频波动 · 4 桶/日)· 跟 0010 数据精度章节一致

### TTL 策略

| 市场 | TTL | 失效时机 |
|---|---|---|
| A 股 | 4h | 收盘后下一交易日 9:25 前自然过期(09:15 集合竞价开始) |
| 美股 | 4h | 收盘后 next-day 9:25 ET 前过期 |
| 加密 | 1h | 6 小时分桶 + 1h TTL · 高频更新 |

**主动 invalidate(M2+,M1 第二波不做):**
- 该 (symbol, period) 收到价格异动 trigger(0009)→ 主动删 cache
- 财报 / 重大公告事件 → 主动删 cache(M2+ 接事件源)

### 命中率预期(0012 § 成本验证后)

| 用户规模 | top 标的命中率 | 月度独立 LLM 调用 |
|---|---|---|
| 100 用户 | top 20 标的覆盖 80% 流量 | ~2,400 次/月 |
| 1000 用户 | top 50 标的覆盖 80% 流量 | ~6,000 次/月 |

### 实现位置

```python
# apps/api/app/services/ai/cache.py(新建)
async def get_cached_card(...) -> DecisionCard | None
async def set_cached_card(card: DecisionCard, ttl_seconds: int) -> None
def make_cache_key(market, symbol, period, trading_day) -> str
def compute_trading_day(market, now: datetime) -> str
```

---

## LiteLLM 接入(LLM 统一层)

### 为什么用 LiteLLM 而不是直接调 DeepSeek SDK

- **将来切换模型零成本** · LiteLLM 用 OpenAI 风格统一 API,切换 DeepSeek / Claude / GPT / Gemini 只改一个 env 变量
- **统一 retry / timeout / token tracking**(LiteLLM 自带)· 不用自己写
- 支持 batch / async / streaming · M2+ 真要降级备用模型直接配
- BSL/MIT 双协议,不引入授权问题

### 配置

```python
# apps/api/app/services/ai/llm.py
from litellm import acompletion  # async completion

DEFAULT_MODEL = "deepseek/deepseek-chat"  # LiteLLM 命名 · 也可换 deepseek-reasoner

async def ainvoke(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    response_format: dict | None = None,    # {"type": "json_object"} for JSON mode
    max_tokens: int = 1024,                  # 0012 硬上限
    temperature: float = 0.3,                # 偏保守 · 减少瞎说
    timeout: float = 30.0,
) -> tuple[str, int]:                       # (content, total_tokens)
    """单次 LLM 调用 · retry 由 LiteLLM transport 层负责(铁律 P5)。"""
    resp = await acompletion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format=response_format,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        num_retries=2,                       # transport 层 retry · 不再叠加上层
    )
    return resp.choices[0].message.content, resp.usage.total_tokens
```

### env 变量

```bash
LLM_PROVIDER=deepseek          # 切换供应商时改这里
DEEPSEEK_API_KEY=sk-xxx        # 产品负责人提供(等待中)
DEEPSEEK_API_BASE=https://api.deepseek.com/v1  # 可选 · default
LLM_MONTHLY_BUDGET_CNY=200     # 软上限 · cron 任务读 token usage 累计 + 接近时邮件告警
```

**红线:** retry 只在 LiteLLM 这一层(transport 贴近的)做 · 不要在 LangGraph / API 层再叠 retry · 遵守 docs/decisions/0002 翻车 8 + CLAUDE.md 项目铁律。

---

## 缠论买卖点提取(czsc.signals)

### M1 第一波 defer 内容 · 第二波补

0011 ADR § 4 留了 `buy_sell_points: list[BuySellPoint]` 字段。M1 第二波填充:

**输出 schema:**

```python
class ChanBuySellPoint(BaseModel):
    ts: AwareDatetime
    price: float
    kind: Literal["B1", "B2", "B3", "S1", "S2", "S3"]
    # B1=一买/B2=二买/B3=三买  S1=一卖/S2=二卖/S3=三卖
    description: str         # 简短解释 · 给 hover tooltip
    chan_event: str          # czsc.signals 原始 event 名 · 给调试
```

**实现:** `apps/api/app/services/analysis/chan.py` 加新函数:

```python
def extract_buy_sell_points(c: CZSC) -> list[ChanBuySellPoint]:
    """从 czsc CZSC 实例提取一/二/三类买卖点。

    czsc.signals 模块有 cxt_first_buy_V230228 / cxt_third_sell_V230228 等约 30+ 信号,
    M1 第二波先实装 6 个核心买卖点(B1/B2/B3/S1/S2/S3)。
    """
    points: list[ChanBuySellPoint] = []
    # czsc.signals 的输出在 c.signals_pos / c.signals_seq 里
    # 具体提取逻辑跟着 czsc 0.10.x 的 API 走(实装时验证)
    return points
```

**前端渲染:** `chan-overlay.tsx` 在 zhongshus 之后、bis 之前 push 一组 `midas-fractal` overlay(复用之前注册的自定义 overlay),用不同字符标记:

| Kind | 字符 | 颜色 | 位置 |
|---|---|---|---|
| B1 | `B1` 文字 | 朱红 `#DC143C` | K 线下方 |
| B2 | `B2` | 朱红 | 下方 |
| B3 | `B3` | 朱红 | 下方 |
| S1 | `S1` | 墨绿 `#0F6E5F` | K 线上方 |
| S2 | `S2` | 墨绿 | 上方 |
| S3 | `S3` | 墨绿 | 上方 |

跟分型语义一致:买点用「涨」色,卖点用「跌」色。

---

## 视觉系统(右栏决策卡组件)

### 替换 M0 占位

`apps/web/components/workbench/watchlist-column.tsx` 底部当前是 "AI 决策卡 M1 待实装(缠论 + LLM)" 占位 ·
M1 第二波替换为真组件。

### 组件 ascii 草图

```
┌───────────────────────────────────────────────┐
│ AI 决策卡  · ⚙ 展开明细       VIRTUAL · 模拟  │  ← header 帝王金徽章
├───────────────────────────────────────────────┤
│           ╭───────╮                            │
│           │ +47  │   弱多                      │  ← 综合评分大字 · midas-red
│           ╰───────╯   置信度 72%               │
├───────────────────────────────────────────────┤
│ 关键位:  支撑 $76,200  阻力 $82,850          │  ← 等宽 JetBrains Mono
├───────────────────────────────────────────────┤
│ 分析:                                          │
│ 缠论结构显示上升笔延伸,中枢上沿突破有效。      │  ← 陈述句,无祈使
│ MACD 死叉但 RSI 未超买,短线分歧明显。          │
├───────────────────────────────────────────────┤
│ ▶ 各维度评分(展开)                            │
│   技术面 +65 / 基本面 0 / 消息面 0 / 价值面 0 │  ← B/C/D 在 M1 二波为 0
├───────────────────────────────────────────────┤
│ ⚠ 仅供参考,不构成投资建议                     │  ← 强制 disclaimer · 浅灰底
│ 上次更新:2 分钟前(缓存)                      │  ← cached 状态
└───────────────────────────────────────────────┘
```

### 颜色 token 应用(严守视觉系统)

| 元素 | token | 备注 |
|---|---|---|
| 综合评分数字 | 强多/弱多 = `bull #DC143C` · 强空/弱空 = `bear #0F6E5F` · 中性 = `ink-faint #94949C` | 跟涨跌色一致 |
| 评分背景圆 | `midas-red-glow` 半透明 | 跟工作台 watchlist 高亮一致 |
| Header 徽章 | `gold #B8860B` 描边 + 「VIRTUAL · 模拟」白底 | 复用 VirtualBadge.tsx |
| disclaimer | `ink-faint` 文字 + `cream` 底 | 不能太显眼,但必须能看见 |
| 关键位数字 | JetBrains Mono | 数据强调 |

### 失败回退状态

| 状态 | UI |
|---|---|
| 加载中 | skeleton 卡 · 「AI 思考中...」+ 帝王金 spinner |
| 整体失败 | 灰底卡 · 「暂时无法生成决策卡 · 重试」按钮 |
| 部分 Agent 失败 | 正常卡 · 失败 Agent 显示「数据暂缺」灰字 |
| 缓存命中 | 正常卡 · footer 显示「上次更新 X 分钟前(缓存)」 |
| 价格异动触发刷新 | 卡片右上角小红点 · hover 提示「价格异动,即将更新」(M2+)|

---

## disclaimer 强制嵌入(API + UI 双层兜底)

| 层 | 实现 |
|---|---|
| **API response** | Pydantic `DecisionCard.disclaimer` 字段默认 `"仅供参考,不构成投资建议"` · 不可空 |
| **ValidatorNode** | 输出 narrative 字段经 regex 检测「建议」「应该买」「快入场」等祈使词 · 命中改写为陈述句(eg.「建议买入」→「分析显示买入信号」) |
| **前端 UI** | 决策卡组件底部硬编码 `<DisclaimerStrip />` 组件 · 不依赖 API 字段(后端响应缺字段也兜底显示) |
| **导出 / 分享(M2+)** | 截图分享时叠加水印「仅供参考」+ 时间戳 |

---

## 监控(M1 第二波最小化 · M2+ 完善)

**M1 第二波必做:**
- Celery beat 每天一次写一行 token usage 累计到 `ai_usage_log` 表(market / token_count / cost_cny / call_count)
- 接近 `LLM_MONTHLY_BUDGET_CNY` 80% 时邮件告警(用现有 0009 Resend 通道)

**M2+:**
- Prometheus / Grafana(token 用量曲线 / cache 命中率 / Agent 失败率)
- 单用户每日调用上限(0012 § 硬上限)
- 异常输出归档(LLM 说出祈使句被 ValidatorNode 改写的次数 + 内容)

---

## 实装拆分 · Checkpoint Y / Z

### Checkpoint Y · AI 后端

| Sub | 范围 | 估时 |
|---|---|---|
| Y1 | 装 langgraph + litellm + pyproject.toml + mypy ignore | 30 min |
| Y2 | `services/ai/llm.py` · LiteLLM 包装 + retry transport 层 | 1h |
| Y3 | `services/ai/cache.py` · Redis cache + trading_day 计算 + TTL | 1h |
| Y4 | `services/ai/agents/` · 4 Agent system prompt 文件(A 股美股 + 加密 各 4) | 2h |
| Y5 | `services/ai/workflow.py` · LangGraph workflow + 7 节点 | 2.5h |
| Y6 | `schemas/ai_decision.py` · DecisionCard + AgentScore + ChanBuySellPoint | 30 min |
| Y7 | `services/analysis/chan.py` 加 extract_buy_sell_points + 6 核心买卖点 | 2h |
| Y8 | `api/v1/ai_decision.py` · REST `GET /api/v1/ai/decision-card` | 1h |
| Y9 | pytest · workflow 整体测试(mock LiteLLM + 验证 schema + disclaimer) | 1.5h |
| Y10 | `ai_usage_log` 表 + alembic migration + Celery beat daily 累计任务 | 1h |
| Y11 | 端到端 smoke test 三市场 · 真 DeepSeek key + 验证 token 用量 | 1h |
| Y12 | commit + tag checkpoint-y | 15 min |
| **小计** | | **~14h** |

### Checkpoint Z · AI 前端 + 信号条 + 买卖点 overlay

| Sub | 范围 | 估时 |
|---|---|---|
| Z1 | `lib/api/ai-decision.ts` + `hooks/use-ai-decision.ts` · TanStack Query | 30 min |
| Z2 | `components/workbench/ai-decision-card.tsx` · 完整决策卡组件 | 2.5h |
| Z3 | `components/workbench/signal-bar.tsx` · 顶部信号条(替换 M0 占位)| 1.5h |
| Z4 | `components/chart/chan-overlay.tsx` 加 B1-S3 买卖点 overlay 渲染 | 1.5h |
| Z5 | DecisionCardSkeleton / Error / Cached 三种状态组件 | 1h |
| Z6 | `<DisclaimerStrip />` 复用组件 · 决策卡 + 信号条都用 | 30 min |
| Z7 | playwright 截图三市场 · 决策卡 + 顶部信号条 + 买卖点 | 1h |
| Z8 | commit + tag checkpoint-z | 15 min |
| **小计** | | **~8h** |

**Y + Z 合计 ~22h**

---

## 启动前置 checklist(给产品负责人)

完成 M1-Y 缠论配色验收后,启动 Checkpoint Y 前需要:

- [ ] **产品负责人浏览器验收 m1-y 三张截图**(BTC/NVDA/600519)· 确认新配色 OK
- [ ] **产品负责人提供 `DEEPSEEK_API_KEY`** · 填到 `/Users/hans.pan/点金Midas/.env`
  的 `DEEPSEEK_API_KEY=sk-xxx` 行(当前为空)
- [ ] **产品负责人确认 ¥200/月 预算上限**(0012 § 成本估算列出)
- [ ] **产品负责人确认 M1 第二波 Agent B/C/D 降级 OK**(只上技术面 + 缠论 · 其他维度 M2+ 接齐数据源后激活)
- [ ] **产品负责人确认决策卡视觉草图**(0012 § 视觉系统 ascii 图)· 不满意当场改

满足后回复「启动 Y」即可进 Checkpoint Y。

---

## 备注

- 本估算基于 DeepSeek-V4-Flash 当前定价 · DeepSeek 历史每年降一次价(2024 → 2025 → 2026 持续下调),实际成本可能更低
- 不考虑流量突增时 DeepSeek 限速 · M2+ 真上量再做降级 / 备用 LLM 选型
- 不在本 ADR 范围:Claude / GPT 等贵价模型选型 · 0003 已锁定 DeepSeek 为主用
- **红线复述(产品负责人 2026-05-20):**
  ① AI 决策卡视觉严守 midas-red / gold · 带 VIRTUAL 徽章
  ② 决策卡里不出现「建议买入/卖出」祈使句 · 只做「分析」和「评分」
  ③ DeepSeek 账户硬上限 ¥200/月
  ④ disclaimer 「仅供参考,不构成投资建议」API + UI 双层兜底
  ⑤ M1 第二波不接 Task 7.1 首页(第三波)· 不接真实交易

---

## M1 二波降级 v2 · 单 Agent 卡片(2026-05-20 微调)

**产品负责人 2026-05-20 拍板:M1 二波 AI 决策卡只做「技术面 Agent」,卡片 UI 只显示
技术面这一个 Agent,不挂基本面 / 消息面 / 价值面占位。**

### 改动范围

| 原 0012 设计(4 Agent 卡片)| M1 二波微调(单 Agent 卡片) |
|---|---|
| LangGraph 7 节点 · 4 Agent 并行 | LangGraph **6 节点** · 1 Agent(去掉并行 fan-out)|
| Aggregator 加权 40/30/15/15 | **Aggregator 直通**:综合分 = 技术面分 · 综合 label = 技术面 label |
| `agent_scores: list[AgentScore]` 长度 4 | 长度 1 · 只含技术面 |
| 卡片 UI 展开各维度评分(4 行)| **UI 不展开** · 只展示技术面评分 + 解读 |
| 矛盾提示(max-min > 80)| **不显示**(单 Agent 无内部矛盾)|

### M1 二波 LangGraph workflow(简化版)

```
EntryNode → DataPrepareNode → 技术面 Agent → DecisionCardNode → ValidatorNode → ExitNode
                                  (单一)
```

**去掉的节点:** AggregatorNode(因为只有一个 Agent,综合 = 技术面)。
**保留的节点:** 其余 5 个不变 · Validator / Cache / disclaimer 等机制照旧。

### 卡片 UI 简化版(M1 二波)

```
┌───────────────────────────────────────────────┐
│ AI 决策卡 · 技术面分析       VIRTUAL · 模拟    │  ← header 帝王金徽章
├───────────────────────────────────────────────┤
│           ╭───────╮                            │
│           │ +47  │   弱多                      │  ← 综合 = 技术面评分
│           ╰───────╯   置信度 72%               │
├───────────────────────────────────────────────┤
│ 关键位:  支撑 $76,200  阻力 $82,850          │
├───────────────────────────────────────────────┤
│ 技术面分析:                                    │
│ 缠论结构显示上升笔延伸,中枢上沿突破有效。      │
│ MACD 死叉但 RSI 未超买,短线分歧明显。          │
├───────────────────────────────────────────────┤
│ 缠论买卖点:                                    │
│  2026-05-06 B2 二买  ¥82,850                  │  ← czsc 提取的买卖点列表
├───────────────────────────────────────────────┤
│ ⚠ 仅供参考,不构成投资建议                     │  ← 强制 disclaimer
│ 上次更新:2 分钟前(缓存)                      │
└───────────────────────────────────────────────┘
```

跟原 ascii 草图相比:
- 删除「▶ 各维度评分(展开)」一行
- header 副标题改成「· 技术面分析」明示当前只覆盖技术面
- 多加一行「缠论买卖点」总结 czsc 提取出的近期买卖点(原本只画在 K 线 overlay 上)

### 输出 schema 微调

```python
class DecisionCard(BaseModel):
    ...
    agent_scores: list[AgentScore]   # M1 二波长度恒为 1;M2 升级到 4
    contradiction: str | None = None # M1 二波永远 None;M2 启用
    ...
```

向后兼容:M2 升级到 4 Agent 时,前端组件做条件渲染 `agent_scores.length > 1 ? <Detailed /> : <Single />`,后端 schema 不动。

### 升级路径(M2 / M2+)

- **M2:** 接基本面 Agent + 数据源(财报字段)· `agent_scores.length = 2`(技术 + 基本)· AggregatorNode 重新接入做加权
- **M2+:** 接消息面 / 价值面 / 链上 / 衍生品 / 舆情 · 完整 4 Agent

### 实装拆分调整(Checkpoint Y 减少 ~2h)

| Sub | M1 二波(单 Agent)| 原 4 Agent 估时 |
|---|---|---|
| Y4 | 1 个技术面 Agent system prompt · 分市场 3 个(A 股 / 美股 / 加密)| 4 个 Agent × 2 市场组 = 8 个 |
| Y5 | 6 节点 LangGraph(不含 Aggregator 并行 fan-out)| 7 节点 |
| **总变化** | **~12h**(原 ~14h 减 ~2h) | |

### 不变的部分

- 应用层缓存 / TTL 策略 / 视觉系统 / disclaimer 双层兜底 / ValidatorNode 祈使句改写 /
  ai_usage_log / DeepSeek ¥200 月度上限 / czsc 买卖点提取 全部按原计划做。
- czsc 买卖点 6 类 B1-3 / S1-3 在 M1 二波就上线 · UI 在卡片里**多加一栏**显示近期买卖点摘要。
