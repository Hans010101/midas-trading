"""i18n Phase4 刀3 · en 结构诊断测试。

覆盖:en prompt 组装(三红线英文对等)/ 语言锁双层(prompt LANGUAGE LOCK + Python CJK 重试→
      仍中文则 502 不造假)/ en validator + 免责兜底 / 结论≤400 + detail≤300 长度兜底 /
      缓存 :en 分桶 / ★zh 逐字节不变回归。

★诚实标注:mock 验不了真实 DeepSeek 英文质量与串台率 —— 部署后 admin/前端真机验证点。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

import app.services.structure.workflow as wf_mod
from app.schemas.structure import StructureFactor, StructureSnapshot
from app.services.ai.language_lock import contains_cjk
from app.services.ai.llm import LLMResponse
from app.services.ai.validator import ADVISORY_DISCLAIMER_EN, has_imperative
from app.services.structure.prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_EN
from app.services.structure.workflow import _cache_key, parse_intent, run_structure_diagnosis

_TS = datetime(2026, 6, 10, 8, 0, tzinfo=UTC)


def _snapshot() -> StructureSnapshot:
    factor = StructureFactor(value={"latest": 2.1, "avg_24h": 1.8}, window="24h", asof=_TS)
    return StructureSnapshot(
        symbol="BTCUSDT", generated_at=_TS,
        account_long_short=factor, position_long_short=factor, taker_flow=factor,
        open_interest=None, funding_rate=None, basis=None, sentiment=None,
    )


def _llm_json(conclusion: str, detail: str = "Account long-short ratio 2.1 vs 24h avg 1.8.") -> str:
    return json.dumps(
        {
            "conclusion": conclusion,
            "factor_findings": [
                {"factor": "account_long_short", "state": "long-leaning",
                 "detail": detail, "window": "24h"},
            ],
            "unsupported_note": None,
        },
        ensure_ascii=False,
    )


def _patch(monkeypatch: pytest.MonkeyPatch, *, contents: list[str]) -> None:
    """mock 快照 + mock ainvoke(按调用序返回 contents · 支持重试不同返回)+ 强制 mock。"""
    calls = {"n": 0}

    async def fake_snapshot(client: Any, symbol: str) -> StructureSnapshot:  # noqa: ARG001
        return _snapshot()

    async def fake_ainvoke(prompt: str, **kwargs: Any) -> LLMResponse:  # noqa: ARG001
        idx = min(calls["n"], len(contents) - 1)
        calls["n"] += 1
        return LLMResponse(
            content=contents[idx], prompt_tokens=100, completion_tokens=80,
            total_tokens=180, is_mock=True,
        )

    monkeypatch.setattr(wf_mod, "build_structure_snapshot", fake_snapshot)
    monkeypatch.setattr(wf_mod, "ainvoke", fake_ainvoke)
    monkeypatch.setattr(wf_mod, "is_mock_mode", lambda: True)


# ===== 一 en prompt 组装(三红线英文对等)=====


def test_en_system_prompt_red_lines() -> None:
    assert "[LANGUAGE LOCK]" in SYSTEM_PROMPT_EN
    assert ADVISORY_DISCLAIMER_EN in SYSTEM_PROMPT_EN          # 英文免责固定串
    assert "Chan Theory" in SYSTEM_PROMPT_EN                    # 术语锁(来自共用前导)
    assert "description, not prediction" in SYSTEM_PROMPT_EN    # 结构红线一
    assert "window discipline" in SYSTEM_PROMPT_EN              # 结构红线二
    assert "declare gaps" in SYSTEM_PROMPT_EN                   # 结构红线三
    for key in ("conclusion", "factor_findings", "unsupported_note"):
        assert key in SYSTEM_PROMPT_EN                          # JSON 契约同中文
    assert SYSTEM_PROMPT_EN != SYSTEM_PROMPT                    # 与中文物理隔离


# ===== 二 en 诊断:happy / 串台 502 / 重试恢复 =====


@pytest.mark.asyncio
async def test_en_diagnose_happy(monkeypatch: pytest.MonkeyPatch) -> None:
    """en happy:结论英文 + 结尾英文免责固定串 + 无中文。"""
    _patch(monkeypatch, contents=[_llm_json("Longs are moderately crowded (last 24h).")])
    diag = await run_structure_diagnosis(object(), "BTCUSDT", "is long crowded", language="en")  # type: ignore[arg-type]
    assert not contains_cjk(diag.conclusion)
    assert diag.conclusion.rstrip().endswith(ADVISORY_DISCLAIMER_EN)
    assert not contains_cjk(diag.factor_findings[0].detail)


@pytest.mark.asyncio
async def test_en_diagnose_persistent_cjk_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """★en 串台:两次都返中文 → 重试后仍中文 → raise ValueError(端点 502·不产中文假诊断)。"""
    _patch(monkeypatch, contents=[_llm_json("当前多头侧结构偏拥挤(近 24h)。")])
    with pytest.raises(ValueError, match="串台|中文"):
        await run_structure_diagnosis(object(), "BTCUSDT", "is long crowded", language="en")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_en_diagnose_retry_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    """★en 首次串台(中文)→ 重试返英文 → 采用重试结果。"""
    _patch(monkeypatch, contents=[
        _llm_json("当前多头侧结构偏拥挤。"),                    # 第一次串台
        _llm_json("Longs are moderately crowded (last 24h)."),  # 重试英文
    ])
    diag = await run_structure_diagnosis(object(), "BTCUSDT", "is long crowded", language="en")  # type: ignore[arg-type]
    assert not contains_cjk(diag.conclusion)
    assert "crowded" in diag.conclusion.lower()


# ===== 三 en validator + 长度兜底 =====


@pytest.mark.asyncio
async def test_en_validator_scrubs_and_disclaims(monkeypatch: pytest.MonkeyPatch) -> None:
    """★en 红线对等:结论含祈使+营销 → 改写洗掉 + 补英文免责。"""
    _patch(monkeypatch, contents=[
        _llm_json("Longs crowded; you should sell now for guaranteed profit."),
    ])
    diag = await run_structure_diagnosis(object(), "BTCUSDT", "structure", language="en")  # type: ignore[arg-type]
    low = diag.conclusion.lower()
    assert "you should sell" not in low
    assert "guaranteed profit" not in low
    assert not has_imperative(diag.conclusion, language="en")
    assert diag.conclusion.rstrip().endswith(ADVISORY_DISCLAIMER_EN)


@pytest.mark.asyncio
async def test_en_conclusion_capped_400(monkeypatch: pytest.MonkeyPatch) -> None:
    """★finding1 同类回归:超长英文结论 + 免责兜底后仍 ≤400(否则 response_model 500)。"""
    _patch(monkeypatch, contents=[_llm_json("Longs are crowded. " * 40)])  # ~720 字
    diag = await run_structure_diagnosis(object(), "BTCUSDT", "structure", language="en")  # type: ignore[arg-type]
    assert len(diag.conclusion) <= 400
    assert diag.conclusion.rstrip().endswith(ADVISORY_DISCLAIMER_EN)


@pytest.mark.asyncio
async def test_en_detail_capped_300(monkeypatch: pytest.MonkeyPatch) -> None:
    """★detail 改写后 re-truncate ≤300(FactorFinding.detail 上限·防 response_model 500)。"""
    _patch(monkeypatch, contents=[
        _llm_json("Longs crowded.", detail="Account long-short ratio is elevated. " * 20),
    ])
    diag = await run_structure_diagnosis(object(), "BTCUSDT", "structure", language="en")  # type: ignore[arg-type]
    assert len(diag.factor_findings[0].detail) <= 300


# ===== 四 zh 零变化回归 + 缓存分桶 =====


@pytest.mark.asyncio
async def test_zh_diagnose_still_chinese(monkeypatch: pytest.MonkeyPatch) -> None:
    """★zh 零变化:zh 结论仍中文(不被 en 兜底污染)· 不追加英文免责。"""
    _patch(monkeypatch, contents=[_llm_json("当前多头侧结构偏拥挤(近 24h 口径)。")])
    diag = await run_structure_diagnosis(object(), "BTCUSDT", "多头拥挤吗", language="zh")  # type: ignore[arg-type]
    assert contains_cjk(diag.conclusion)
    assert ADVISORY_DISCLAIMER_EN not in diag.conclusion


# ===== 五 对抗验证回归(CJK 检测覆盖 factor/window · state/note 也过 scrub)=====


def _llm_json_fields(*, factor: str, state: str, window: str, note: str | None) -> str:
    return json.dumps(
        {
            "conclusion": "Longs are moderately crowded (last 24h).",
            "factor_findings": [
                {"factor": factor, "state": state, "detail": "Ratio elevated.", "window": window},
            ],
            "unsupported_note": note,
        },
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_en_diagnose_cjk_in_window_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """★对抗回归:LLM 只在 window 串台中文(其余英文)→ CJK 检测捕获 → 502(中文不漏)。"""
    bad = _llm_json_fields(factor="account_long_short", state="long-leaning",
                           window="近7天", note=None)
    _patch(monkeypatch, contents=[bad])
    with pytest.raises(ValueError, match="串台|中文"):
        await run_structure_diagnosis(object(), "BTCUSDT", "structure", language="en")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_en_diagnose_cjk_in_factor_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """★对抗回归:LLM 只在 factor 串台中文 → CJK 检测捕获 → 502。"""
    bad = _llm_json_fields(factor="账户多空比", state="long-leaning", window="24h", note=None)
    _patch(monkeypatch, contents=[bad])
    with pytest.raises(ValueError, match="串台|中文"):
        await run_structure_diagnosis(object(), "BTCUSDT", "structure", language="en")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_en_state_scrubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    """★对抗回归闭合:en state 也过营销/祈使 scrub(此前只洗 detail·绕过 state)。"""
    bad = _llm_json_fields(factor="account_long_short", state="guaranteed profit",
                           window="24h", note=None)
    _patch(monkeypatch, contents=[bad])
    diag = await run_structure_diagnosis(object(), "BTCUSDT", "structure", language="en")  # type: ignore[arg-type]
    assert "guaranteed profit" not in diag.factor_findings[0].state.lower()


@pytest.mark.asyncio
async def test_en_note_scrubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    """★对抗回归闭合:en unsupported_note 也过 scrub(此前直穿 exit·绕过 validator)。"""
    bad = _llm_json_fields(factor="account_long_short", state="long-leaning", window="24h",
                           note="Liquidation not collected; you should buy now anyway.")
    _patch(monkeypatch, contents=[bad])
    diag = await run_structure_diagnosis(object(), "BTCUSDT", "liquidation?", language="en")  # type: ignore[arg-type]
    assert "you should buy" not in (diag.unsupported_note or "").lower()


def test_structure_cache_key_language_bucket() -> None:
    """★缓存分桶(刀1 已铺·刀3 确认接上):zh 无后缀 · en 加 :en。"""
    intent = parse_intent("is long crowded")
    zh = _cache_key("BTCUSDT", intent)
    en = _cache_key("BTCUSDT", intent, "en")
    assert not zh.endswith(":en")
    assert en.endswith(":en")
    assert en == zh + ":en"
