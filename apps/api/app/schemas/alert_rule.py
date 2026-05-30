"""告警规则 Pydantic 契约 · 0025 G2b。

指标 key / 算子 / 适用市场 / 是否需 symbol 的合法性由 services/alerts/registry
在路由层校验(本 schema 只做基础类型/长度约束)。
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Operator = Literal["gt", "gte", "lt", "lte"]
RuleMarket = Literal["cn", "us", "crypto", "hk"]


class AlertRuleCreate(BaseModel):
    """POST /alert-rules 入参。"""

    model_config = ConfigDict(extra="forbid")

    market: RuleMarket
    # 市场级指标(如恐贪 / 涨跌家数)可不传;per-symbol 指标必传(路由按 registry 校验)
    symbol: str | None = Field(default=None, max_length=64)
    indicator: str = Field(min_length=1, max_length=48)
    operator: Operator
    threshold: float
    timeframe: str | None = Field(default=None, max_length=8)
    cooldown_sec: int = Field(default=300, ge=60, le=86_400)


class AlertRuleUpdate(BaseModel):
    """PATCH /alert-rules/{id} 入参 · 部分更新(None = 不动)。"""

    model_config = ConfigDict(extra="forbid")

    operator: Operator | None = None
    threshold: float | None = None
    timeframe: str | None = Field(default=None, max_length=8)
    enabled: bool | None = None
    cooldown_sec: int | None = Field(default=None, ge=60, le=86_400)


class AlertRuleResponse(BaseModel):
    """告警规则响应体。"""

    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    id: int
    market: str
    symbol: str | None
    indicator: str
    operator: str
    threshold: float
    timeframe: str | None
    enabled: bool
    cooldown_sec: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class IndicatorMeta(BaseModel):
    """GET /alert-rules/indicators 单条 · 供前端 / bot 渲染可选指标清单。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    label: str
    category: str
    markets: list[str]
    requires_symbol: bool
    needs_timeframe: bool
    unit: str | None = None


def to_response(rule) -> AlertRuleResponse:  # type: ignore[no-untyped-def]
    return AlertRuleResponse.model_validate(rule)


__all__ = [
    "AlertRuleCreate",
    "AlertRuleResponse",
    "AlertRuleUpdate",
    "IndicatorMeta",
    "Operator",
    "RuleMarket",
    "to_response",
]
