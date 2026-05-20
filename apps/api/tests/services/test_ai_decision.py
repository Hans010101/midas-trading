"""AI 决策卡 workflow + 子模块 pytest · 0012 ADR M1 二波 Checkpoint Y。

覆盖范围:
  - indicators(MA / MACD / RSI / BOLL / trend_5d)
  - validator(祈使句改写 · 0012 红线 ②)
  - cache(trading_day 计算)
  - chan extract_buy_sell_points(0012 § 缠论买卖点提取)
  - workflow 端到端(mock LLM 模式 · 不需要 DEEPSEEK_API_KEY)

真实 DeepSeek 调用测试不在本文件 · 等产品负责人填 key 后另写
test_ai_decision_real.py(integration · 跑 CI 时可 skip)。
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.market import Kline
from app.services.ai import indicators as ind
from app.services.ai.cache import compute_trading_day, make_cache_key
from app.services.ai.validator import (
    has_imperative,
    rewrite_imperatives,
)
from app.services.ai.workflow import run_decision_workflow
from app.services.analysis.chan import analyze as analyze_chan


def _make_klines(n: int, seed: int = 42) -> list[Kline]:
    """合成 K 线 · 复用 chan 测试的模式。"""
    random.seed(seed)
    bars: list[Kline] = []
    price = 100.0
    base_ts = datetime(2025, 1, 1, tzinfo=UTC)
    for i in range(n):
        trend = (5.0 * (1 if (i // 30) % 2 == 0 else -1)) * (i % 30 / 30)
        noise = random.uniform(-1.5, 1.5)
        price = max(price + trend / 30 + noise, 10.0)
        h = price + random.uniform(0.3, 1.2)
        low = price - random.uniform(0.3, 1.2)
        bars.append(
            Kline(
                ts=base_ts + timedelta(days=i),
                open=price + random.uniform(-0.3, 0.3),
                high=h,
                low=low,
                close=price,
                volume=1000.0 + random.uniform(0, 500),
                amount=None,
            ),
        )
    return bars


# ===== indicators =====


def test_indicators_ma_basic():
    klines = _make_klines(200)
    ma = ind.compute_ma(klines)
    assert set(ma.keys()) == {5, 20, 60}
    assert all(v > 0 for v in ma.values())


def test_indicators_macd_returns_dif_dea_macd():
    klines = _make_klines(200)
    macd = ind.compute_macd(klines)
    assert set(macd.keys()) == {"dif", "dea", "macd"}


def test_indicators_rsi_in_range():
    klines = _make_klines(200)
    rsi = ind.compute_rsi(klines)
    val = rsi[14]
    assert 0.0 <= val <= 100.0


def test_indicators_boll_order():
    klines = _make_klines(200)
    boll = ind.compute_boll(klines)
    # 上 > 中 > 下
    assert boll["upper"] >= boll["mid"] >= boll["lower"]


def test_indicators_trend_5d():
    klines = _make_klines(200)
    trend = ind.compute_trend_5d(klines)
    assert trend in {"up", "down", "sideways"}


# ===== validator · 祈使句改写 =====


def test_validator_detects_imperative():
    text = "缠论显示买入信号,建议买入。"
    assert has_imperative(text) is True


def test_validator_rewrites_jianyi_mai_to_chen_shu():
    text = "结构良好,建议买入,目标位 120。"
    rewritten = rewrite_imperatives(text)
    assert "建议买入" not in rewritten
    # 应该改写为陈述句
    assert "买入信号" in rewritten


def test_validator_rewrites_yinggai_mai_to_keneng():
    text = "RSI 超卖,应该买入。"
    rewritten = rewrite_imperatives(text)
    assert "应该买入" not in rewritten
    assert "可能存在买入机会" in rewritten


def test_validator_rewrites_kuai_ru_chang():
    text = "突破中枢,快入场!"
    rewritten = rewrite_imperatives(text)
    assert "快入场" not in rewritten


def test_validator_idempotent():
    """rewrite 幂等 · 多次调用结果一致。"""
    text = "建议买入。建议卖出。应该加仓。"
    once = rewrite_imperatives(text)
    twice = rewrite_imperatives(once)
    assert once == twice
    assert not has_imperative(twice)


# ===== cache · trading_day 计算 =====


def test_trading_day_cn_yyyymmdd():
    """A 股 / 美股 用 YYYY-MM-DD 一日一桶。"""
    now = datetime(2026, 5, 20, 14, 30, tzinfo=UTC)
    assert compute_trading_day("cn", now) == "2026-05-20"
    assert compute_trading_day("us", now) == "2026-05-20"


def test_trading_day_crypto_6h_bucket():
    """加密 6 小时分桶 · 取整到 0/6/12/18。"""
    cases = [
        (datetime(2026, 5, 20, 1, 30, tzinfo=UTC), "2026-05-20-00"),
        (datetime(2026, 5, 20, 6, 0, tzinfo=UTC), "2026-05-20-06"),
        (datetime(2026, 5, 20, 11, 59, tzinfo=UTC), "2026-05-20-06"),
        (datetime(2026, 5, 20, 13, 30, tzinfo=UTC), "2026-05-20-12"),
        (datetime(2026, 5, 20, 23, 59, tzinfo=UTC), "2026-05-20-18"),
    ]
    for now, expected in cases:
        assert compute_trading_day("crypto", now) == expected


def test_make_cache_key_format():
    """key 形如 ai:decision:{market}:{symbol}:{period}:{trading_day}"""
    key = make_cache_key("us", "NVDA", "1d", "2026-05-20")
    assert key == "ai:decision:us:NVDA:1d:2026-05-20"


# ===== chan 买卖点提取 · 0012 § 缠论买卖点提取 =====


@pytest.mark.asyncio
async def test_chan_buy_sell_points_extracted():
    """合成 K 线跑完 chan 后,buy_sell_points 字段应该有内容(对长序列)。"""
    klines = _make_klines(300)
    result = await analyze_chan(klines, "1d", "TEST")
    # 不强求一定 > 0(合成数据可能不出特定模式),但字段必须是 list
    assert isinstance(result.buy_sell_points, list)
    # 若有 · kind 必须是 6 类之一
    valid_kinds = {"B1", "B2", "B3", "S1", "S2", "S3"}
    for p in result.buy_sell_points:
        assert p.kind in valid_kinds
        assert isinstance(p.description, str)
        assert p.ts.tzinfo is not None       # 必须 tz-aware


# ===== workflow 端到端 · mock LLM =====


@pytest.mark.asyncio
async def test_workflow_end_to_end_with_mock_llm(monkeypatch):
    """跑完整 workflow · llm.ainvoke 走 mock(deepseek_api_key 为空)。

    验证:
      - 返回 DecisionCardResponse 结构完整
      - composite_score 在 -100..100
      - composite_label 在 5 档之一
      - agent_scores 长度 1(M1 二波单 Agent · 0012 § M1 二波降级 v2)
      - disclaimer 字段强制存在
      - narrative 不含祈使句(Validator 兜底)
      - llm_mode == 'mock'
    """
    # 强制 mock 模式(即使本机 .env 有 DEEPSEEK_API_KEY 也走 mock)
    from app.core import config as config_mod
    monkeypatch.setattr(config_mod.settings, "llm_mock_mode", True)

    klines = _make_klines(200)
    card = await run_decision_workflow(
        symbol="TEST", market="us", period="1d", klines=klines,
    )

    assert card.symbol == "TEST"
    assert -100 <= card.composite_score <= 100
    assert card.composite_label in {"强多", "弱多", "中性", "弱空", "强空"}
    assert len(card.agent_scores) == 1
    assert card.agent_scores[0].name == "technical"
    assert 0.0 <= card.agent_scores[0].confidence <= 1.0
    assert card.disclaimer == "仅供参考,不构成投资建议"
    assert not has_imperative(card.narrative), (
        f"narrative 不应含祈使句,实际:{card.narrative!r}"
    )
    assert card.llm_mode == "mock"
    assert card.token_usage > 0


@pytest.mark.asyncio
async def test_workflow_validator_rewrites_imperative_in_narrative(monkeypatch):
    """Validator 在 narrative 含祈使句时改写为陈述句。"""
    from app.core import config as config_mod
    from app.services.ai import llm as llm_mod

    monkeypatch.setattr(config_mod.settings, "llm_mock_mode", True)

    # 让 mock 返回的 rationale 故意含祈使句 · 验证 Validator 接住
    fake_jsonl = (
        '{"score": 50, "confidence": 0.7, '
        '"rationale": "结构良好,建议买入,目标 120。", "key_levels": [110.0, 120.0]}'
    )
    async def fake_ainvoke(prompt, **kwargs):  # type: ignore[no-untyped-def]
        return llm_mod.LLMResponse(
            content=fake_jsonl,
            prompt_tokens=100, completion_tokens=50, total_tokens=150,
            is_mock=True,
        )
    monkeypatch.setattr(llm_mod, "ainvoke", fake_ainvoke)
    monkeypatch.setattr(
        "app.services.ai.agents.technical.ainvoke", fake_ainvoke,
    )

    klines = _make_klines(200)
    card = await run_decision_workflow(
        symbol="TEST", market="us", period="1d", klines=klines,
    )

    assert "建议买入" not in card.narrative
    assert "买入信号" in card.narrative   # 改写后包含「买入信号」
