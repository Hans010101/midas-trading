"""actionable 适配层 pytest · 0036 批次甲。

验证:决策卡观点(五档 label × 市场)→ 模拟可下单建议(direction)映射正确;
拍板④ 现货弱空/强空 = sell + 有持仓平/无持仓观望提示;hold 不出按钮;
basis/hint 不含违规营销话术;with_actionable 幂等。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.schemas.ai_decision import CompositeLabel, DecisionCardResponse
from app.schemas.market import Market
from app.services.ai.actionable import to_actionable, with_actionable
from app.services.ai.validator import has_marketing_violation


def _card(label: CompositeLabel, market: Market, score: int = 50, conf: float = 0.7) -> DecisionCardResponse:
    return DecisionCardResponse(
        symbol="X", market=market, period="1d",
        generated_at=datetime(2026, 5, 31, tzinfo=UTC),
        composite_score=score, composite_label=label, composite_confidence=conf,
        agent_scores=[], narrative="结构分析", chan_signals=[],
    )


@pytest.mark.parametrize(("label", "market", "expect_dir", "expect_act"), [
    ("强多", "us", "buy", True),
    ("弱多", "cn", "buy", True),
    ("中性", "us", "hold", False),
    ("弱空", "us", "sell", True),
    ("强空", "cn", "sell", True),
    ("强多", "crypto", "open_long", True),
    ("弱多", "crypto", "open_long", True),
    ("强空", "crypto", "open_short", True),
    ("中性", "crypto", "hold", False),
])
def test_to_actionable_direction(
    label: CompositeLabel, market: Market, expect_dir: str, expect_act: bool,
) -> None:
    adv = to_actionable(_card(label, market))
    assert adv.direction == expect_dir
    assert adv.actionable is expect_act
    assert label in adv.basis  # basis 含 label


def test_spot_bearish_hint_close_or_watch() -> None:
    """拍板④:现货弱空/强空 → sell + 提示有持仓平、无持仓观望。"""
    adv = to_actionable(_card("强空", "us"))
    assert adv.direction == "sell"
    assert "持有" in adv.hint
    assert "观望" in adv.hint


def test_hold_not_actionable() -> None:
    adv = to_actionable(_card("中性", "crypto"))
    assert adv.direction == "hold"
    assert adv.actionable is False


def test_basis_hint_no_marketing_violation() -> None:
    """★红线:模板化 basis/hint 不含违规营销话术。"""
    labels: list[CompositeLabel] = ["强多", "弱多", "中性", "弱空", "强空"]
    markets: list[Market] = ["cn", "us", "crypto"]
    for label in labels:
        for market in markets:
            adv = to_actionable(_card(label, market))
            assert not has_marketing_violation(adv.basis)
            assert not has_marketing_violation(adv.hint)
    # disclaimer 始终在
    assert to_actionable(_card("强多", "us")).disclaimer == ""


def test_with_actionable_attaches_and_idempotent() -> None:
    card = _card("强多", "us")
    assert card.actionable is None
    card2 = with_actionable(card)
    assert card2.actionable is not None
    assert card2.actionable.direction == "buy"
    # 幂等 · 重算覆盖结果一致
    card3 = with_actionable(card2)
    assert card3.actionable is not None
    assert card3.actionable.direction == "buy"
