"""智能交易 PR-6 · 前向测试统计纯函数测(胜率/盈亏比/回撤/by_reason/★by_side 做多做空)。

★纯函数本地真跑(无 DB)· 吸取「本地能跑必真跑」。
"""

from __future__ import annotations

from decimal import Decimal

from app.services.virtual_trading.intelligent.stats import (
    ClosedIntelligentTrade,
    compute_intelligent_stats,
)


def _t(pnl: str, reason: str, side: str) -> ClosedIntelligentTrade:
    return ClosedIntelligentTrade(realized_pnl=Decimal(pnl), close_reason=reason, side=side)


def test_empty() -> None:
    s = compute_intelligent_stats([])
    assert s["total_trades"] == 0
    assert s["win_rate"] == 0.0
    assert s["by_reason"] == {"stop_loss": 0, "take_profit": 0, "signal_reversal": 0}
    assert s["by_side"] == {"long": 0, "short": 0}


def test_win_rate_and_pnl() -> None:
    trades = [
        _t("100", "take_profit", "long"),
        _t("-50", "stop_loss", "short"),
        _t("80", "take_profit", "long"),
        _t("-20", "signal_reversal", "short"),
    ]
    s = compute_intelligent_stats(trades)
    assert s["total_trades"] == 4
    assert s["wins"] == 2
    assert s["losses"] == 2
    assert s["win_rate"] == 0.5
    assert s["total_pnl"] == 110.0  # 100−50+80−20
    assert s["avg_pnl"] == 27.5


def test_profit_factor() -> None:
    # 总盈利 180 / 总亏损 70 = 2.5714
    trades = [_t("100", "take_profit", "long"), _t("80", "take_profit", "long"),
              _t("-70", "stop_loss", "short")]
    s = compute_intelligent_stats(trades)
    assert s["profit_factor"] == round(180 / 70, 4)


def test_profit_factor_no_loss() -> None:
    # 无亏损 → 0.0(前端特判「无穷大」)
    s = compute_intelligent_stats([_t("100", "take_profit", "long")])
    assert s["profit_factor"] == 0.0


def test_max_drawdown() -> None:
    # 权益曲线:+100 → +50(回撤50)→ +130 → +30(回撤100)· 最大回撤=100
    trades = [_t("100", "take_profit", "long"), _t("-50", "stop_loss", "short"),
              _t("80", "take_profit", "long"), _t("-100", "stop_loss", "short")]
    s = compute_intelligent_stats(trades)
    assert s["max_drawdown"] == 100.0


def test_by_reason_three_exits() -> None:
    # ★intelligent 三退出分类(managed 的 tp/signal/timeout 不在这里)
    trades = [
        _t("10", "stop_loss", "long"), _t("10", "stop_loss", "short"),
        _t("10", "take_profit", "long"),
        _t("10", "signal_reversal", "short"),
    ]
    s = compute_intelligent_stats(trades)
    assert s["by_reason"] == {"stop_loss": 2, "take_profit": 1, "signal_reversal": 1}


def test_by_side_long_short() -> None:
    # ★做多做空拆分(intelligent 特有)
    trades = [
        _t("10", "take_profit", "long"), _t("10", "take_profit", "long"),
        _t("10", "take_profit", "long"),
        _t("-10", "stop_loss", "short"), _t("-10", "stop_loss", "short"),
    ]
    s = compute_intelligent_stats(trades)
    assert s["by_side"] == {"long": 3, "short": 2}
