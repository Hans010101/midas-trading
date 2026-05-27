"""告警引擎求值 pytest · 0025 G2b · compare 真值表 + evaluate_rule 流程(mock 指标)。"""

from __future__ import annotations

import pytest

from app.models.alert_rule import AlertRule
from app.services.alerts import engine
from app.services.alerts.registry import IndicatorDef


def test_compare_truth_table():
    assert engine.compare(75.0, "gt", 70.0) is True
    assert engine.compare(70.0, "gt", 70.0) is False
    assert engine.compare(70.0, "gte", 70.0) is True
    assert engine.compare(65.0, "lt", 70.0) is True
    assert engine.compare(70.0, "lte", 70.0) is True
    assert engine.compare(75.0, "lte", 70.0) is False
    assert engine.compare(1.0, "??", 0.0) is False  # 未知算子 → False


def _rule(**kw: object) -> AlertRule:
    base: dict[str, object] = {
        "market": "us", "symbol": "NVDA", "indicator": "rsi_14",
        "operator": "gt", "threshold": 70.0, "timeframe": "1d",
    }
    base.update(kw)
    return AlertRule(**base)


def _fake_indicator(value: float | None, markets: tuple[str, ...] = ("us",)) -> IndicatorDef:
    async def _fetch(_ctx: object, _m: str, _s: str | None, _tf: str | None) -> float | None:
        return value
    return IndicatorDef(
        key="rsi_14", label="RSI", category="technical", markets=markets,
        requires_symbol=True, needs_timeframe=True, fetch=_fetch,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_evaluate_rule_triggered(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(engine, "get_indicator", lambda _k: _fake_indicator(75.0))
    result = await engine.evaluate_rule(None, _rule(operator="gt", threshold=70.0))  # type: ignore[arg-type]
    assert result.triggered is True
    assert result.value == 75.0


@pytest.mark.asyncio
async def test_evaluate_rule_not_triggered(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(engine, "get_indicator", lambda _k: _fake_indicator(50.0))
    result = await engine.evaluate_rule(None, _rule(operator="gt", threshold=70.0))  # type: ignore[arg-type]
    assert result.triggered is False
    assert result.value == 50.0


@pytest.mark.asyncio
async def test_evaluate_rule_unknown_indicator(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(engine, "get_indicator", lambda _k: None)
    result = await engine.evaluate_rule(None, _rule())  # type: ignore[arg-type]
    assert result.triggered is False
    assert result.value is None


@pytest.mark.asyncio
async def test_evaluate_rule_market_mismatch(monkeypatch: pytest.MonkeyPatch):
    # 指标只支持 crypto,规则却是 us → 不触发(防错配)
    monkeypatch.setattr(
        engine, "get_indicator", lambda _k: _fake_indicator(99.0, markets=("crypto",)),
    )
    result = await engine.evaluate_rule(None, _rule(market="us"))  # type: ignore[arg-type]
    assert result.triggered is False


@pytest.mark.asyncio
async def test_evaluate_rule_no_value(monkeypatch: pytest.MonkeyPatch):
    # fetch 取不到值(无数据)→ 不触发,不抛
    monkeypatch.setattr(engine, "get_indicator", lambda _k: _fake_indicator(None))
    result = await engine.evaluate_rule(None, _rule())  # type: ignore[arg-type]
    assert result.triggered is False
    assert result.value is None
