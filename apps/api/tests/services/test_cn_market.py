"""A股市场情绪聚合单测(0023 阶段③ · 3.2)· 纯逻辑 · 不打网络。

覆盖:板块涨跌幅上限判定(主板/ST/创业板/科创板/北交所)+ 涨跌平家数精确聚合 +
涨跌停按阈值估算。
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.schemas.cn_market import CnSpotRow
from app.services.cn_market import aggregate_breadth, board_limit_pct

_TS = datetime(2026, 5, 22, 7, 0, tzinfo=UTC)


def _row(symbol: str, name: str, change_pct: float, amount: float = 0.0) -> CnSpotRow:
    return CnSpotRow(
        symbol=symbol, name=name, last_price=10.0, change_pct=change_pct,
        change_amount=0.0, amount=amount, volume=0.0,
    )


# ── 板块涨跌幅上限 ────────────────────────────────────────────────────────────


def test_limit_main_board() -> None:
    assert board_limit_pct("600519", "贵州茅台") == 10.0  # noqa: PLR2004
    assert board_limit_pct("000001", "平安银行") == 10.0  # noqa: PLR2004


def test_limit_main_st() -> None:
    assert board_limit_pct("600001", "ST康美") == 5.0  # noqa: PLR2004
    assert board_limit_pct("000003", "*ST 国农") == 5.0  # noqa: PLR2004


def test_limit_growth_and_star() -> None:
    assert board_limit_pct("300750", "宁德时代") == 20.0  # noqa: PLR2004 · 创业板
    assert board_limit_pct("688981", "中芯国际") == 20.0  # noqa: PLR2004 · 科创板


def test_limit_bse() -> None:
    assert board_limit_pct("920000", "安徽凤凰") == 30.0  # noqa: PLR2004
    assert board_limit_pct("830799", "艾融软件") == 30.0  # noqa: PLR2004


# ── 涨跌家数 + 总成交额 ───────────────────────────────────────────────────────


def test_breadth_counts_exact() -> None:
    rows = [
        _row("600519", "茅台", 1.0, amount=100.0),
        _row("000001", "平安", -1.0, amount=200.0),
        _row("600000", "浦发", 0.0, amount=50.0),
        _row("600036", "招行", 2.5, amount=30.0),
    ]
    b = aggregate_breadth(rows, ts=_TS)
    assert b.up_count == 2  # noqa: PLR2004
    assert b.down_count == 1
    assert b.flat_count == 1
    assert b.total_amount == 380.0  # noqa: PLR2004
    assert b.ts == _TS


# ── 涨跌停估算(按板块阈值 · _LIMIT_EPS=0.2)──────────────────────────────────


def test_breadth_limit_estimate() -> None:
    rows = [
        _row("600519", "茅台", 9.95),    # 主板 ≥9.8 → 涨停
        _row("300750", "宁德", 19.9),    # 创业板 ≥19.8 → 涨停
        _row("688981", "中芯", 20.0),    # 科创板 ≥19.8 → 涨停
        _row("600001", "ST康美", -4.9),  # 主板 ST ≤-4.8 → 跌停
        _row("920000", "凤凰", -29.95),  # 北交所 ≤-29.8 → 跌停
        _row("000002", "万科", 5.0),     # 主板 +5% < 9.8 → 不算
    ]
    b = aggregate_breadth(rows, ts=_TS)
    assert b.limit_up_count == 3  # noqa: PLR2004
    assert b.limit_down_count == 2  # noqa: PLR2004
