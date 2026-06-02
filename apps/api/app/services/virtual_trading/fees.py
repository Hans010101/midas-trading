"""滑点 + 手续费 · 0008 § 4 产品负责人决策表。

费率全部按各市场自己的货币算,不做 CNY 折算。
"""

from __future__ import annotations

from decimal import Decimal

from app.models.virtual import OrderSide

# 滑点(基点 · 1bp = 0.01%)
SLIPPAGE_BPS: dict[str, int] = {
    "cn": 5,       # A 股流动性 OK
    "us": 3,       # 美股流动性最好
    "crypto": 10,  # 加密波动大 + 撮合粒度小
    "hk": 5,       # 港股策展池为蓝筹 / 大型中概 · 流动性 OK · 同 A 股口径
}

# 手续费率(原币种 · 双向不对称 · A 股印花税仅卖)
# 港股(2026-06-02 产品负责人定):印花税 0.1% + 佣金 0.1% = 0.2% 综合(简化)·
#   港股印花税【买卖双边】均征(不同于 A 股仅卖)→ buy / sell 均 0.002 对称。
#   ★ 全程虚拟资金记账 · 不接真实券商通道(第一红线)。
#   ⚠️ 港交所 2025-12 在咨询「精简每手单位框架」· 费率 / 每手后续可能调整 · 此处集中配置易更新。
COMMISSION_RATES: dict[str, dict[OrderSide, Decimal]] = {
    "cn": {
        OrderSide.BUY: Decimal("0.0003"),
        OrderSide.SELL: Decimal("0.0013"),
    },
    "us": {
        OrderSide.BUY: Decimal("0"),
        OrderSide.SELL: Decimal("0"),
    },
    "crypto": {
        OrderSide.BUY: Decimal("0.001"),
        OrderSide.SELL: Decimal("0.001"),
    },
    "hk": {
        OrderSide.BUY: Decimal("0.002"),
        OrderSide.SELL: Decimal("0.002"),
    },
}


def commission_rate(market: str, side: OrderSide) -> Decimal:
    return COMMISSION_RATES[market][side]


def calc_commission(market: str, side: OrderSide, notional: Decimal) -> Decimal:
    """按 notional × 费率 算出佣金 · 四舍五入到 0.0001。"""
    rate = commission_rate(market, side)
    return (notional * rate).quantize(Decimal("0.0001"))


def apply_slippage(price: Decimal, market: str, side: OrderSide) -> Decimal:
    """滑点对成交价的影响:买价上浮,卖价下浮。"""
    bps = SLIPPAGE_BPS[market]
    factor = Decimal(bps) / Decimal("10000")
    if side == OrderSide.BUY:
        return price * (Decimal("1") + factor)
    return price * (Decimal("1") - factor)
