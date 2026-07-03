"""i18n Phase4 刀2 · 英文决策卡测试。

覆盖:en prompt 组装(4 市场)/ 语言锁双层(prompt LANGUAGE LOCK + Python CJK 重试/降级)/
      en validator 挂接 + 免责兜底 / 缓存分桶 key / ★zh 逐字节不变回归。

★诚实标注:mock 验不了【真实 DeepSeek 英文质量与串台率】—— 那是部署后 admin / 前端真机
  验证点。这里验的是【接线正确性】:prompt 选对、语言锁逻辑、validator 挂接、缓存 key、zh 不变。
  ★mock 天然模拟串台:_mock_invoke 恒返回中文 narrative,en 路径必触发 CJK 检测 → 降级英文兜底,
   正好端到端验语言锁第二层。
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.ai_decision import TechnicalSnapshot, TradingPlan
from app.schemas.market import Kline, Market
from app.services.ai import llm as llm_mod
from app.services.ai.agents import plan_note as plan_note_mod
from app.services.ai.agents import technical as technical_mod
from app.services.ai.agents.plan_note import _finalize_note_en, generate_plan_note
from app.services.ai.agents.technical import (
    _SYSTEM_CN,
    _SYSTEM_CRYPTO,
    _SYSTEM_HK,
    _SYSTEM_US,
    _system_prompt,
    analyze_technical,
)
from app.services.ai.cache import make_cache_key
from app.services.ai.language_lock import contains_cjk
from app.services.ai.prompts_en import TECHNICAL_SYSTEM_EN
from app.services.ai.trading_plan import template_note, template_note_en
from app.services.ai.validator import ADVISORY_DISCLAIMER_EN, has_imperative
from app.services.ai.workflow import run_decision_workflow

_MARKETS: list[Market] = ["cn", "us", "hk", "crypto"]


def _make_snapshot() -> TechnicalSnapshot:
    return TechnicalSnapshot(
        last_close=100.0,
        last_ts=datetime(2025, 1, 1, tzinfo=UTC),
        ma={5: 101.0, 20: 99.0, 60: 95.0},
        macd={"dif": 0.5, "dea": 0.3, "macd": 0.4},
        rsi={14: 55.0},
        boll={"upper": 110.0, "mid": 100.0, "lower": 90.0},
        trend_5d="up",
        chan_bi_count=8,
        chan_last_bi_direction="up",
        chan_zhongshu_count=2,
        chan_recent_buy_sell_points=[],
        atr=2.0,
        zhongshu_high=105.0,
        zhongshu_low=95.0,
    )


def _make_plan() -> TradingPlan:
    return TradingPlan(
        direction="long", entry_low=98.0, entry_high=100.0, stop=94.0,
        target1=108.0, target2=116.0, risk_reward=2.0,
    )


def _make_klines(n: int, seed: int = 42) -> list[Kline]:
    random.seed(seed)
    bars: list[Kline] = []
    price = 100.0
    base_ts = datetime(2025, 1, 1, tzinfo=UTC)
    for i in range(n):
        trend = (5.0 * (1 if (i // 30) % 2 == 0 else -1)) * (i % 30 / 30)
        price = max(price + trend / 30 + random.uniform(-1.5, 1.5), 10.0)
        bars.append(
            Kline(
                ts=base_ts + timedelta(days=i),
                open=price, high=price + 1.0, low=price - 1.0, close=price,
                volume=1000.0, amount=None,
            ),
        )
    return bars


def _resp(content: str) -> llm_mod.LLMResponse:
    return llm_mod.LLMResponse(
        content=content, prompt_tokens=50, completion_tokens=50, total_tokens=100, is_mock=True,
    )


# ===== 一 en prompt 组装(4 市场)=====


@pytest.mark.parametrize("market", _MARKETS)
def test_en_system_prompt_has_red_lines(market: Market) -> None:
    """en system prompt = TECHNICAL_SYSTEM_EN · 含语言锁 + 免责固定串 + 术语锁 + JSON 契约。"""
    p = _system_prompt(market, "en")
    assert p == TECHNICAL_SYSTEM_EN[market]
    assert "[LANGUAGE LOCK]" in p
    assert ADVISORY_DISCLAIMER_EN in p          # 英文免责固定串(与 validator/landing 统一)
    assert "Chan Theory" in p                    # 术语锁
    assert "Central Hub" in p
    # JSON 契约与中文一致(_parse_response 无需区分语言)
    for key in ("score", "confidence", "rationale", "key_levels"):
        assert key in p


def test_en_system_prompt_market_context() -> None:
    """4 市场只在市场语境句不同(涨跌停/T+1/funding 等)。"""
    assert "A-shares" in TECHNICAL_SYSTEM_EN["cn"]
    assert "US stocks" in TECHNICAL_SYSTEM_EN["us"]
    assert "HK stocks" in TECHNICAL_SYSTEM_EN["hk"]
    assert "perpetuals" in TECHNICAL_SYSTEM_EN["crypto"]


@pytest.mark.parametrize(
    ("market", "zh_const"),
    [("cn", _SYSTEM_CN), ("us", _SYSTEM_US), ("crypto", _SYSTEM_CRYPTO), ("hk", _SYSTEM_HK)],
)
def test_zh_system_prompt_byte_identical(market: Market, zh_const: str) -> None:
    """★zh 零变化:默认 language 命中的永远是逐字节相同的现有中文常量。"""
    assert _system_prompt(market) == zh_const
    assert _system_prompt(market, "zh") == zh_const


# ===== 二 语言锁第二层(CJK 检测)=====


def test_contains_cjk() -> None:
    assert contains_cjk("上升趋势") is True
    assert contains_cjk("golden cross 金叉") is True         # 混中文
    assert contains_cjk("结构未给出。") is True               # 含中文标点
    assert contains_cjk("Strong long. MA aligned.") is False
    assert contains_cjk("") is False


# ===== 三 en 技术卡:mock 串台 → 降级英文兜底(4 市场各一)=====


@pytest.mark.asyncio
@pytest.mark.parametrize("market", _MARKETS)
async def test_en_technical_mock_degrades_to_english(market: Market, monkeypatch) -> None:
    """mock 恒返中文 rationale(模拟串台)· en 路径 CJK 检测 → 重试仍中文 → 降级英文兜底。"""
    from app.core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "llm_mock_mode", True)
    score, *_ = await analyze_technical(_make_snapshot(), market, language="en")
    assert not contains_cjk(score.rationale), f"英文用户不应见中文:{score.rationale!r}"
    assert "Composite technical read" in score.rationale   # 降级兜底文案
    assert -100 <= score.score <= 100


@pytest.mark.asyncio
async def test_en_technical_happy_path_no_degrade(monkeypatch) -> None:
    """LLM 直接返英文 JSON → 不触发降级,rationale = LLM 英文内容。"""
    en_json = (
        '{"score": 45, "confidence": 0.7, '
        '"rationale": "MA aligned bullish, MACD golden cross forming. Worth watching.", '
        '"key_levels": [98.0, 110.0]}'
    )

    async def fake(prompt, **kwargs):  # noqa: ARG001
        return _resp(en_json)

    monkeypatch.setattr(technical_mod, "ainvoke", fake)
    score, *_ = await analyze_technical(_make_snapshot(), "us", language="en")
    assert "golden cross" in score.rationale
    assert "Composite technical read" not in score.rationale   # 未走降级
    assert not contains_cjk(score.rationale)


@pytest.mark.asyncio
async def test_en_technical_retry_recovers(monkeypatch) -> None:
    """首次串台(中文)→ 重试返英文 → 采用重试结果(不降级)。"""
    calls = {"n": 0}
    zh_json = '{"score": 30, "confidence": 0.6, "rationale": "上升趋势延续。", "key_levels": [98.0]}'
    en_json = (
        '{"score": 40, "confidence": 0.65, '
        '"rationale": "Uptrend continues, RSI mid-range.", "key_levels": [99.0]}'
    )

    async def fake(prompt, **kwargs):  # noqa: ARG001
        calls["n"] += 1
        return _resp(zh_json if calls["n"] == 1 else en_json)

    monkeypatch.setattr(technical_mod, "ainvoke", fake)
    score, *_ = await analyze_technical(_make_snapshot(), "us", language="en")
    assert calls["n"] == 2                                   # 重试发生
    assert "Uptrend continues" in score.rationale            # 用重试英文结果
    assert "Composite technical read" not in score.rationale  # 非降级
    assert not contains_cjk(score.rationale)


@pytest.mark.asyncio
async def test_zh_technical_keeps_chinese(monkeypatch) -> None:
    """★zh 零变化:zh 路径不进语言锁分支,中文 rationale 原样通过(不被降级)。"""
    from app.core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "llm_mock_mode", True)
    score, *_ = await analyze_technical(_make_snapshot(), "cn", language="zh")
    assert contains_cjk(score.rationale)   # zh 就该是中文


# ===== 四 en plan_note:mock / 降级 / happy · 都英文 + 免责 + 无祈使 =====


@pytest.mark.asyncio
async def test_en_plan_note_mock(monkeypatch) -> None:
    """mock:en plan_note 走英文模板 + finalize(免责 + validator)。"""
    from app.core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "llm_mock_mode", True)
    note, _tok = await generate_plan_note(_make_plan(), "us", language="en")
    assert note.endswith(ADVISORY_DISCLAIMER_EN)
    assert not contains_cjk(note)
    assert not has_imperative(note, language="en")
    assert "Long plan" in note


@pytest.mark.asyncio
async def test_en_plan_note_degrades_on_cjk(monkeypatch) -> None:
    """LLM 两次都返中文(串台)→ 降级英文模板 + finalize。"""
    monkeypatch.setattr(plan_note_mod, "is_mock_mode", lambda: False)

    async def fake(prompt, **kwargs):  # noqa: ARG001
        return _resp("这是一段中文解释。")

    monkeypatch.setattr(plan_note_mod, "ainvoke", fake)
    note, _tok = await generate_plan_note(_make_plan(), "crypto", language="en")
    assert not contains_cjk(note)
    assert note.endswith(ADVISORY_DISCLAIMER_EN)


@pytest.mark.asyncio
async def test_en_plan_note_scrubs_imperative_and_marketing(monkeypatch) -> None:
    """★en 红线对等:LLM 英文含祈使+营销 → finalize 过 en validator 洗掉 + 补免责。"""
    monkeypatch.setattr(plan_note_mod, "is_mock_mode", lambda: False)

    async def fake(prompt, **kwargs):  # noqa: ARG001
        return _resp("You should buy now for guaranteed profit at 98.")

    monkeypatch.setattr(plan_note_mod, "ainvoke", fake)
    note, _tok = await generate_plan_note(_make_plan(), "us", language="en")
    low = note.lower()
    assert "you should buy" not in low
    assert "guaranteed profit" not in low
    assert note.endswith(ADVISORY_DISCLAIMER_EN)


@pytest.mark.asyncio
async def test_zh_plan_note_byte_identical_mock(monkeypatch) -> None:
    """★zh 零变化:zh plan_note(mock)== 现有 template_note · 不追加英文免责。"""
    from app.core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "llm_mock_mode", True)
    note, tok = await generate_plan_note(_make_plan(), "us", language="zh")
    assert note == template_note(_make_plan())
    assert tok == 0
    assert ADVISORY_DISCLAIMER_EN not in note


def test_template_note_en_preserves_numbers() -> None:
    """英文模板价位数字与中文版一字不差(纯规则算 · 只英文化叙述)。"""
    plan = _make_plan()
    en = template_note_en(plan)
    for num in ("98.0", "100.0", "94.0", "108.0", "116.0", "2.0"):
        assert num in en
    assert not contains_cjk(en)
    assert "not a trading instruction" in en


# ===== 五 workflow 端到端(en 决策卡)+ 缓存分桶 =====


@pytest.mark.asyncio
async def test_workflow_en_narrative_english_with_disclaimer(monkeypatch) -> None:
    """★en 决策卡端到端(mock):narrative 全英文 + 结尾英文免责固定串(validator 节点兜底)。"""
    from app.core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "llm_mock_mode", True)
    card = await run_decision_workflow(
        symbol="NVDA", market="us", period="1d", klines=_make_klines(200), language="en",
    )
    assert not contains_cjk(card.narrative), f"英文卡不应含中文:{card.narrative!r}"
    assert card.narrative.rstrip().endswith(ADVISORY_DISCLAIMER_EN)
    assert card.llm_mode == "mock"


@pytest.mark.asyncio
async def test_workflow_zh_still_chinese(monkeypatch) -> None:
    """★zh 零变化:zh 决策卡 narrative 仍是中文(不被 en 兜底污染)。"""
    from app.core import config as config_mod

    monkeypatch.setattr(config_mod.settings, "llm_mock_mode", True)
    card = await run_decision_workflow(
        symbol="600519", market="cn", period="1d", klines=_make_klines(200), language="zh",
    )
    assert contains_cjk(card.narrative)
    assert ADVISORY_DISCLAIMER_EN not in card.narrative


# ===== 六 对抗验证回归(finding 1 长度溢出 · finding 4 祈使门控缺口)=====


def test_finalize_note_en_caps_at_400_keeping_disclaimer() -> None:
    """★finding1 回归:免责兜底后必 ≤400(TradingPlan.plan_note 上限)且免责完整不被截。"""
    out = _finalize_note_en("a" * 600)
    assert len(out) <= 400
    assert out.endswith(ADVISORY_DISCLAIMER_EN)


@pytest.mark.asyncio
async def test_en_plan_note_long_llm_stays_under_400(monkeypatch) -> None:
    """★finding1 回归:LLM 返超长英文 → generate_plan_note en 出的 note 仍 ≤400 + 带免责
    (否则端点 response_model=DecisionCardResponse 再校验 string_too_long → 500)。"""
    monkeypatch.setattr(plan_note_mod, "is_mock_mode", lambda: False)

    async def fake(prompt, **kwargs):  # noqa: ARG001
        return _resp("The structure is framed around a pullback. " * 20)  # ~860 字英文

    monkeypatch.setattr(plan_note_mod, "ainvoke", fake)
    note, _tok = await generate_plan_note(_make_plan(), "us", language="en")
    assert len(note) <= 400
    assert note.endswith(ADVISORY_DISCLAIMER_EN)
    assert not contains_cjk(note)


def test_has_imperative_en_catches_buy_right_now() -> None:
    """★finding4 回归:'buy right now'/'sell right now' 现被 has_imperative(en) 命中
    (原漏出 _IMPERATIVE_KEYWORDS_EN → 门控漏改)。"""
    assert has_imperative("Momentum strong, buy right now.", language="en") is True
    assert has_imperative("Weakness — sell right now.", language="en") is True


@pytest.mark.asyncio
async def test_workflow_en_rewrites_buy_right_now(monkeypatch) -> None:
    """★finding4 回归:en narrative 含 'buy right now' → 决策卡 narrative 已改写为陈述句。"""

    async def fake(prompt, **kwargs):  # noqa: ARG001
        return _resp(
            '{"score": 55, "confidence": 0.7, '
            '"rationale": "Momentum is strong, buy right now before it runs.", '
            '"key_levels": [98.0, 110.0]}',
        )

    monkeypatch.setattr(technical_mod, "ainvoke", fake)
    card = await run_decision_workflow(
        symbol="NVDA", market="us", period="1d", klines=_make_klines(200), language="en",
    )
    assert "buy right now" not in card.narrative.lower()
    assert card.narrative.rstrip().endswith(ADVISORY_DISCLAIMER_EN)


def test_cache_key_language_bucket() -> None:
    """★缓存分桶:zh 无后缀(现有 key 不变)· en 加 :en(独立命名空间)。"""
    zh = make_cache_key("us", "NVDA", "1d", "2026-05-20")
    zh2 = make_cache_key("us", "NVDA", "1d", "2026-05-20", language="zh")
    en = make_cache_key("us", "NVDA", "1d", "2026-05-20", language="en")
    assert zh == "ai:decision:us:NVDA:1d:2026-05-20"     # 逐字节不变
    assert zh2 == zh
    assert en == "ai:decision:us:NVDA:1d:2026-05-20:en"
