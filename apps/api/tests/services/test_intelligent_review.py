"""智能交易 PR-7 · 复盘数据层测:build_review_data(复用 stats + by_side 各方向 + 共振质量)+ 取数窗口。

★纯函数本地真跑(build_review_data/analyze_signal_quality/period_start)· 取数 fetch CI DB collect。
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.services.virtual_trading.intelligent import account as iacc
from app.services.virtual_trading.intelligent import review


def _t(
    side: str, pnl: str, reason: str, contributions: dict[str, int], score: float,
) -> review.ReviewTrade:
    return review.ReviewTrade(
        symbol="BTCUSDT", side=side, entry_price=100.0, realized_pnl=Decimal(pnl),
        close_reason=reason, contributions=contributions, score=score,
        hold_seconds=3600, opened_at="2026-06-28T00:00:00+00:00",
        closed_at="2026-06-28T01:00:00+00:00",
    )


# ── 纯函数 build_review_data(本地真跑)──────────────────────────────
def test_build_review_data_overall_and_by_side() -> None:
    trades = [
        _t("long", "100", "take_profit", {"boll": 1, "macd": 1}, 8.0),
        _t("long", "-50", "stop_loss", {"boll": 1}, 3.5),
        _t("short", "80", "take_profit", {"boll": -1, "macd": -1}, -8.0),
        _t("short", "-20", "signal_reversal", {"boll": -1}, -3.5),
    ]
    data = review.build_review_data(trades, "day")
    assert data["period"] == "day"
    assert data["trade_count"] == 4
    # ★整体(复用 PR-6 stats)
    assert data["overall"]["total_trades"] == 4
    assert data["overall"]["win_rate"] == 0.5
    # ★by_side 各自(做多 1胜1负=50% · 做空 1胜1负=50%)
    assert data["by_side"]["long"]["total_trades"] == 2
    assert data["by_side"]["long"]["win_rate"] == 0.5
    assert data["by_side"]["short"]["total_trades"] == 2
    assert data["by_side"]["short"]["win_rate"] == 0.5


def test_by_side_asymmetric_win_rate() -> None:
    # ★做多全赢 / 做空全输 → 揭示哪个方向更准
    trades = [
        _t("long", "100", "take_profit", {"boll": 1}, 8.0),
        _t("long", "50", "take_profit", {"boll": 1}, 8.0),
        _t("short", "-30", "stop_loss", {"boll": -1}, -8.0),
    ]
    data = review.build_review_data(trades, "week")
    assert data["by_side"]["long"]["win_rate"] == 1.0   # 做多全赢
    assert data["by_side"]["short"]["win_rate"] == 0.0  # 做空全输


def test_by_reason_pct() -> None:
    trades = [
        _t("long", "100", "take_profit", {"boll": 1}, 8.0),
        _t("long", "80", "take_profit", {"boll": 1}, 8.0),
        _t("short", "-30", "stop_loss", {"boll": -1}, -8.0),
        _t("short", "-10", "signal_reversal", {"boll": -1}, -3.5),
    ]
    pct = review.build_review_data(trades, "month")["by_reason_pct"]
    assert pct["take_profit"] == 0.5    # 2/4
    assert pct["stop_loss"] == 0.25
    assert pct["signal_reversal"] == 0.25


# ── 纯函数 analyze_signal_quality(本地真跑)──────────────────────────
def test_signal_quality_by_indicator() -> None:
    # boll 参与全部 4 单(2 赢) · macd 参与 2 单(都赢)
    trades = [
        _t("long", "100", "take_profit", {"boll": 1, "macd": 1}, 8.0),
        _t("short", "80", "take_profit", {"boll": -1, "macd": -1}, -8.0),
        _t("long", "-50", "stop_loss", {"boll": 1}, 3.5),
        _t("short", "-20", "signal_reversal", {"boll": -1}, -3.5),
    ]
    q = review.analyze_signal_quality(trades)
    assert q["by_indicator"]["boll"]["trades"] == 4
    assert q["by_indicator"]["boll"]["win_rate"] == 0.5
    assert q["by_indicator"]["macd"]["trades"] == 2
    assert q["by_indicator"]["macd"]["win_rate"] == 1.0  # ★macd 参与的都赢
    assert q["by_indicator"]["rsi"]["trades"] == 0       # rsi 没参与


def test_signal_quality_by_score_band() -> None:
    # |score|≥6 强(2单·都赢) · 3<|score|<6 中(1单·输)
    trades = [
        _t("long", "100", "take_profit", {"boll": 1}, 8.0),
        _t("short", "80", "take_profit", {"boll": -1}, -7.0),
        _t("long", "-50", "stop_loss", {"boll": 1}, 3.5),
    ]
    band = review.analyze_signal_quality(trades)["by_score_band"]
    assert band["strong"]["trades"] == 2
    assert band["strong"]["win_rate"] == 1.0
    assert band["medium"]["trades"] == 1
    assert band["medium"]["win_rate"] == 0.0


def test_empty_review() -> None:
    data = review.build_review_data([], "day")
    assert data["trade_count"] == 0
    assert data["overall"]["total_trades"] == 0
    assert data["signal_quality"]["by_indicator"]["boll"]["trades"] == 0


# ── period_start 纯函数(本地真跑)──────────────────────────────────
def test_period_start() -> None:
    now = datetime(2026, 6, 24, 15, 30, tzinfo=UTC)  # 周三
    assert review.period_start("day", now) == datetime(2026, 6, 24, tzinfo=UTC)
    assert review.period_start("week", now) == datetime(2026, 6, 22, tzinfo=UTC)  # 周一
    assert review.period_start("month", now) == datetime(2026, 6, 1, tzinfo=UTC)


# ── 取数 fetch_review_trades(CI · DB)────────────────────────────────
def _closed_pos(account_id: int, symbol: str, closed_at: datetime, signals: dict[str, Any] | None) -> VirtualPerpPosition:
    p = VirtualPerpPosition(
        account_id=account_id, symbol=symbol, side=PerpSide.LONG,
        margin_mode=MarginMode.CROSS, leverage=5, quantity=Decimal("1"),
        entry_price=Decimal("100"), initial_margin=Decimal("20"),
        maintenance_margin_rate=Decimal("0.005"), liquidation_price=Decimal("0"),
        intelligent=True, intelligent_close_reason="take_profit",
        realized_pnl=Decimal("10"), intelligent_signals=signals,
    )
    p.opened_at = closed_at
    p.closed_at = closed_at
    return p


@pytest.mark.asyncio
async def test_fetch_review_trades_window(db_session: AsyncSession) -> None:
    acc = await iacc.ensure_intelligent_account(db_session)
    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
    # 窗口内(今天)+ 窗口外(昨天)
    db_session.add(_closed_pos(acc.id, "BTCUSDT", datetime(2026, 6, 24, 3, 0, tzinfo=UTC),
                               {"contributions": {"boll": 1}, "score": 8.0}))
    db_session.add(_closed_pos(acc.id, "ETHUSDT", datetime(2026, 6, 23, 3, 0, tzinfo=UTC), None))
    await db_session.commit()
    trades = await review.fetch_review_trades(db_session, "day", now)
    assert len(trades) == 1  # ★只今天的(昨天的在窗口外)
    assert trades[0].symbol == "BTCUSDT"
    assert trades[0].contributions == {"boll": 1}
    assert trades[0].score == 8.0


@pytest.mark.asyncio
async def test_fetch_handles_null_signals(db_session: AsyncSession) -> None:
    # ★intelligent_signals 为 None(早期仓)→ contributions={} score=0 不崩
    acc = await iacc.ensure_intelligent_account(db_session)
    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
    db_session.add(_closed_pos(acc.id, "BTCUSDT", datetime(2026, 6, 24, 3, 0, tzinfo=UTC), None))
    await db_session.commit()
    trades = await review.fetch_review_trades(db_session, "day", now)
    assert len(trades) == 1
    assert trades[0].contributions == {}
    assert trades[0].score == 0.0
