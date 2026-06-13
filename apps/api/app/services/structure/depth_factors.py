"""盘口深度因子(沙盘三期第二批 · 刀2)· 纯函数 · 可单测钉死,不依赖实时 CH。

🔴 红线:只读盘口结构 · 这里只算因子(前端/LLM 提示用),不撮合不预测价格。
本刀只产纯函数 + 读层 select(clickhouse_crypto.select_latest_depth);
沙盘接入(snapshot/prompts)留刀3 —— 本模块【不】import structure.snapshot / prompts。

口径(Hans 拍:先上两个稳健因子,挂单墙/斜率噪声大后置):
- spread 价差率 = (ask1 - bid1) / mid · mid=(ask1+bid1)/2 —— 即时流动性成本(越大越差)。
- imbalance 买卖盘失衡 = Σbid_qty / Σask_qty(全 10 档)—— >1 买盘厚 / <1 卖盘厚。
  全 10 档求和:补 0 档自然贡献 0 = 等价只算有效档 · 稳健,不依赖 X% 近档阈值。

脏数据如实留白:bid1/ask1 为 0 或缺档 → 因子返回 None(不伪造、不除零)。
"""

from __future__ import annotations

from app.schemas.crypto import OrderbookDepth


def best_bid_ask(depth: OrderbookDepth) -> tuple[float, float] | None:
    """取盘口一档 (bid1_price, ask1_price) · 任一 ≤0 或缺档 → None(脏数据留白)。"""
    bid1 = depth.bids[0][0] if depth.bids else 0.0
    ask1 = depth.asks[0][0] if depth.asks else 0.0
    if bid1 <= 0 or ask1 <= 0:
        return None
    return bid1, ask1


def spread_pct(depth: OrderbookDepth) -> float | None:
    """盘口价差率 = (ask1 - bid1) / mid · mid=(ask1+bid1)/2 · 即时流动性成本。

    返回小数(0.0005 = 0.05%)· bid1/ask1 任一 ≤0 或缺档 → None。
    """
    ba = best_bid_ask(depth)
    if ba is None:
        return None
    bid1, ask1 = ba
    mid = (ask1 + bid1) / 2
    if mid <= 0:
        return None
    return (ask1 - bid1) / mid


def imbalance(depth: OrderbookDepth) -> float | None:
    """买卖盘失衡 = Σbid_qty / Σask_qty(全 10 档)· >1 买盘厚 / <1 卖盘厚。

    需盘口存在(bid1/ask1 有效)否则 None · Σask_qty 为 0(单边空/缺档)→ None(不除零)。
    """
    if best_bid_ask(depth) is None:
        return None
    bid_sum = sum(qty for _, qty in depth.bids)
    ask_sum = sum(qty for _, qty in depth.asks)
    if ask_sum <= 0:
        return None
    return bid_sum / ask_sum
