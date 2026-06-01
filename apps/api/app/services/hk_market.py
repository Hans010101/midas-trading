"""港股市场情绪聚合 · 纯逻辑(港股首页全市场)· 可单测、不打网络。

- 涨跌平家数:全市场 spot 精确聚合(涨跌幅 >0 / <0 / =0)。
- ★ 港股**无涨跌停制度** → 不算涨跌停(对比 A股 `cn_market.aggregate_breadth` 的板块阈值估算)。
- 总成交额:全市场成交额累加(港币元)。
"""

from __future__ import annotations

from datetime import datetime

from app.schemas.hk_market import HkBreadth, HkSpotRow


def aggregate_breadth(rows: list[HkSpotRow], *, ts: datetime) -> HkBreadth:
    """全市场 spot → 情绪条(涨跌平家数 + 总成交额)· 港股无涨跌停。"""
    up = down = flat = 0
    total_amount = 0.0
    for r in rows:
        if r.change_pct > 0:
            up += 1
        elif r.change_pct < 0:
            down += 1
        else:
            flat += 1
        total_amount += r.amount
    return HkBreadth(
        ts=ts,
        up_count=up,
        down_count=down,
        flat_count=flat,
        total_amount=total_amount,
    )
