"""支付订单业务(Phase 2a 刀1 · 建单 + 回调核验开权益)。

🔴 红线:支付域【不 import virtual_trading/engine】(收订阅费非交易)·
开权益走 growth.extend_subscription(source='paid' · 不传 cap_days = 不封顶 · 复用 pro 档额度)。

建单 = 生成不可猜 external_id → Bcon 建收款地址 → 存 pending(Bcon 失败回滚,无残留);
回调 = ★ 防伪造三重(status==2 + 查单真实金额≥应付 + external_id 命中 pending)+ rowcount 幂等。
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment_order import PaymentOrder
from app.services.growth import extend_subscription
from app.services.membership import PERIOD_DAYS
from app.services.payment.bcon_client import BconError, create_address, get_transaction

logger = logging.getLogger(__name__)

# 各周期 USDT【直接计价】(Hans 拍)· 与 USD 无关 · 不换算不取整 · 显示=转账=到账同一数
PRICE_USDT: dict[str, str] = {"month": "4.9", "quarter": "9.9", "year": "19.9"}
_PLAN = "pro"


async def create_payment_order(
    db: AsyncSession, user_id: UUID, period: str, *, chain: str = "binance",
) -> tuple[PaymentOrder, str]:
    """建 pending 订单 → Bcon 建收款地址 → 回填 pay_address。返回 (order, payment_amount)。

    period 非法 → ValueError(端点转 400);Bcon 失败 → BconError(端点转 502 · get_db 回滚无残留)。
    """
    if period not in PRICE_USDT:
        msg = f"未知周期: {period}"
        raise ValueError(msg)
    amount = PRICE_USDT[period]
    external_id = secrets.token_urlsafe(24)  # 不可猜 · 给 Bcon + 回调匹配键
    order = PaymentOrder(
        external_id=external_id, user_id=user_id, plan=_PLAN, period=period,
        amount_usdt=Decimal(amount), chain=chain, status="pending",
    )
    db.add(order)
    await db.flush()
    # 调 Bcon 建收款地址 · 失败抛 BconError → 端点 502 → get_db 回滚 · 无 pending 残留
    address, payment_amount = await create_address(external_id, amount, chain=chain)
    order.pay_address = address
    await db.commit()
    return order, payment_amount


async def get_order_status(
    db: AsyncSession, user_id: UUID, external_id: str,
) -> PaymentOrder | None:
    """查本人订单(前端到账轮询用)· 限本人(user_id 过滤,不泄露他人订单)· 无则 None。"""
    order: PaymentOrder | None = await db.scalar(
        select(PaymentOrder).where(
            PaymentOrder.external_id == external_id,
            PaymentOrder.user_id == user_id,
        ),
    )
    return order


async def process_bcon_callback(
    db: AsyncSession, *, status: str | None, txid: str | None,
    external_id: str | None, addr: str | None = None,
) -> str:
    """Bcon 回调处理 · 返回结果标签(端点恒返 200,标签仅日志)。

    ★ 防伪造三重(+ addr 交叉守卫):
      ① status==2(confirmed)才处理;② external_id 命中 pending 订单(不可猜 · 不存在/已付忽略);
      ③ 查单二次核验:独立向 Bcon 查真实金额 ≥ 订单应付额(防伪造回调);
      (+ addr 若与订单收款地址不符 → 拒,防拿别单 txid 套现)。
    rowcount 幂等:pending→paid 只成功一次 → 同回调重复只开一次权益。
    """
    if not external_id or not txid:
        return "ignored: missing external_id/txid"
    if status != "2":  # 只处理 confirmed(partial/unconfirmed 等后续 confirmed 回调)
        return f"ignored: status={status} not confirmed"

    order = await db.scalar(
        select(PaymentOrder).where(
            PaymentOrder.external_id == external_id,
            PaymentOrder.status == "pending",
        ),
    )
    if order is None:  # 不存在 / 已 paid → 幂等忽略
        return "ignored: no pending order"

    # addr 交叉守卫:回调收款地址须与建单时 Bcon 返回的一致(防拿别单 txid 套现)
    if addr and order.pay_address and addr.lower() != order.pay_address.lower():
        logger.warning(
            "[payment.callback] addr 不符 ext=%s cb=%s order=%s",
            external_id, addr, order.pay_address,
        )
        return "rejected: addr mismatch"

    # ★ 查单二次核验(防伪造:独立向 Bcon 查真实金额,不信回调自带 value)
    try:
        tx = await get_transaction(txid)
    except BconError as exc:
        logger.warning("[payment.callback] get_transaction 失败 ext=%s: %s", external_id, exc)
        return "ignored: verify failed"
    real_amount = _tx_amount(tx)
    if real_amount is None or real_amount < order.amount_usdt:
        logger.warning(
            "[payment.callback] 金额核验不足 ext=%s real=%s need=%s",
            external_id, real_amount, order.amount_usdt,
        )
        return "rejected: amount insufficient"

    # ★ 幂等闸:pending→paid 只成功一次(照 redeem returning+first 范式 · 并发/重复回调只开一次)
    res = await db.execute(
        update(PaymentOrder)
        .where(PaymentOrder.external_id == external_id, PaymentOrder.status == "pending")
        .values(status="paid", gateway_txid=txid, paid_at=datetime.now(UTC))
        .returning(PaymentOrder.id),
    )
    if res.first() is None:  # pending 行已被另一回调抢走(竞态)→ 已付,只开一次
        return "ignored: already paid (race)"

    # 开权益(同事务原子)· source='paid' 不传 cap_days = 不封顶
    await extend_subscription(db, order.user_id, PERIOD_DAYS[order.period], "paid")
    await db.commit()
    logger.info(
        "[payment.callback] paid ext=%s user=%s period=%s",
        external_id, order.user_id, order.period,
    )
    return "paid"


def _tx_amount(tx: dict[str, Any]) -> Decimal | None:
    """从查单响应提真实金额(defensive:data.sum / sum / value / payment_amount)· 非数 None。"""
    candidates: list[Any] = []
    data = tx.get("data")
    if isinstance(data, dict):
        candidates += [data.get("sum"), data.get("value"), data.get("payment_amount")]
    candidates += [tx.get("sum"), tx.get("value")]
    for c in candidates:
        if c is None:
            continue
        try:
            return Decimal(str(c))
        except (InvalidOperation, ValueError):
            continue
    return None
