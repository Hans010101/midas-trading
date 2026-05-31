"""AI 历史命中率计算 pytest · 0036 批次乙 sub-unit C(自学习闭环呈现层)。

覆盖范围:
- 总体命中率 + 样本数算对。
- 市场 / 方向 / 置信度三维分桶算对。
- ★ 样本量诚实标注:reliable 阈值 · 小样本 reliable=False。
- hit_rate 在样本 0 时为 None(不写 0.0)。
- 未验证记录(was_correct NULL)不计入。
- since(时间窗)+ llm_mode 过滤。
- 置信度桶边界(<50 / 90-100 含 1.0)。

🔴 红线验证:
- 只读 PG · 只统计 was_correct IS NOT NULL 的 reflection 已验证记录。
- 不碰下单 / 不改 analyze(本服务只 select 聚合)。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_analysis_memory import AIAnalysisMemory
from app.services.ai.accuracy import MIN_RELIABLE_SAMPLE, compute_accuracy

_NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)


async def _make_verified(
    db: AsyncSession,
    *,
    symbol: str = "NVDA",
    market: str = "us",
    direction: str = "bull",
    confidence: str = "0.7000",
    was_correct: bool | None = True,
    analyzed_at: datetime | None = None,
    llm_mode: str = "mock",
    composite_label: str = "强多",
) -> AIAnalysisMemory:
    """造一行 AIAnalysisMemory · was_correct 默认已回填(reflected)。"""
    at = analyzed_at or (_NOW - timedelta(days=10))
    row = AIAnalysisMemory(
        symbol=symbol,
        market=market,
        instrument="spot",
        period="1d",
        analyzed_at=at,
        direction=direction,
        composite_score=60,
        composite_label=composite_label,
        composite_confidence=Decimal(confidence),
        price_at=Decimal("100"),
        llm_mode=llm_mode,
        # 已验证:reflected_at + was_correct 都写(NULL=未验证不计入)
        reflected_at=(at + timedelta(days=7)) if was_correct is not None else None,
        price_after=Decimal("110") if was_correct is not None else None,
        actual_return=Decimal("0.1") if was_correct is not None else None,
        was_correct=was_correct,
    )
    db.add(row)
    await db.flush()
    return row


# ===== 总体命中率 =====


@pytest.mark.asyncio
async def test_overall_hit_rate(db_session: AsyncSession) -> None:
    """3 对 1 错 → 总体 75% · 样本 4。"""
    for _ in range(3):
        await _make_verified(db_session, was_correct=True)
    await _make_verified(db_session, was_correct=False)
    await db_session.commit()

    resp = await compute_accuracy(db_session)

    assert resp.overall_sample_count == 4
    assert resp.overall_correct_count == 3
    assert resp.overall_hit_rate == 0.75


@pytest.mark.asyncio
async def test_unverified_records_excluded(db_session: AsyncSession) -> None:
    """was_correct IS NULL(未到 horizon / 未回填)不计入统计。"""
    await _make_verified(db_session, was_correct=True)
    await _make_verified(db_session, was_correct=None)  # 未验证
    await _make_verified(db_session, was_correct=None)  # 未验证
    await db_session.commit()

    resp = await compute_accuracy(db_session)
    assert resp.overall_sample_count == 1  # 只算已验证的 1 条
    assert resp.overall_hit_rate == 1.0


@pytest.mark.asyncio
async def test_empty_returns_none_not_zero(db_session: AsyncSession) -> None:
    """★ 无样本时 hit_rate=None(不写 0.0 避免「0% 命中」误导)。"""
    resp = await compute_accuracy(db_session)
    assert resp.overall_sample_count == 0
    assert resp.overall_hit_rate is None
    # 固定列出的市场 / 方向桶仍返回(样本 0 · hit_rate None · reliable False)
    cn = next(b for b in resp.by_market if b.key == "cn")
    assert cn.sample_count == 0
    assert cn.hit_rate is None
    assert cn.reliable is False


# ===== 分桶 =====


@pytest.mark.asyncio
async def test_by_market_bucketing(db_session: AsyncSession) -> None:
    """市场分桶:cn 2对1错(66.7%)· us 1对(100%)· crypto 0样本(None)。"""
    await _make_verified(db_session, market="cn", was_correct=True)
    await _make_verified(db_session, market="cn", was_correct=True)
    await _make_verified(db_session, market="cn", was_correct=False)
    await _make_verified(db_session, market="us", was_correct=True)
    await db_session.commit()

    resp = await compute_accuracy(db_session)
    by_market = {b.key: b for b in resp.by_market}

    assert by_market["cn"].sample_count == 3
    assert by_market["cn"].correct_count == 2
    assert by_market["cn"].hit_rate == pytest.approx(2 / 3)
    assert by_market["us"].sample_count == 1
    assert by_market["us"].hit_rate == 1.0
    assert by_market["crypto"].sample_count == 0
    assert by_market["crypto"].hit_rate is None


@pytest.mark.asyncio
async def test_by_direction_bucketing(db_session: AsyncSession) -> None:
    """方向分桶:bull / bear / flat 各自聚合。"""
    await _make_verified(db_session, direction="bull", was_correct=True)
    await _make_verified(db_session, direction="bull", was_correct=False)
    await _make_verified(db_session, direction="bear", was_correct=True)
    await _make_verified(db_session, direction="flat", was_correct=True)
    await db_session.commit()

    resp = await compute_accuracy(db_session)
    by_dir = {b.key: b for b in resp.by_direction}

    assert by_dir["bull"].sample_count == 2
    assert by_dir["bull"].hit_rate == 0.5
    assert by_dir["bear"].sample_count == 1
    assert by_dir["bear"].hit_rate == 1.0
    assert by_dir["flat"].sample_count == 1
    assert by_dir["flat"].hit_rate == 1.0


@pytest.mark.asyncio
async def test_by_confidence_bucketing(db_session: AsyncSession) -> None:
    """置信度分桶:0.55→50-60 · 0.65→60-70 · 0.95→90-100。"""
    await _make_verified(db_session, confidence="0.5500", was_correct=True)
    await _make_verified(db_session, confidence="0.6500", was_correct=True)
    await _make_verified(db_session, confidence="0.6500", was_correct=False)
    await _make_verified(db_session, confidence="0.9500", was_correct=True)
    await db_session.commit()

    resp = await compute_accuracy(db_session)
    by_conf = {b.key: b for b in resp.by_confidence}

    assert by_conf["50-60"].sample_count == 1
    assert by_conf["50-60"].hit_rate == 1.0
    assert by_conf["60-70"].sample_count == 2
    assert by_conf["60-70"].hit_rate == 0.5
    assert by_conf["90-100"].sample_count == 1
    assert by_conf["90-100"].hit_rate == 1.0
    # 没数据的桶仍在(<50 / 70-80 / 80-90)· 样本 0
    assert by_conf["<50"].sample_count == 0
    assert by_conf["<50"].hit_rate is None


@pytest.mark.asyncio
async def test_confidence_boundary_1_0_in_top_bucket(db_session: AsyncSession) -> None:
    """置信度 1.0(满)落入 90-100 桶(上界含 1.0)。"""
    await _make_verified(db_session, confidence="1.0000", was_correct=True)
    await _make_verified(db_session, confidence="0.4000", was_correct=False)
    await db_session.commit()

    resp = await compute_accuracy(db_session)
    by_conf = {b.key: b for b in resp.by_confidence}
    assert by_conf["90-100"].sample_count == 1  # 1.0 在这
    assert by_conf["<50"].sample_count == 1      # 0.4 在这


# ===== ★ 样本量诚实标注 =====


@pytest.mark.asyncio
async def test_reliable_flag_small_sample(db_session: AsyncSession) -> None:
    """★ 小样本(< MIN_RELIABLE_SAMPLE)reliable=False · 即便 3 条全对也不冒充可靠。"""
    for _ in range(3):
        await _make_verified(db_session, market="cn", was_correct=True)
    await db_session.commit()

    resp = await compute_accuracy(db_session)
    cn = next(b for b in resp.by_market if b.key == "cn")
    assert cn.sample_count == 3
    assert cn.hit_rate == 1.0       # 3 条全对
    assert cn.reliable is False     # ★ 但样本不足 · 诚实标注不可靠
    assert resp.min_reliable_sample == MIN_RELIABLE_SAMPLE


@pytest.mark.asyncio
async def test_reliable_flag_enough_sample(db_session: AsyncSession) -> None:
    """样本 >= 阈值 → reliable=True。"""
    for _ in range(MIN_RELIABLE_SAMPLE):
        await _make_verified(db_session, market="us", was_correct=True)
    await db_session.commit()

    resp = await compute_accuracy(db_session)
    us = next(b for b in resp.by_market if b.key == "us")
    assert us.sample_count == MIN_RELIABLE_SAMPLE
    assert us.reliable is True


# ===== 过滤 =====


@pytest.mark.asyncio
async def test_since_filter(db_session: AsyncSession) -> None:
    """since 时间窗:只统计 analyzed_at >= since 的记录。"""
    await _make_verified(
        db_session, analyzed_at=_NOW - timedelta(days=5), was_correct=True,
    )
    await _make_verified(
        db_session, analyzed_at=_NOW - timedelta(days=100), was_correct=False,
    )
    await db_session.commit()

    # 只看最近 30 天 → 只算 5 天前那条
    resp = await compute_accuracy(
        db_session, since=_NOW - timedelta(days=30), since_days=30,
    )
    assert resp.overall_sample_count == 1
    assert resp.overall_hit_rate == 1.0
    assert resp.since_days == 30


@pytest.mark.asyncio
async def test_llm_mode_filter(db_session: AsyncSession) -> None:
    """llm_mode 过滤:只统计指定模式(mock 数据不污染 real 命中率)。"""
    await _make_verified(db_session, llm_mode="real", was_correct=True)
    await _make_verified(db_session, llm_mode="mock", was_correct=False)
    await _make_verified(db_session, llm_mode="mock", was_correct=False)
    await db_session.commit()

    resp = await compute_accuracy(db_session, llm_mode="real")
    assert resp.overall_sample_count == 1
    assert resp.overall_hit_rate == 1.0
    assert resp.llm_mode_filter == "real"


# ===== note 诚实标注 =====


@pytest.mark.asyncio
async def test_note_present(db_session: AsyncSession) -> None:
    """统计口径说明(note)非空 · 含小样本告知。"""
    resp = await compute_accuracy(db_session)
    assert resp.note
    assert str(MIN_RELIABLE_SAMPLE) in resp.note
