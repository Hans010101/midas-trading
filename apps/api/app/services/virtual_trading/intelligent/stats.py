"""智能交易 · 前向测试统计(智能交易 PR-6)· 纯函数 · 从已平仓 intelligent 仓算。

胜率 / 总盈亏 / 平均盈亏 / 盈亏比 / 最大回撤 / 按平仓原因分类 / ★做多做空拆分(intelligent 特有)。
🔴纯虚拟统计 · 只读 closed intelligent 仓 realized_pnl + close_reason + side · 零碰引擎。
★by_reason keys = intelligent 三退出(stop_loss/take_profit/signal_reversal)· 不复用 managed。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ClosedIntelligentTrade:
    """已平仓 intelligent 单(统计入参 · 从 VirtualPerpPosition 抽)。"""

    realized_pnl: Decimal
    close_reason: str | None  # stop_loss / take_profit / signal_reversal
    side: str                 # long / short(★做多做空拆分)


def compute_intelligent_stats(
    trades: list[ClosedIntelligentTrade],
) -> dict[str, float | int | dict[str, int]]:
    """聚合统计(全 float 便于 JSON)· trades 按平仓时间升序(算最大回撤的权益曲线)。

    ★by_reason = 三退出分类 · by_side = 做多做空笔数(intelligent 做多做空,managed 没有)。
    """
    total = len(trades)
    by_reason: dict[str, int] = {"stop_loss": 0, "take_profit": 0, "signal_reversal": 0}
    by_side: dict[str, int] = {"long": 0, "short": 0}
    if total == 0:
        return {
            "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "total_pnl": 0.0, "avg_pnl": 0.0, "profit_factor": 0.0,
            "max_drawdown": 0.0, "by_reason": by_reason, "by_side": by_side,
        }

    wins = sum(1 for t in trades if t.realized_pnl > 0)
    losses = sum(1 for t in trades if t.realized_pnl < 0)
    total_pnl = sum((t.realized_pnl for t in trades), Decimal("0"))
    gross_profit = sum((t.realized_pnl for t in trades if t.realized_pnl > 0), Decimal("0"))
    gross_loss = sum((-t.realized_pnl for t in trades if t.realized_pnl < 0), Decimal("0"))
    # 盈亏比:总盈利 / 总亏损(无亏损 → 0.0 表示「无穷大/无亏损」,前端特判展示)
    profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else 0.0

    # 最大回撤:累计权益曲线的峰值回落最大值(绝对 U)
    cum = Decimal("0")
    peak = Decimal("0")
    max_dd = Decimal("0")
    for t in trades:
        cum += t.realized_pnl
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    for t in trades:
        if t.close_reason in by_reason:
            by_reason[t.close_reason] += 1
        if t.side in by_side:
            by_side[t.side] += 1

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total, 4),
        "total_pnl": round(float(total_pnl), 4),
        "avg_pnl": round(float(total_pnl) / total, 4),
        "profit_factor": round(profit_factor, 4),
        "max_drawdown": round(float(max_dd), 4),
        "by_reason": by_reason,
        "by_side": by_side,
    }
