"""美股板块聚合单测(0023 阶段③ · 3.3)· 纯逻辑 · 不打网络。"""

from __future__ import annotations

from app.schemas.us_market import UsSpotRow
from app.services.us_market import aggregate_sectors


def _row(symbol: str, sector: str, change_pct: float, amount: float = 0.0) -> UsSpotRow:
    return UsSpotRow(
        symbol=symbol, name=symbol, sector=sector, last_price=10.0,
        change_pct=change_pct, amount=amount, volume=0.0,
    )


def test_aggregate_groups_and_sorts() -> None:
    rows = [
        _row("AAPL", "科技", 2.0, amount=100.0),
        _row("MSFT", "科技", 4.0, amount=200.0),
        _row("JPM", "金融", -1.0, amount=50.0),
        _row("BABA", "中概股", 5.0, amount=30.0),
    ]
    secs = aggregate_sectors(rows)
    # 按板块涨跌幅降序:中概股(5.0)> 科技(3.0 等权均值)> 金融(-1.0)
    assert [s.name for s in secs] == ["中概股", "科技", "金融"]
    tech = next(s for s in secs if s.name == "科技")
    assert tech.change_pct == 3.0  # noqa: PLR2004 ·(2+4)/2
    assert tech.stock_count == 2  # noqa: PLR2004
    assert tech.total_amount == 300.0  # noqa: PLR2004
    china = next(s for s in secs if s.name == "中概股")
    assert china.stock_count == 1


def test_aggregate_empty() -> None:
    assert aggregate_sectors([]) == []
