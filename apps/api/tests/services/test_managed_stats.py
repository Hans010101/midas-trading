"""托管交易 PR-4 · 前向测试统计(纯函数)· 胜率/盈亏比/最大回撤/按原因分类。"""

from __future__ import annotations

from decimal import Decimal

from app.services.virtual_trading.managed.stats import ClosedTrade, compute_managed_stats


def _t(pnl: str, reason: str) -> ClosedTrade:
    return ClosedTrade(realized_pnl=Decimal(pnl), close_reason=reason)


def test_empty() -> None:
    s = compute_managed_stats([])
    assert s["total_trades"] == 0
    assert s["win_rate"] == 0.0
    assert s["by_reason"] == {"tp": 0, "signal": 0, "timeout": 0}


def test_win_rate_and_pnl() -> None:
    # 3 单:+100(tp)、-40(signal)、+60(timeout)→ 胜 2/3 · 总 +120 · 均 40
    s = compute_managed_stats([_t("100", "tp"), _t("-40", "signal"), _t("60", "timeout")])
    assert s["total_trades"] == 3
    assert s["wins"] == 2
    assert s["losses"] == 1
    assert s["win_rate"] == round(2 / 3, 4)
    assert s["total_pnl"] == 120.0
    assert s["avg_pnl"] == 40.0
    assert s["by_reason"] == {"tp": 1, "signal": 1, "timeout": 1}


def test_profit_factor() -> None:
    # 盈 160(100+60)/ 亏 40 = 4.0
    s = compute_managed_stats([_t("100", "tp"), _t("-40", "signal"), _t("60", "tp")])
    assert s["profit_factor"] == 4.0


def test_profit_factor_no_loss() -> None:
    # 无亏损 → 0.0(前端特判「∞」)
    s = compute_managed_stats([_t("100", "tp"), _t("60", "tp")])
    assert s["profit_factor"] == 0.0


def test_max_drawdown() -> None:
    # 权益曲线:+100 → 60(回 40)→ 160 → 110(回 50)· 峰 160 谷 110 → 最大回撤 50
    trades = [_t("100", "tp"), _t("-40", "signal"), _t("100", "tp"), _t("-50", "signal")]
    s = compute_managed_stats(trades)
    assert s["max_drawdown"] == 50.0
