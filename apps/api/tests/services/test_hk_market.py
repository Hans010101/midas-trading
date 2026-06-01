"""港股市场情绪聚合单测(港股首页全市场)· 纯逻辑 · 不打网络。

覆盖:涨跌平家数精确聚合 + 总成交额。★港股无涨跌停制度 → 无 limit 估算(对比 cn_market)。
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.schemas.hk_market import HkSpotRow
from app.services.hk_market import aggregate_breadth

_TS = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)


def _row(symbol: str, name: str, change_pct: float, amount: float = 0.0) -> HkSpotRow:
    return HkSpotRow(
        symbol=symbol, name=name, last_price=10.0, change_pct=change_pct,
        change_amount=0.0, amount=amount, volume=0.0,
    )


def test_breadth_counts_exact() -> None:
    rows = [
        _row("00700", "腾讯控股", 1.0, amount=100.0),
        _row("09988", "阿里巴巴-W", -1.0, amount=200.0),
        _row("00005", "汇丰控股", 0.0, amount=50.0),
        _row("03690", "美团-W", 2.5, amount=30.0),
    ]
    b = aggregate_breadth(rows, ts=_TS)
    assert b.up_count == 2  # noqa: PLR2004
    assert b.down_count == 1
    assert b.flat_count == 1
    assert b.total_amount == 380.0  # noqa: PLR2004
    assert b.ts == _TS


def test_breadth_empty() -> None:
    b = aggregate_breadth([], ts=_TS)
    assert b.up_count == 0
    assert b.down_count == 0
    assert b.flat_count == 0
    assert b.total_amount == 0.0


def test_breadth_no_limit_fields() -> None:
    """★港股 HkBreadth 不含涨跌停字段(对比 CnBreadth · 港股无涨跌停制度)。"""
    b = aggregate_breadth([_row("00700", "腾讯", 30.0)], ts=_TS)
    assert not hasattr(b, "limit_up_count")
    assert not hasattr(b, "limit_down_count")
