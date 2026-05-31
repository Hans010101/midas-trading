"""AI 决策卡 Reflection 回填 pytest · 0036 批次乙 sub-unit B(自学习闭环核心)。

覆盖范围:
- judge_correct 判定口径(bull/bear/flat/unknown)。
- reflect_pending 用真实 CH 历史价(fake)回填 was_correct + actual_return。
- 看多/看空/中性 各自命中 / 不命中。
- 未到 horizon 的记录不被处理。
- CH 暂无 horizon 后 K 线 → skip · reflected_at 仍 NULL · 下轮重试。
- 已验证(reflected_at NOT NULL)不重复处理。
- actual_return 数值精确。
- 批次混合(到期 + 未到期 + 已反思)。

🔴 红线验证:
- reflect_pending 只通过 ch.select_first_kline_at_or_after 读价(只读 CH 历史 · 不打实时)。
- fake CH 只实现该一个只读方法 · 证明 reflection 不调用任何写 / 实时 / 下单接口。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_analysis_memory import AIAnalysisMemory
from app.schemas.market import Kline
from app.services.ai.reflection import (
    DEFAULT_HORIZON,
    judge_correct,
    reflect_pending,
)

_NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)


class _FakeCH:
    """只实现 select_first_kline_at_or_after 的假 CH(★只读 · 证明 reflection 不碰别的)。

    close_by_symbol[symbol] = None → CH 暂无 horizon 后数据(返回 None)。
    记录每次调用的参数,供红线断言「只读历史 · 传的是 horizon 时刻」。
    """

    def __init__(self, close_by_symbol: dict[str, float | None]) -> None:
        self._close_by_symbol = close_by_symbol
        self.calls: list[dict[str, Any]] = []

    async def select_first_kline_at_or_after(
        self,
        *,
        symbol: str,
        market: str,
        period: str,
        at_or_after: datetime,
        instrument: str = "spot",
    ) -> Kline | None:
        self.calls.append(
            {
                "symbol": symbol,
                "market": market,
                "period": period,
                "at_or_after": at_or_after,
                "instrument": instrument,
            },
        )
        close = self._close_by_symbol.get(symbol)
        if close is None:
            return None
        return Kline(
            ts=at_or_after,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1000.0,
            amount=None,
        )


async def _make_memory(
    db: AsyncSession,
    *,
    symbol: str = "NVDA",
    market: str = "us",
    period: str = "1d",
    instrument: str = "spot",
    analyzed_at: datetime,
    direction: str = "bull",
    price_at: Decimal = Decimal("100"),
    composite_score: int = 60,
    composite_label: str = "强多",
    composite_confidence: Decimal = Decimal("0.7000"),
    llm_mode: str = "mock",
    reflected_at: datetime | None = None,
) -> AIAnalysisMemory:
    """造一行 AIAnalysisMemory · flush 拿 id(外层 SAVEPOINT 控制回滚)。"""
    row = AIAnalysisMemory(
        symbol=symbol,
        market=market,
        instrument=instrument,
        period=period,
        analyzed_at=analyzed_at,
        direction=direction,
        composite_score=composite_score,
        composite_label=composite_label,
        composite_confidence=composite_confidence,
        price_at=price_at,
        llm_mode=llm_mode,
        reflected_at=reflected_at,
    )
    db.add(row)
    await db.flush()
    return row


# ===== judge_correct · 判定口径 =====


def test_judge_bull_correct_when_up():
    """看多 + 涨 = 对 · 看多 + 跌 = 错。"""
    assert judge_correct("bull", Decimal("0.05")) is True
    assert judge_correct("bull", Decimal("-0.05")) is False
    assert judge_correct("bull", Decimal("0")) is False  # 不涨不算对


def test_judge_bear_correct_when_down():
    """看空 + 跌 = 对 · 看空 + 涨 = 错。"""
    assert judge_correct("bear", Decimal("-0.05")) is True
    assert judge_correct("bear", Decimal("0.05")) is False
    assert judge_correct("bear", Decimal("0")) is False  # 不跌不算对


def test_judge_flat_correct_within_1pct():
    """中性 + |涨跌| < 1% = 对 · 超出 = 错。"""
    assert judge_correct("flat", Decimal("0.005")) is True
    assert judge_correct("flat", Decimal("-0.009")) is True
    assert judge_correct("flat", Decimal("0.01")) is False   # 恰好 1% 不算横盘
    assert judge_correct("flat", Decimal("0.05")) is False
    assert judge_correct("flat", Decimal("-0.05")) is False


def test_judge_unknown_direction_false():
    """未知方向(防御)→ False。"""
    assert judge_correct("sideways", Decimal("0.05")) is False
    assert judge_correct("", Decimal("0")) is False


# ===== reflect_pending · 回填验证 =====


@pytest.mark.asyncio
async def test_reflect_bull_correct(db_session: AsyncSession) -> None:
    """看多 + 事后涨 → was_correct=True · actual_return>0 · reflected_at 写入。"""
    row = await _make_memory(
        db_session,
        symbol="NVDA",
        analyzed_at=_NOW - timedelta(days=8),  # 到期(>7d)
        direction="bull",
        price_at=Decimal("100"),
    )
    await db_session.commit()
    ch = _FakeCH({"NVDA": 110.0})  # 事后 110 → 涨 10%

    stats = await reflect_pending(db_session, ch, now=_NOW)  # type: ignore[arg-type]

    assert stats.scanned == 1
    assert stats.reflected == 1
    assert stats.skipped == 0

    await db_session.refresh(row)
    assert row.reflected_at == _NOW
    assert row.price_after == Decimal("110")
    assert row.actual_return == Decimal("0.100000")  # (110-100)/100
    assert row.was_correct is True


@pytest.mark.asyncio
async def test_reflect_bull_wrong(db_session: AsyncSession) -> None:
    """看多 + 事后跌 → was_correct=False。"""
    row = await _make_memory(
        db_session,
        symbol="NVDA",
        analyzed_at=_NOW - timedelta(days=8),
        direction="bull",
        price_at=Decimal("100"),
    )
    await db_session.commit()
    ch = _FakeCH({"NVDA": 90.0})  # 事后跌 10%

    stats = await reflect_pending(db_session, ch, now=_NOW)  # type: ignore[arg-type]
    assert stats.reflected == 1

    await db_session.refresh(row)
    assert row.actual_return == Decimal("-0.100000")
    assert row.was_correct is False


@pytest.mark.asyncio
async def test_reflect_bear_correct(db_session: AsyncSession) -> None:
    """看空 + 事后跌 → was_correct=True。"""
    row = await _make_memory(
        db_session,
        symbol="600519",
        market="cn",
        analyzed_at=_NOW - timedelta(days=8),
        direction="bear",
        price_at=Decimal("1800"),
    )
    await db_session.commit()
    ch = _FakeCH({"600519": 1620.0})  # 跌 10%

    await reflect_pending(db_session, ch, now=_NOW)  # type: ignore[arg-type]

    await db_session.refresh(row)
    assert row.was_correct is True
    assert row.actual_return == Decimal("-0.100000")


@pytest.mark.asyncio
async def test_reflect_flat_correct(db_session: AsyncSession) -> None:
    """中性 + 事后横盘(<1%)→ was_correct=True。"""
    row = await _make_memory(
        db_session,
        symbol="AAPL",
        analyzed_at=_NOW - timedelta(days=8),
        direction="flat",
        price_at=Decimal("200"),
    )
    await db_session.commit()
    ch = _FakeCH({"AAPL": 201.0})  # +0.5% < 1%

    await reflect_pending(db_session, ch, now=_NOW)  # type: ignore[arg-type]

    await db_session.refresh(row)
    assert row.was_correct is True


@pytest.mark.asyncio
async def test_reflect_flat_wrong_when_big_move(db_session: AsyncSession) -> None:
    """中性 + 事后大涨(>1%)→ was_correct=False。"""
    row = await _make_memory(
        db_session,
        symbol="AAPL",
        analyzed_at=_NOW - timedelta(days=8),
        direction="flat",
        price_at=Decimal("200"),
    )
    await db_session.commit()
    ch = _FakeCH({"AAPL": 220.0})  # +10%

    await reflect_pending(db_session, ch, now=_NOW)  # type: ignore[arg-type]

    await db_session.refresh(row)
    assert row.was_correct is False


@pytest.mark.asyncio
async def test_reflect_skips_not_yet_horizon(db_session: AsyncSession) -> None:
    """analyzed_at 仅 2 天前(< 7d horizon)→ 不在扫描范围 · 不被处理。"""
    row = await _make_memory(
        db_session,
        symbol="NVDA",
        analyzed_at=_NOW - timedelta(days=2),  # 未到 horizon
        direction="bull",
    )
    await db_session.commit()
    ch = _FakeCH({"NVDA": 110.0})

    stats = await reflect_pending(db_session, ch, now=_NOW)  # type: ignore[arg-type]

    assert stats.scanned == 0  # 查询过滤掉(analyzed_at > now-horizon)
    assert len(ch.calls) == 0  # 没读 CH
    await db_session.refresh(row)
    assert row.reflected_at is None  # 保持待回填


@pytest.mark.asyncio
async def test_reflect_skips_when_ch_empty(db_session: AsyncSession) -> None:
    """CH 暂无 horizon 后 K 线 → skip · reflected_at 仍 NULL · 下轮重试。"""
    row = await _make_memory(
        db_session,
        symbol="OBSCURE",
        analyzed_at=_NOW - timedelta(days=8),
        direction="bull",
    )
    await db_session.commit()
    ch = _FakeCH({"OBSCURE": None})  # CH 无数据

    stats = await reflect_pending(db_session, ch, now=_NOW)  # type: ignore[arg-type]

    assert stats.scanned == 1
    assert stats.reflected == 0
    assert stats.skipped == 1
    await db_session.refresh(row)
    assert row.reflected_at is None  # 仍待回填(下轮重试)
    assert row.was_correct is None


@pytest.mark.asyncio
async def test_reflect_does_not_redo_already_reflected(
    db_session: AsyncSession,
) -> None:
    """已验证(reflected_at NOT NULL)的记录不被重复处理。"""
    already = _NOW - timedelta(days=1)
    row = await _make_memory(
        db_session,
        symbol="NVDA",
        analyzed_at=_NOW - timedelta(days=8),
        direction="bull",
        reflected_at=already,
    )
    # 模拟已回填的旧值
    row.price_after = Decimal("105")
    row.actual_return = Decimal("0.05")
    row.was_correct = True
    await db_session.commit()
    ch = _FakeCH({"NVDA": 999.0})  # 若被重复处理,值会变

    stats = await reflect_pending(db_session, ch, now=_NOW)  # type: ignore[arg-type]

    assert stats.scanned == 0  # 部分索引 reflected_at IS NULL 过滤掉它
    assert len(ch.calls) == 0
    await db_session.refresh(row)
    # 旧值不变(没被重复回填)
    assert row.reflected_at == already
    assert row.price_after == Decimal("105")
    assert row.was_correct is True


@pytest.mark.asyncio
async def test_reflect_actual_return_precision(db_session: AsyncSession) -> None:
    """actual_return 数值精确 · Numeric(10,6) 保留 6 位小数。"""
    row = await _make_memory(
        db_session,
        symbol="BTCUSDT",
        market="crypto",
        instrument="perp",
        period="1h",
        analyzed_at=_NOW - timedelta(days=8),
        direction="bull",
        price_at=Decimal("60000"),
    )
    await db_session.commit()
    ch = _FakeCH({"BTCUSDT": 63450.0})  # (63450-60000)/60000 = 0.0575

    await reflect_pending(db_session, ch, now=_NOW)  # type: ignore[arg-type]

    await db_session.refresh(row)
    assert row.actual_return == Decimal("0.057500")
    assert row.was_correct is True
    # ★ 红线断言:reflection 读的是 horizon 时刻(analyzed_at + 7d)· 只读历史 · perp instrument 透传
    assert len(ch.calls) == 1
    call = ch.calls[0]
    assert call["at_or_after"] == row.analyzed_at + DEFAULT_HORIZON
    assert call["instrument"] == "perp"
    assert call["market"] == "crypto"


@pytest.mark.asyncio
async def test_reflect_batch_mixed(db_session: AsyncSession) -> None:
    """批次混合:到期未反思(处理)+ 未到期(跳过)+ 已反思(跳过)。"""
    due = await _make_memory(
        db_session,
        symbol="DUE",
        analyzed_at=_NOW - timedelta(days=10),
        direction="bull",
        price_at=Decimal("100"),
    )
    not_yet = await _make_memory(
        db_session,
        symbol="NOTYET",
        analyzed_at=_NOW - timedelta(days=3),
        direction="bull",
    )
    done = await _make_memory(
        db_session,
        symbol="DONE",
        analyzed_at=_NOW - timedelta(days=9),
        direction="bull",
        reflected_at=_NOW - timedelta(days=1),
    )
    await db_session.commit()
    ch = _FakeCH({"DUE": 120.0, "NOTYET": 120.0, "DONE": 120.0})

    stats = await reflect_pending(db_session, ch, now=_NOW)  # type: ignore[arg-type]

    # 只有 DUE 被处理
    assert stats.scanned == 1
    assert stats.reflected == 1
    assert {c["symbol"] for c in ch.calls} == {"DUE"}

    await db_session.refresh(due)
    await db_session.refresh(not_yet)
    await db_session.refresh(done)
    assert due.reflected_at == _NOW
    assert due.was_correct is True
    assert not_yet.reflected_at is None  # 未到期 · 没动
    assert done.reflected_at == _NOW - timedelta(days=1)  # 已反思 · 没动
