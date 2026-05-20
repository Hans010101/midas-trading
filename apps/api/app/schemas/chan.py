"""缠论分析 Pydantic 契约 · 0011 ADR § 2。"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.market import Market, Period


class FractalPointResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ts: AwareDatetime
    price: float
    kind: Literal["G", "D"]  # G=顶分型, D=底分型


class BiResponse(BaseModel):
    """笔 · 0011 § 2"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    start_ts: AwareDatetime
    end_ts: AwareDatetime
    start_price: float
    end_price: float
    direction: Literal["up", "down"]
    high: float
    low: float
    power: float
    length: int


class ZhongshuResponse(BaseModel):
    """中枢(简化版 · M1 第一波)"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    start_ts: AwareDatetime
    end_ts: AwareDatetime
    high: float
    low: float


class ChanAnalysisResponse(BaseModel):
    """缠论分析综合响应 · GET /api/v1/analysis/chan"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1)
    market: Market
    period: Period
    bar_count: int
    fractals: list[FractalPointResponse]
    bis: list[BiResponse]
    zhongshus: list[ZhongshuResponse]
    # M1 第二波填充 · 当前固定空列表
    buy_sell_points: list[dict[str, object]] = Field(default_factory=list)
    # 红线 · 缠论 / AI 输出必带
    disclaimer: str = "仅供参考,不构成投资建议"
