"""加密永续合约虚拟交易 · 费率 / 保证金 / 强平价 / 盈亏 纯函数 · ADR-0019 v2 §4。

单列在本文件(不并进 0008 fees.py),保持 0008 现货那套零改动。
全部 USDT 本位线性合约 · 纯函数,无 IO,便于单测逐项核数值。

🔴 红线:这些只是虚拟撮合的数学,绝不对应任何真实合约 / 真实资金。
"""

from __future__ import annotations

from decimal import Decimal

from app.models.perp import PerpSide

# ── 产品决策表(ADR-0019 §11 已审定)─────────────────────────────────────────
PERP_TAKER_FEE_RATE = Decimal("0.0005")  # D8 · 开/平按成交额 0.05% · 计入盈亏
PERP_SLIPPAGE_BPS = 10  # D8 · 滑点 10bp(与 0008 crypto 现货一致)
MAINTENANCE_MARGIN_RATE = Decimal("0.005")  # MMR 0.5% · 教学版全局常量(不分档)
MIN_LEVERAGE = 1
MAX_LEVERAGE = 20  # D3 · 虚拟杠杆上限 1–20x(教学防爆,不依赖 info.max_leverage stub)

# ── 量化精度 ──────────────────────────────────────────────────────────────
# USDT 金额对齐共用钱包 virtual_account.cash_balance 的 Numeric(20,4),零漂移
Q_MONEY = Decimal("0.0001")
# 数量 / 价格 / 强平价 = Numeric(20,8)
Q_PRICE = Decimal("0.00000001")


def q_money(v: Decimal) -> Decimal:
    """USDT 金额量化到 0.0001。"""
    return v.quantize(Q_MONEY)


def q_price(v: Decimal) -> Decimal:
    """价格 / 数量量化到 0.00000001。"""
    return v.quantize(Q_PRICE)


def apply_perp_slippage(mark: Decimal, *, is_buy: bool) -> Decimal:
    """滑点:买入(开多 / 平空)上浮,卖出(开空 / 平多)下浮。"""
    factor = Decimal(PERP_SLIPPAGE_BPS) / Decimal("10000")
    if is_buy:
        return q_price(mark * (Decimal("1") + factor))
    return q_price(mark * (Decimal("1") - factor))


def perp_taker_fee(notional: Decimal) -> Decimal:
    """taker 手续费 = 名义额 × 0.05% · USDT。"""
    return q_money(notional * PERP_TAKER_FEE_RATE)


def liquidation_price(
    entry_price: Decimal,
    leverage: int,
    side: PerpSide,
    *,
    mmr: Decimal = MAINTENANCE_MARGIN_RATE,
) -> Decimal:
    """逐仓简化强平价(忽略平仓手续费的闭式解 · ADR-0019 §4.5)。

    long :  entry × (1 − 1/lev + MMR)
    short:  entry × (1 + 1/lev − MMR)
    """
    inv_lev = Decimal("1") / Decimal(leverage)
    if side == PerpSide.LONG:
        liq = entry_price * (Decimal("1") - inv_lev + mmr)
    else:
        liq = entry_price * (Decimal("1") + inv_lev - mmr)
    if liq < Decimal("0"):
        liq = Decimal("0")  # 高杠杆下理论可能为负 · 钳到 0(永不为负价)
    return q_price(liq)


def unrealized_pnl(
    side: PerpSide, entry_price: Decimal, mark: Decimal, quantity: Decimal,
) -> Decimal:
    """浮动盈亏(USDT · 线性合约)· long:(mark−entry)×qty;short:(entry−mark)×qty。"""
    if side == PerpSide.LONG:
        return q_money((mark - entry_price) * quantity)
    return q_money((entry_price - mark) * quantity)


def realized_pnl_gross(
    side: PerpSide, entry_price: Decimal, exit_price: Decimal, quantity: Decimal,
) -> Decimal:
    """平仓已实现盈亏(未扣手续费 · USDT)· 公式同浮盈,exit 替 mark。"""
    if side == PerpSide.LONG:
        return q_money((exit_price - entry_price) * quantity)
    return q_money((entry_price - exit_price) * quantity)


def liquidation_distance_pct(mark: Decimal, liq_price: Decimal) -> Decimal:
    """强平距离% = |mark − liq| / mark × 100(给 UI / 策略④用)。"""
    if mark <= 0:
        return Decimal("0")
    return q_money(abs(mark - liq_price) / mark * Decimal("100"))
