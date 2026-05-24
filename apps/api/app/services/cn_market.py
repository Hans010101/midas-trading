"""A股市场情绪聚合 · 纯逻辑(0023 阶段③ · 3.2)· 可单测、不打网络。

- 涨跌平家数:全市场 spot 精确聚合(涨跌幅 >0 / <0 / =0)。
- 涨跌停家数:**估算** · 东财涨跌停池(stock_zt_pool_em)本地不可达,改用「按板块涨跌幅
  阈值」估:个股涨跌幅触及所在板块价格涨跌幅上限(留 _LIMIT_EPS 收盘四舍五入容差)即记一笔。
  口径在 CnBreadth 字段说明 + 前端文案标注。板块上限:
    · 主板(沪 60 / 深 00):±10%(ST/*ST:±5%)
    · 创业板(30)/ 科创板(688):±20%
    · 北交所(8/4/920…):±30%
"""

from __future__ import annotations

from datetime import datetime

from app.schemas.cn_market import CnBreadth, CnSpotRow

# 收盘价四舍五入容差:涨停收盘价对应涨跌幅常为 9.9x%~10.0x%,留 0.2 缓冲少漏。
_LIMIT_EPS = 0.2

_LIMIT_STAR = 5.0
_LIMIT_MAIN = 10.0
_LIMIT_GROWTH = 20.0  # 创业板 / 科创板
_LIMIT_BSE = 30.0     # 北交所


def board_limit_pct(symbol: str, name: str) -> float:
    """个股所在板块的价格涨跌幅上限(%)· symbol 为纯代码(去 sh/sz/bj 前缀)。"""
    if symbol.startswith(("688", "300")):
        return _LIMIT_GROWTH
    if symbol.startswith(("8", "4", "920")):
        return _LIMIT_BSE
    # 主板(沪 60 / 深 00):ST/*ST 为 ±5%,其余 ±10%
    return _LIMIT_STAR if "ST" in name.upper() else _LIMIT_MAIN


def aggregate_breadth(rows: list[CnSpotRow], *, ts: datetime) -> CnBreadth:
    """全市场 spot → 情绪条(涨跌平家数精确 + 涨跌停估算 + 总成交额)。"""
    up = down = flat = limit_up = limit_down = 0
    total_amount = 0.0
    for r in rows:
        if r.change_pct > 0:
            up += 1
        elif r.change_pct < 0:
            down += 1
        else:
            flat += 1
        total_amount += r.amount
        lim = board_limit_pct(r.symbol, r.name)
        if r.change_pct >= lim - _LIMIT_EPS:
            limit_up += 1
        elif r.change_pct <= -(lim - _LIMIT_EPS):
            limit_down += 1
    return CnBreadth(
        ts=ts,
        up_count=up,
        down_count=down,
        flat_count=flat,
        limit_up_count=limit_up,
        limit_down_count=limit_down,
        total_amount=total_amount,
    )
