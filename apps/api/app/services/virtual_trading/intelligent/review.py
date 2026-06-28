"""智能交易 · 复盘数据层(第二期 PR-7)· 🔴只读交易数据分析 · 不碰交易执行 · 引擎零碰。

把 intelligent 交易数据整理成【结构化复盘数据】(喂 PR-8 的 DeepSeek 复盘分析师)· 纯函数可测。
★复用 PR-6 compute_intelligent_stats(整体 + by_reason + by_side 笔数)· 扩展:
  ① 时间聚合(日/周/月)· ② 做多/做空各自胜率盈亏比(复用 stats)· ③ 共振质量。
★PR-7 只整理数据(还不调 DeepSeek · PR-8 才调)· DeepSeek 定位 = 复盘分析师(旁观 · 不参与下单)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.perp import VirtualPerpPosition
from app.services.virtual_trading.intelligent import account as iacc
from app.services.virtual_trading.intelligent.stats import (
    ClosedIntelligentTrade,
    compute_intelligent_stats,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

INDICATORS = ("boll", "macd", "ma", "rsi", "kdj", "extreme")
_PERIODS = ("day", "week", "month")


@dataclass(frozen=True)
class ReviewTrade:
    """复盘单(从已平 intelligent 仓抽 · 含开仓共振 + 平仓结果)。"""

    symbol: str
    side: str                       # long / short
    entry_price: float
    realized_pnl: Decimal
    close_reason: str | None        # stop_loss / take_profit / signal_reversal
    contributions: dict[str, int]   # 开仓时共振方向分 {boll:1, macd:1, ...}
    score: float                    # 开仓共振总分
    hold_seconds: int
    opened_at: str
    closed_at: str | None


def _to_closed(t: ReviewTrade) -> ClosedIntelligentTrade:
    return ClosedIntelligentTrade(
        realized_pnl=t.realized_pnl, close_reason=t.close_reason, side=t.side,
    )


def _win_block(trades: list[ReviewTrade]) -> dict[str, Any]:
    """一组单的笔数/赢数/胜率(共振质量子项 · 纯计数)。"""
    total = len(trades)
    wins = sum(1 for t in trades if t.realized_pnl > 0)
    return {"trades": total, "wins": wins, "win_rate": round(wins / total, 4) if total else 0.0}


def analyze_signal_quality(trades: list[ReviewTrade]) -> dict[str, Any]:
    """★共振质量:哪些指标 / 共振强度开的单表现好。

    ① by_indicator:每个指标【参与(方向≠0)】的单的胜率(哪个指标更准)。
    ② by_score_band:共振强弱区间胜率(|score|≥6 强 / 3<|score|<6 中 · 强共振是否更准)。
    """
    by_indicator = {
        ind: _win_block([t for t in trades if t.contributions.get(ind, 0) != 0])
        for ind in INDICATORS
    }
    strong = [t for t in trades if abs(t.score) >= 6]
    medium = [t for t in trades if 3 < abs(t.score) < 6]
    return {
        "by_indicator": by_indicator,
        "by_score_band": {"strong": _win_block(strong), "medium": _win_block(medium)},
    }


def _reason_pct(stats: dict[str, Any]) -> dict[str, float]:
    """三退出原因占比(说明策略靠什么离场)· 从 stats.by_reason 算。"""
    by_reason: dict[str, int] = stats["by_reason"]
    total = sum(by_reason.values())
    return {k: round(v / total, 4) if total else 0.0 for k, v in by_reason.items()}


def build_review_data(trades: list[ReviewTrade], period: str) -> dict[str, Any]:
    """★结构化复盘数据(喂 PR-8 DeepSeek)· period=day/week/month · 纯函数。

    overall + by_side(做多做空各自) + by_reason 占比 + 共振质量 + 单数。
    """
    closed = [_to_closed(t) for t in trades]
    longs = [c for c in closed if c.side == "long"]
    shorts = [c for c in closed if c.side == "short"]
    overall = compute_intelligent_stats(closed)        # ★复用 PR-6
    return {
        "period": period,
        "trade_count": len(trades),
        "overall": overall,
        "by_side": {
            "long": compute_intelligent_stats(longs),  # ★做多各自胜率/盈亏比
            "short": compute_intelligent_stats(shorts),  # ★做空各自
        },
        "by_reason_pct": _reason_pct(overall),         # 三退出占比
        "signal_quality": analyze_signal_quality(trades),  # ★共振质量
    }


def period_start(period: str, now: datetime) -> datetime:
    """时间窗口起点(纯函数)· day=当天 0 点 / week=本周一 / month=本月 1 号(均 now 的 tz)。"""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        return midnight - timedelta(days=now.weekday())
    if period == "month":
        return midnight.replace(day=1)
    return midnight  # day(含未知兜底)


async def fetch_review_trades(
    session: AsyncSession, period: str, now: datetime,
) -> list[ReviewTrade]:
    """★取数(只读)· 查【已平 intelligent 仓】closed_at 在窗口内 → list[ReviewTrade]· 引擎零碰。"""
    if period not in _PERIODS:
        period = "day"
    start = period_start(period, now)
    uid = await iacc.get_intelligent_user_id(session)
    if uid is None:
        return []
    acc = await iacc.ensure_intelligent_account(session)
    rows = list(await session.scalars(
        select(VirtualPerpPosition)
        .where(
            VirtualPerpPosition.account_id == acc.id,
            VirtualPerpPosition.intelligent.is_(True),
            VirtualPerpPosition.closed_at.is_not(None),
            VirtualPerpPosition.closed_at >= start,
        )
        .order_by(VirtualPerpPosition.closed_at.asc()),  # 升序 · 复盘按时间读
    ))
    out: list[ReviewTrade] = []
    for r in rows:
        sig: dict[str, Any] = r.intelligent_signals or {}
        contributions = sig.get("contributions") if isinstance(sig, dict) else None
        hold = int((r.closed_at - r.opened_at).total_seconds()) if r.closed_at else 0
        out.append(ReviewTrade(
            symbol=r.symbol, side=r.side.value, entry_price=float(r.entry_price),
            realized_pnl=r.realized_pnl, close_reason=r.intelligent_close_reason,
            contributions=contributions if isinstance(contributions, dict) else {},
            score=float(sig.get("score", 0.0)) if isinstance(sig, dict) else 0.0,
            hold_seconds=hold,
            opened_at=r.opened_at.isoformat(),
            closed_at=r.closed_at.isoformat() if r.closed_at else None,
        ))
    return out
