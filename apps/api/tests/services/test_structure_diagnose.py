"""结构诊断 workflow 单测 · mock LLM + mock 快照(零真实 CH/Redis/LLM · 本地可跑)。

覆盖:意图归一 · 五节点走通出 StructureDiagnosis 形状 · prompt 三红线锁字(防后续误改弱化)·
validator 祈使句改写复用 · LLM 坏输出明确 raise(不产假诊断)。
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

import app.services.structure.workflow as wf_mod
from app.schemas.structure import StructureFactor, StructureSnapshot
from app.services.ai.llm import LLMResponse
from app.services.ai.validator import has_imperative
from app.services.structure.prompts import SYSTEM_PROMPT
from app.services.structure.workflow import parse_intent, run_structure_diagnosis

_TS = datetime(2026, 6, 10, 8, 0, tzinfo=UTC)


def _snapshot() -> StructureSnapshot:
    factor = StructureFactor(value={"latest": 2.1, "avg_24h": 1.8}, window="24h", asof=_TS)
    return StructureSnapshot(
        symbol="BTCUSDT", generated_at=_TS,
        account_long_short=factor, position_long_short=factor, taker_flow=factor,
        open_interest=None, funding_rate=None, basis=None, sentiment=None,
    )


def _llm_json(conclusion: str) -> str:
    return json.dumps(
        {
            "conclusion": conclusion,
            "factor_findings": [
                {
                    "factor": "account_long_short",
                    "state": "偏多拥挤",
                    "detail": "大户账户多空比最新 2.1,高于近 24h 均值 1.8。",
                    "window": "24h",
                },
            ],
            "unsupported_note": None,
        },
        ensure_ascii=False,
    )


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch, *, llm_content: str,
) -> None:
    """mock 快照 + mock ainvoke + 强制 mock 模式(跳过 log_usage 落库)。"""

    async def fake_snapshot(client: Any, symbol: str) -> StructureSnapshot:  # noqa: ARG001
        return _snapshot()

    async def fake_ainvoke(prompt: str, **kwargs: Any) -> LLMResponse:  # noqa: ARG001
        return LLMResponse(
            content=llm_content, prompt_tokens=100, completion_tokens=80,
            total_tokens=180, is_mock=True,
        )

    monkeypatch.setattr(wf_mod, "build_structure_snapshot", fake_snapshot)
    monkeypatch.setattr(wf_mod, "ainvoke", fake_ainvoke)
    monkeypatch.setattr(wf_mod, "is_mock_mode", lambda: True)


# ── 意图归一 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("BTC 现在多头是不是太拥挤", "long_crowding"),
        ("空头会不会被挤爆", "short_crowding"),
        ("杠杆是不是堆太高了", "leverage_buildup"),
        ("最近 OI 涨得猛吗", "leverage_buildup"),
        ("资金费率现在极端吗", "funding_extreme"),
        ("现在市场结构怎么样", "overall"),
        ("做空的人多吗", "short_crowding"),
    ],
)
def test_parse_intent(question: str, expected: str) -> None:
    assert parse_intent(question) == expected


# ── workflow 五节点走通 + 输出形状 ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_workflow_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pipeline(monkeypatch, llm_content=_llm_json("当前多头侧结构偏拥挤(近 24h 口径)。"))
    diag = await run_structure_diagnosis(object(), "btc/usdt", "BTC 现在多头是不是太拥挤")

    assert diag.intent == "long_crowding"
    assert "拥挤" in diag.conclusion
    assert len(diag.factor_findings) == 1
    assert diag.factor_findings[0].factor == "account_long_short"
    assert diag.factor_findings[0].window == "24h"  # 口径随行(红线②)
    assert diag.unsupported_note is None
    assert diag.snapshot.symbol == "BTCUSDT"  # 快照随诊断返回(下钻用)


# ── prompt 三红线锁字(防后续误改弱化)─────────────────────────────────────────


def test_prompt_red_lines_locked() -> None:
    # 红线① 非预测
    assert "禁止价格预测" in SYSTEM_PROMPT
    assert "点位" in SYSTEM_PROMPT
    assert "目标价" in SYSTEM_PROMPT
    assert "买入/卖出" in SYSTEM_PROMPT
    # 红线② 口径限定
    assert "数据窗口" in SYSTEM_PROMPT
    assert "近 N 天内" in SYSTEM_PROMPT
    assert "60 天" in SYSTEM_PROMPT
    # 红线③ 缺失明示
    assert "清算数据" in SYSTEM_PROMPT
    assert "盘口深度" in SYSTEM_PROMPT
    assert "未采集" in SYSTEM_PROMPT
    assert "暂不支持该维度" in SYSTEM_PROMPT


# ── validator 复用(祈使句改写)──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validator_rewrites_imperative(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = "建议立即买入,多头结构强劲。"
    assert has_imperative(raw)  # guard:样例确实触发词表(validator.py 词表首条)
    _patch_pipeline(monkeypatch, llm_content=_llm_json(raw))

    diag = await run_structure_diagnosis(object(), "BTCUSDT", "现在市场结构怎么样")
    assert not has_imperative(diag.conclusion)  # 已被改写
    assert "建议立即买入" not in diag.conclusion
    assert "买入信号" in diag.conclusion  # 词表改写产物(陈述句)


# ── LLM 坏输出 → 明确 raise(不产假诊断 · 不污染缓存)──────────────────────────


@pytest.mark.asyncio
async def test_bad_llm_output_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pipeline(monkeypatch, llm_content="这不是 JSON")
    with pytest.raises(ValueError, match="解析失败"):
        await run_structure_diagnosis(object(), "BTCUSDT", "现在市场结构怎么样")
