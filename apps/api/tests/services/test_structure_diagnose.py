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
from app.services.structure.workflow import (
    NoFactorDataError,
    parse_intent,
    run_structure_diagnosis,
)

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
    # 红线③ 缺失明示(清算仍未采 · 盘口深度二批已采:移出未采集 + 加因子口径)
    assert "清算数据" in SYSTEM_PROMPT
    assert "未采集" in SYSTEM_PROMPT
    assert "暂不支持该维度" in SYSTEM_PROMPT
    # ★ 盘口深度已从「未采集」名单移除(旧 未采集-列表措辞消失,逐字核只动盘口不碰清算)
    assert "盘口深度(orderbook depth)" not in SYSTEM_PROMPT
    # ★ 盘口深度现为已采因子:spread/imbalance 口径 + 诚实提示(瞬时切片/易操纵)进 prompt
    assert "spread" in SYSTEM_PROMPT
    assert "imbalance" in SYSTEM_PROMPT
    assert "瞬时切片" in SYSTEM_PROMPT
    assert "操纵" in SYSTEM_PROMPT


# ── prompt 专业化指令锁字(v1.1 · 防被改回罗列式)────────────────────────────


def test_prompt_professional_instructions_locked() -> None:
    # (a) 因子关系
    assert "背离" in SYSTEM_PROMPT
    assert "共振" in SYSTEM_PROMPT
    assert "孤立罗列" in SYSTEM_PROMPT
    # (b) 结构定性
    assert "结构类型" in SYSTEM_PROMPT
    # (c) 触发条件 = 可观察因子变化 · 仍非预测
    assert "可观察的因子变化" in SYSTEM_PROMPT
    assert "触发条件(非预测)" in SYSTEM_PROMPT
    # (d) 诚实不确定性 · 禁安全废话
    assert "不装确定" in SYSTEM_PROMPT
    assert "无信息增量的安全话术" in SYSTEM_PROMPT


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


# ── 友好闸:合约因子全 null → 不进 LLM(省成本 · symbol 模糊输入刀)────────────


@pytest.mark.asyncio
async def test_no_factor_data_skips_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """6 合约因子全 null(如无效 symbol / 非 USDT 永续)→ NoFactorDataError 且 ainvoke 零调用。"""
    sentiment_only = StructureSnapshot(
        symbol="XYZUSDT", generated_at=_TS,
        account_long_short=None, position_long_short=None, taker_flow=None,
        open_interest=None, funding_rate=None, basis=None,
        # sentiment 是全局因子(不吃 symbol)· 正是 Hans 实证 "eth" 只剩 FGI 的形态
        sentiment=StructureFactor(value={"fear_greed": 30.0}, window="latest", asof=_TS),
    )
    calls = {"n": 0}

    async def fake_snapshot(client: Any, symbol: str) -> StructureSnapshot:  # noqa: ARG001
        return sentiment_only

    async def counting_ainvoke(prompt: str, **kwargs: Any) -> LLMResponse:  # noqa: ARG001
        calls["n"] += 1
        return LLMResponse(content="{}", prompt_tokens=0, completion_tokens=0,
                           total_tokens=0, is_mock=True)

    monkeypatch.setattr(wf_mod, "build_structure_snapshot", fake_snapshot)
    monkeypatch.setattr(wf_mod, "ainvoke", counting_ainvoke)
    monkeypatch.setattr(wf_mod, "is_mock_mode", lambda: True)

    with pytest.raises(NoFactorDataError, match="XYZUSDT"):
        await run_structure_diagnosis(object(), "xyz", "结构怎么样")
    assert calls["n"] == 0  # ★ 没进 LLM 节点 = 零成本


# ── LLM 坏输出 → 明确 raise(不产假诊断 · 不污染缓存)──────────────────────────


@pytest.mark.asyncio
async def test_bad_llm_output_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pipeline(monkeypatch, llm_content="这不是 JSON")
    with pytest.raises(ValueError, match="解析失败"):
        await run_structure_diagnosis(object(), "BTCUSDT", "现在市场结构怎么样")
