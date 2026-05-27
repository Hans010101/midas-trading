"""告警规则求值 · 0025 G2b。

取指标最新值(registry fetcher · 读 CH)→ 按算子比阈值 → 命中与否 + 当前值。
扫描 worker 据此决定是否(经 Redis 去重后)dispatch 推送。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.services.alerts.registry import get_indicator

if TYPE_CHECKING:
    from app.models.alert_rule import AlertRule
    from app.services.alerts.registry import ScanContext

# DP6 护栏:单用户最多规则数。
MAX_RULES_PER_USER = 20

_OPS = {
    "gt": lambda v, t: v > t,
    "gte": lambda v, t: v >= t,
    "lt": lambda v, t: v < t,
    "lte": lambda v, t: v <= t,
}


@dataclass(frozen=True)
class EvalResult:
    triggered: bool
    value: float | None  # None = 取不到值(无数据 / 不支持)→ 不触发


def compare(value: float, operator: str, threshold: float) -> bool:
    op = _OPS.get(operator)
    return bool(op(value, threshold)) if op else False


async def evaluate_rule(ctx: ScanContext, rule: AlertRule) -> EvalResult:
    """求值单条规则 · 取不到值返回 not-triggered(绝不抛到扫描循环)。"""
    indicator = get_indicator(rule.indicator)
    if indicator is None or rule.market not in indicator.markets:
        return EvalResult(triggered=False, value=None)
    value = await indicator.fetch(ctx, rule.market, rule.symbol, rule.timeframe)
    if value is None:
        return EvalResult(triggered=False, value=None)
    return EvalResult(
        triggered=compare(value, rule.operator, float(rule.threshold)),
        value=value,
    )
