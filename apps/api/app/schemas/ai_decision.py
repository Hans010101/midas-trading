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

    # 红线 · 强制 disclaimer · API + UI 双层兜底
    disclaimer: str = "仅供参考,不构成投资建议"

    # 元信息
    cached: bool = False
    token_usage: int = 0
    # mock 调用 / 真实调用 · 等 DEEPSEEK_API_KEY 配置后切到 "real"
    llm_mode: Literal["mock", "real"] = "mock"
