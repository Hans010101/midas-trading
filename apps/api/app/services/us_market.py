"""美股板块聚合 · 纯逻辑(0023 阶段③ · 3.3)· 可单测、不打网络。

按 sector 把策展池个股聚合成板块(行业 + 中概股):
- change_pct = 成分等权均值(板块内个股涨跌幅简单平均 · 透明 · 无需市值)
- stock_count = 成分数 · total_amount = 成分成交额(美元估)之和
美股无免费行业板块行情源,故板块由策展池按 sector 标签分组得出(口径透明)。
"""

from __future__ import annotations

from app.schemas.us_market import UsSector, UsSpotRow


def aggregate_sectors(rows: list[UsSpotRow]) -> list[UsSector]:
    """策展池个股 → 板块聚合(含「中概股」板块)· 按板块涨跌幅降序。"""
    by_sector: dict[str, list[UsSpotRow]] = {}
    for r in rows:
        by_sector.setdefault(r.sector, []).append(r)
    sectors = [
        UsSector(
            name=sector,
            change_pct=sum(m.change_pct for m in members) / len(members),
            stock_count=len(members),
            total_amount=sum(m.amount for m in members),
        )
        for sector, members in by_sector.items()
        if members
    ]
    sectors.sort(key=lambda s: s.change_pct, reverse=True)
    return sectors
