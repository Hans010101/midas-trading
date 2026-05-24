"""加密永续合约 · 资金费结算 · ADR-0020 Block 1 · M2-C.2.2。

🔴 红线:全程【虚拟资金】· 资金费只是虚拟教学,绝不接真实资金费 / 转账 / 下单。
   worker 只读行情(premiumIndex 的 mark + rate + interval),结算走点金自己的逻辑。

设计(ADR-0020 §1.2 / §11):
- E3:每 UTC 整点扫,按每币各自周期对齐(`hour % interval == 0` 才结算该币),
  一个任务覆盖 1h/2h/4h/8h 全部周期。
- E4 = A:资金费【只扣虚拟现金余额 cash_balance,不联动强平】——
  即便扣为负也不因此强平(强平仍只看 mark vs liquidation_price,在强平 worker)。
- E5:每次结算写一行 virtual_perp_funding 流水(可复盘);position.funding_paid 累加。
- E9:rate>0 → 多头付、空头收(标准永续)。

不碰:M2-C.1 撮合/强平核心(本模块只加资金费,不改 perp_engine)· 0008 现货 ·
      M2-C.2.1 premium 采集 / 价源。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from app.models.perp import PerpSide, VirtualPerpFunding, VirtualPerpPosition
from app.models.virtual import VirtualAccount
from app.services.virtual_trading.perp_fees import q_money

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class PremiumSnapshot:
    """结算用的 per-symbol 行情快照(来自 crypto_premium_index 最新行)。

    mark_price / funding_rate 全用 Decimal(钱 = Decimal · 0002 教训);
    funding_interval_hours 来自 fundingInfo 慢刷(未列出默认 8)。
    """

    mark_price: Decimal
    funding_rate: Decimal
    funding_interval_hours: int


def funding_payment(
    side: PerpSide, rate: Decimal, mark: Decimal, quantity: Decimal,
) -> Decimal:
    """资金费【支付额】(USDT · 有符号)· 正 = 该仓付出(现金减少),负 = 收到(现金增加)。

    标准永续(E9):rate>0 → 多头付、空头收。
      payment = sign × rate × mark × qty,sign(long)=+1, sign(short)=−1。
    结算时:cash_balance -= payment;position.funding_paid += payment。
    - long, rate>0 → payment>0(多头付)· short, rate>0 → payment<0(空头收)
    - rate<0 时方向反转(long 收 / short 付),符号自洽。
    """
    sign = Decimal(1) if side == PerpSide.LONG else Decimal(-1)
    return q_money(sign * rate * mark * quantity)


def aligned_for_settlement(interval_hours: int, hour: int) -> bool:
    """该币在本整点是否结算 · `hour % interval == 0`(UTC 整点对齐 · E3)。

    interval=8 → 0/8/16;4 → 0/4/8/12/16/20;2 → 偶数点;1 → 每点。
    interval<=0 视为非法 → 不结算(兜底,绝不除零)。
    """
    if interval_hours <= 0:
        return False
    return hour % interval_hours == 0


async def settle_funding(
    session: AsyncSession,
    premium_by_symbol: dict[str, PremiumSnapshot],
    *,
    now: datetime,
) -> dict[str, int]:
    """对所有活仓在【对齐其各自周期】的整点结算资金费(E3/E4=A/E5)。

    - 只结算 `now.hour % interval == 0` 的币(按 premium 的 funding_interval_hours);
    - 取不到 premium(无 mark)→ 跳过该仓(不猜价、不结算);
    - cash_balance -= payment(原子 UPDATE · 防与下单丢更新 · 允许为负 · E4=A 不强平);
    - position.funding_paid += payment;写一行 virtual_perp_funding 流水;
    - 幂等:(position_id, funding_ts) 已存在则跳过(beat 重触发 / 重试不重复扣)。

    funding_ts = now 对齐到整点(分秒清零)· 作流水幂等键。
    调用方(worker)负责 commit。返回 {settled, skipped, charged_negative}。
    """
    hour = now.hour
    funding_ts = now.replace(minute=0, second=0, microsecond=0)

    positions = (
        await session.scalars(
            select(VirtualPerpPosition).where(
                VirtualPerpPosition.closed_at.is_(None),
            ),
        )
    ).all()

    settled = 0
    skipped = 0
    for p in positions:
        snap = premium_by_symbol.get(p.symbol)
        if snap is None or snap.mark_price <= 0:
            skipped += 1
            continue
        if not aligned_for_settlement(snap.funding_interval_hours, hour):
            continue
        # 幂等 · 本结算整点已结过则跳过
        dup = await session.scalar(
            select(VirtualPerpFunding.id).where(
                VirtualPerpFunding.position_id == p.id,
                VirtualPerpFunding.funding_ts == funding_ts,
            ),
        )
        if dup is not None:
            continue

        payment = funding_payment(p.side, snap.funding_rate, snap.mark_price, p.quantity)

        # 原子扣现金(允许为负 · E4=A 不联动强平)· 用 SQL 表达式避免与并发下单丢更新
        await session.execute(
            update(VirtualAccount)
            .where(VirtualAccount.id == p.account_id)
            .values(cash_balance=VirtualAccount.cash_balance - payment),
        )
        p.funding_paid = q_money(p.funding_paid + payment)
        session.add(
            VirtualPerpFunding(
                account_id=p.account_id,
                position_id=p.id,
                symbol=p.symbol,
                side=p.side,
                funding_rate=snap.funding_rate,
                mark_price=snap.mark_price,
                quantity=p.quantity,
                payment=payment,
                funding_ts=funding_ts,
                settled_at=now,
            ),
        )
        settled += 1

    return {"settled": settled, "skipped": skipped}
