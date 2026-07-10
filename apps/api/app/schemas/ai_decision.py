"""AI 决策卡 Pydantic 契约 · 0012 ADR § 输入数据 schema。

M1 第二波单 Agent 卡片(0012 § M1 二波降级 v2):
  - agent_scores 长度恒为 1(只含技术面)
  - contradiction 永远 None
  - composite_score = technical_score 直通

M2 升级到 4 Agent 时:
  - agent_scores 长度 4
  - Aggregator 加权 40/30/15/15
  - contradiction 启用
  - schema 不变 · 前端 conditional render
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.market import Market, Period

# ===== 技术快照(DataPrepareNode → Agent A 输入)=====


class TechnicalSnapshot(BaseModel):
    """技术面快照 · 喂给技术面 Agent 的所有结构化数据。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    last_close: float
    last_ts: AwareDatetime
    ma: dict[int, float]                  # {5: ..., 20: ..., 60: ...}
    macd: dict[str, float]                # {"dif": ..., "dea": ..., "macd": ...}
    rsi: dict[int, float]                 # {14: 52.3}
    boll: dict[str, float]                # {"upper": ..., "mid": ..., "lower": ...}
    trend_5d: Literal["up", "down", "sideways"]
    # 缠论结构摘要(从 chan service 拿)
    chan_bi_count: int
    chan_last_bi_direction: Literal["up", "down"] | None
    chan_zhongshu_count: int
    chan_recent_buy_sell_points: list[dict[str, object]]
    # 三价位算价素材(交易计划参考)· 带默认值保证旧调用/测试兼容
    atr: float = 0.0                       # ATR(14) · 止损缓冲用(compute_atr 注入)
    zhongshu_high: float | None = None     # 最近中枢上沿(无中枢→None)
    zhongshu_low: float | None = None      # 最近中枢下沿
    # 事件日程层 P0:预格式化「未来7天重大事件」prompt 段(econ_calendar.format 产出 ·
    # 自带红线尾句「仅风险背景·绝不给方向」)· 空串=无事件=prompt 零变化 · 默认值保旧兼容
    econ_events_context: str = ""


# ===== Agent 输出 =====


class AgentScore(BaseModel):
    """单 Agent 评分 · -100..100。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: Literal[
        "technical", "fundamental", "news", "value",
        "onchain", "derivatives", "sentiment",
    ]
    score: int = Field(ge=-100, le=100)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(max_length=400)
    key_levels: list[float] = Field(default_factory=list, max_length=4)


# ===== 缠论买卖点 =====


class ChanBuySellPoint(BaseModel):
    """缠论买卖点 · czsc 提取的 1/2/3 类买卖点。

    M1 二波 0012 § 缠论买卖点提取 落地。
    """
    model_config = ConfigDict(extra="forbid", frozen=True)

    ts: AwareDatetime
    price: float
    kind: Literal["B1", "B2", "B3", "S1", "S2", "S3"]
    description: str = Field(max_length=120)


# ===== 决策卡完整响应 =====


CompositeLabel = Literal["强多", "弱多", "中性", "弱空", "强空"]


# ===== 可下单建议(0036 批次甲 · actionable 适配层 · 纯派生自结构化字段)=====


ActionableDirection = Literal[
    "buy", "sell", "hold", "open_long", "open_short", "close",
]


class ActionableAdvice(BaseModel):
    """AI 观点 → 模拟可下单建议 · 纯派生自决策卡结构化字段(不调 LLM · 不改 AI 管线)。

    ★ 红线:仅【模拟】参考。direction 只是建议方向;真要下单仍走虚拟撮合引擎 + 二次确认
,绝不接真实交易。现货 sell 见拍板④(有持仓建议平 / 无持仓建议观望)。
    拍板③:仓位第一层固定走用户下单预设(size_note 给口径 · 不含具体数额)。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction: ActionableDirection
    actionable: bool                          # direction != hold(前端是否出「一键模拟下单」)
    basis: str = Field(max_length=120)        # 模板化依据(派生自 label / 评分 / 置信)
    size_note: str = Field(max_length=60)     # 仓位口径(拍板③ · 固定下单预设)
    hint: str = Field(max_length=160)         # 操作提示(模拟语境)
    disclaimer: str = ""


# ===== 交易计划参考(三价位纯规则算 + AI 解释)=====


PlanDirection = Literal["long", "short", "neutral"]


class TradingPlan(BaseModel):
    """交易计划参考 · 入场区间/止损失效价/双目标/盈亏比 = 后端【纯规则】计算(非 LLM 生成数字)·
    plan_note = AI 写的"为什么这么定"解释(复用 rationale 机制 · mock/失败走规则模板)。

    ★ 仅【模拟】参考 · 真下单走虚拟撮合 + 二次确认。第一版止损 = 纯结构失效价,不做爆仓校验
      (无杠杆上下文 · 留待后续"仓位/杠杆建议"阶段)。中性方向三价位全 None(前端优雅降级)。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction: PlanDirection
    entry_low: float | None = None
    entry_high: float | None = None
    stop: float | None = None                 # 失效价(结构失效位 ∓ N×ATR)
    target1: float | None = None
    target2: float | None = None
    risk_reward: float | None = None          # |(target1 - entry) / (entry - stop)|
    plan_note: str = Field(default="", max_length=400)


class DecisionCardResponse(BaseModel):
    """GET /api/v1/analysis/decision-card 响应。

    M1 二波单 Agent · agent_scores 长度恒 1 · contradiction 永远 None。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1)
    market: Market
    period: Period
    generated_at: AwareDatetime

    # 综合评分(M1 二波 = 技术面分)
    composite_score: int = Field(ge=-100, le=100)
    composite_label: CompositeLabel
    composite_confidence: float = Field(ge=0.0, le=1.0)

    # Agent 评分明细(M1 二波长度 1)
    agent_scores: list[AgentScore]

    # 矛盾提示(M1 二波永远 None;M2 启用)
    contradiction: str | None = None

    # AI 生成的整体解读(过 ValidatorNode 改写)
    narrative: str = Field(max_length=1000)

    # 缠论近期买卖点摘要
    chan_signals: list[ChanBuySellPoint] = Field(default_factory=list)

    # 可下单建议(0036 批次甲)· 由 actionable 适配层在 API 层派生填充(workflow 不设 · 不改 AI 管线)
    actionable: ActionableAdvice | None = None

    # 交易计划参考 · workflow 产出(三价位规则算 + plan_note)· 前端两卡共用 · 中性/非 Pro 可为 None
    trading_plan: TradingPlan | None = None

    # ★事件日程层 P0 · 近期重大事件风险提示 · API 层【纯模板】派生(econ_calendar.format ·
    #   零 LLM=红线机器可证:只陈述事件+波动放大提示,绝无方向词)· 尾带完整免责 · 无事件=None
    event_risk: str | None = None

    # disclaimer 字段保留(API 契约不破)· 产品决策置空(平台层已说明全程虚拟)
    disclaimer: str = ""

    # 元信息
    cached: bool = False
    token_usage: int = 0
    # mock 调用 / 真实调用 · 等 DEEPSEEK_API_KEY 配置后切到 "real"
    llm_mode: Literal["mock", "real"] = "mock"

    # ★ Pro 门控:True = 非 Pro(未登录/免费)· 此时上方决策字段全为空壳(无真实内容 · 防 F12)·
    #   前端据此 + 登录态出遮罩(未登录→注册墙 / 免费→付费墙)。
    locked: bool = False
