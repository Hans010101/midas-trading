"""Prompt 红线机器证明 · 纯导入 + 字符串断言 + spy/never(无 DB/网络 · 本地可跑)。

★ 红线:prompt 是锁死模块。本测试钉死:
  ① 既有技术面 prompt 的约束未被本次改动破坏(禁祈使句 / crypto 资金费率 M2+ 声明);
  ② 新增 plan_note prompt 也守同款约束(禁祈使句 / 不生成价格数字 / 不注入资金费率);
  ③ spy/never:mock 模式下 plan_note 绝不调用 LLM(走规则模板 · 不烧 token)。
"""

from __future__ import annotations

import pytest

from app.schemas.ai_decision import TradingPlan
from app.services.ai.agents import plan_note as plan_note_mod
from app.services.ai.agents.plan_note import PLAN_NOTE_SYSTEM
from app.services.ai.agents.technical import (
    _SYSTEM_BASE,
    _SYSTEM_CRYPTO,
    _system_prompt,
)

# 五个禁用祈使句(0012 红线 ②)· 既有 + 新 prompt 都必须明令禁止
_FORBIDDEN_IMPERATIVES = ("建议买入", "建议卖出", "应该买", "快入场")


# ===== ① 既有技术面 prompt 约束未破 =====


def test_base_prompt_forbids_imperatives():
    assert "绝对不能出现" in _SYSTEM_BASE
    for bad in _FORBIDDEN_IMPERATIVES:
        assert bad in _SYSTEM_BASE  # 四个禁用祈使句明文列出


def test_base_prompt_structured_fields_intact():
    for field in ("score", "confidence", "rationale", "key_levels"):
        assert field in _SYSTEM_BASE


def test_crypto_prompt_funding_is_m2_declared():
    """crypto:资金费率/链上数据 M2+ 才接的声明必须在(没被本次改动删掉)。"""
    assert "资金费率" in _SYSTEM_CRYPTO
    assert "M2+" in _SYSTEM_CRYPTO


def test_market_prompts_distinct():
    cn, us, crypto, hk = (_system_prompt(m) for m in ("cn", "us", "crypto", "hk"))
    assert len({cn, us, crypto, hk}) == 4
    assert "A 股" in cn
    assert "美股" in us
    assert "加密" in crypto
    assert "港股" in hk


# ===== ② 新增 plan_note prompt 守同款红线 =====


def test_plan_note_prompt_forbids_imperatives():
    assert "绝对不能出现" in PLAN_NOTE_SYSTEM
    for bad in _FORBIDDEN_IMPERATIVES:
        assert bad in PLAN_NOTE_SYSTEM


def test_plan_note_prompt_forbids_generating_numbers():
    """★ 核心红线:LLM 只解释、不生成/改价格数字。"""
    assert "不能修改或新增任何价格数字" in PLAN_NOTE_SYSTEM


def test_plan_note_prompt_no_funding_injection():
    """plan_note 不注入资金费率/链上(与 crypto M2+ 声明一致)。"""
    assert "不要提及资金费率" in PLAN_NOTE_SYSTEM


# ===== ③ spy/never:mock 模式 plan_note 绝不调 LLM =====


@pytest.mark.asyncio
async def test_plan_note_never_calls_llm_in_mock(monkeypatch: pytest.MonkeyPatch):
    """mock 模式:generate_plan_note 走规则模板,绝不调 ainvoke(spy 计数=0)。"""
    monkeypatch.setattr(plan_note_mod, "is_mock_mode", lambda: True)

    calls = {"n": 0}

    async def _spy(*_a: object, **_k: object) -> object:  # pragma: no cover
        calls["n"] += 1
        raise AssertionError("mock 模式不应调用 LLM")

    monkeypatch.setattr(plan_note_mod, "ainvoke", _spy)

    plan = TradingPlan(
        direction="long", entry_low=0.080, entry_high=0.083,
        stop=0.072, target1=0.092, target2=0.099, risk_reward=2.0,
    )
    note, tokens = await plan_note_mod.generate_plan_note(plan, "crypto")
    assert calls["n"] == 0          # ★ 从未调用 LLM
    assert tokens == 0
    assert "0.08" in note           # 模板含真实价位
