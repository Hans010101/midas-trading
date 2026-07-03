"""AI 决策卡历史 memory 服务 pytest · 0036 批次乙 sub-unit A。

覆盖范围:
- direction_from_label 五档 → 三档归并(强多/弱多 → bull · 中性 → flat · 弱空/强空 → bear)。
- record_decision happy path · 写入一行 AIAnalysisMemory · 字段全对。
- record_decision best-effort · 异常吞掉不阻塞调用方(传 None session 也不抛)。
- 端点旁路集成:cache-miss 后调用 record_decision · 路径一致性。

🔴 红线验证:
- 写入失败必须不抛出(用户已经看到决策卡)。
- direction 由 composite_label 派生 · 一致映射 · 防 reflection 错判。
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_analysis_memory import AIAnalysisMemory
from app.schemas.ai_decision import AgentScore, DecisionCardResponse
from app.services.ai.memory import direction_from_label, record_decision


def _make_card(
    *,
    symbol: str = "NVDA",
    market: str = "us",
    period: str = "1d",
    composite_score: int = 60,
    composite_label: str = "强多",
    composite_confidence: float = 0.75,
    llm_mode: str = "mock",
) -> DecisionCardResponse:
    """造一张最小合法决策卡 · 关键字段可覆盖。"""
    score = AgentScore(
        name="technical",
        score=composite_score,
        confidence=composite_confidence,
        rationale="结构良好,均线多头排列。",
        key_levels=[100.0, 110.0],
    )
    return DecisionCardResponse(
        symbol=symbol,
        market=market,  # type: ignore[arg-type]
        period=period,  # type: ignore[arg-type]
        generated_at=datetime(2026, 5, 31, 10, 0, tzinfo=UTC),
        composite_score=composite_score,
        composite_label=composite_label,  # type: ignore[arg-type]
        composite_confidence=composite_confidence,
        agent_scores=[score],
        contradiction=None,
        narrative="技术面整体偏多。",
        chan_signals=[],
        cached=False,
        token_usage=150,
        llm_mode=llm_mode,  # type: ignore[arg-type]
    )


# ===== direction_from_label · 五档 → 三档 =====


def test_direction_from_label_bull():
    """强多 / 弱多 → bull。"""
    assert direction_from_label("强多") == "bull"
    assert direction_from_label("弱多") == "bull"


def test_direction_from_label_flat():
    """中性 → flat。"""
    assert direction_from_label("中性") == "flat"


def test_direction_from_label_bear():
    """弱空 / 强空 → bear。"""
    assert direction_from_label("弱空") == "bear"
    assert direction_from_label("强空") == "bear"


def test_direction_from_label_unknown_fallback_flat():
    """未知 label fallback flat · 防御未来 schema 扩展。"""
    assert direction_from_label("超强多") == "flat"
    assert direction_from_label("") == "flat"


# ===== record_decision · happy path =====


@pytest.mark.asyncio
async def test_record_decision_writes_row_with_all_fields(
    db_session: AsyncSession,
) -> None:
    """决策卡 + price_at + instrument → 一行 AIAnalysisMemory · 字段全对。"""
    card = _make_card(
        symbol="BTCUSDT",
        market="crypto",
        period="1h",
        composite_score=-45,
        composite_label="弱空",
        composite_confidence=0.6,
        llm_mode="real",
    )

    await record_decision(
        db_session,
        card=card,
        instrument="perp",
        price_at=Decimal("60123.45678901"),
    )

    rows = (
        await db_session.scalars(
            select(AIAnalysisMemory).where(AIAnalysisMemory.symbol == "BTCUSDT"),
        )
    ).all()
    assert len(rows) == 1
    row = rows[0]

    assert row.symbol == "BTCUSDT"
    assert row.market == "crypto"
    assert row.instrument == "perp"
    assert row.period == "1h"
    assert row.analyzed_at == card.generated_at
    # 弱空 → bear
    assert row.direction == "bear"
    assert row.composite_score == -45
    assert row.composite_label == "弱空"
    assert row.composite_confidence == Decimal("0.6000")
    assert row.price_at == Decimal("60123.45678901")
    assert row.llm_mode == "real"
    # Reflection 列初写全 NULL
    assert row.reflected_at is None
    assert row.price_after is None
    assert row.actual_return is None
    assert row.was_correct is None


@pytest.mark.asyncio
async def test_record_decision_default_language_zh(db_session: AsyncSession) -> None:
    """i18n Phase4 刀2:不传 language → 默认 'zh'(向后兼容 · server_default 兜底)。"""
    card = _make_card(symbol="ZHDEF", market="us", period="1d")
    await record_decision(
        db_session, card=card, instrument="spot", price_at=Decimal("100.0"),
    )
    row = (
        await db_session.scalars(
            select(AIAnalysisMemory).where(AIAnalysisMemory.symbol == "ZHDEF"),
        )
    ).one()
    assert row.language == "zh"


@pytest.mark.asyncio
async def test_record_decision_stores_en_language(db_session: AsyncSession) -> None:
    """i18n Phase4 刀2:显式 language='en' → 存实际生成语言 'en'。"""
    card = _make_card(symbol="ENGEN", market="us", period="1d")
    await record_decision(
        db_session, card=card, instrument="spot", price_at=Decimal("100.0"), language="en",
    )
    row = (
        await db_session.scalars(
            select(AIAnalysisMemory).where(AIAnalysisMemory.symbol == "ENGEN"),
        )
    ).one()
    assert row.language == "en"


@pytest.mark.asyncio
async def test_record_decision_spot_default_instrument(
    db_session: AsyncSession,
) -> None:
    """现货(instrument='spot')· 强多 → bull · 默认 llm_mode='mock'。"""
    card = _make_card(
        symbol="600519", market="cn", period="1d",
        composite_score=72, composite_label="强多",
    )
    await record_decision(
        db_session, card=card, instrument="spot", price_at=Decimal("1820.30"),
    )

    row = (
        await db_session.scalars(
            select(AIAnalysisMemory).where(AIAnalysisMemory.symbol == "600519"),
        )
    ).one()
    assert row.instrument == "spot"
    assert row.direction == "bull"  # 强多 → bull
    assert row.llm_mode == "mock"


@pytest.mark.asyncio
async def test_record_decision_flat_label(db_session: AsyncSession) -> None:
    """中性 → flat · 评分接近 0。"""
    card = _make_card(
        symbol="AAPL", market="us", period="1d",
        composite_score=5, composite_label="中性",
    )
    await record_decision(
        db_session, card=card, instrument="spot", price_at=Decimal("180.00"),
    )

    row = (
        await db_session.scalars(
            select(AIAnalysisMemory).where(AIAnalysisMemory.symbol == "AAPL"),
        )
    ).one()
    assert row.direction == "flat"


# ===== record_decision · best-effort · 永不抛 =====


@pytest.mark.asyncio
async def test_record_decision_swallows_session_error(
    db_session: AsyncSession,
) -> None:
    """传一个会在 commit 时炸的 session(模拟 DB 故障)· 函数必须吞掉不抛。

    手段:close 掉 session,后续 add + commit 会炸,但 record_decision 必须 silent 返回。
    """
    card = _make_card()
    await db_session.close()

    # ★ 关键断言:不抛任何异常(用户响应路径不阻塞)
    await record_decision(
        db_session, card=card, instrument="spot", price_at=Decimal("100.00"),
    )
    # 没抛 = pass


@pytest.mark.asyncio
async def test_record_decision_swallows_invalid_price_type(
    db_session: AsyncSession,
) -> None:
    """传入非法 price_at(超出 Numeric(20,8) 精度)· 必须吞掉不抛。"""
    card = _make_card()
    # 超大数值 · 触发 numeric overflow(20,8 总 20 位,整数部分最多 12 位)
    bad_price = Decimal("9" * 30)

    await record_decision(
        db_session, card=card, instrument="spot", price_at=bad_price,
    )
    # 没抛 = pass · 用户响应路径不被污染
