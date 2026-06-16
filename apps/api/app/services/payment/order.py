"""支付订单业务(Phase 2a · 建单 + 回调核验开权益 · OxaPay 托管收款)。

🔴 红线:支付域【不 import virtual_trading/engine】(收订阅费非交易)·
开权益走 growth.extend_subscription(source='paid' · 不传 cap_days = 不封顶 · 复用 pro 档额度)。

建单 = 生成不可猜 external_id → OxaPay 建托管收款单 → 存 pending + track_id(失败回滚,无残留);
回调 = ★ 防伪造多重(① HMAC-SHA512 raw-body 验签 = 安全命门 → ② 命中 pending →
       ③ track_id 绑定建单值 → ④ 独立查单真实 status=paid & 金额≥应付)+ rowcount 幂等。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.payment_order import PaymentOrder
from app.services.growth import extend_subscription
from app.services.membership import PERIOD_DAYS
from app.services.payment.oxapay_client import OxaPayError, create_invoice, get_payment

logger = logging.getLogger(__name__)

# 各周期 USDT【直接计价】(Hans 拍)· 与 USD 无关 · 不换算不取整 · 显示=转账=到账同一数
PRICE_USDT: dict[str, str] = {"month": "4.9", "quarter": "9.9", "year": "19.9"}
_PLAN = "pro"


async def create_payment_order(
    db: AsyncSession, user_id: UUID, period: str,
) -> tuple[PaymentOrder, str]:
    """建 pending 订单 → OxaPay 托管收款单 → 回填 pay_address/gateway_txid(URL/track_id)。

    ★ OxaPay 托管页模型 · 无唯一尾数:amount_usdt 存【名义价】(4.9/9.9/19.9 · USD 计价)=
      查单核验基准;track_id 建单即存进 gateway_txid(回调时核对绑定,防拿别单 track_id 套现)。
    period 非法 → ValueError(端点转 400);OxaPay 失败 → OxaPayError(端点转 502 · get_db 回滚无残留)。
    """
    if period not in PRICE_USDT:
        msg = f"未知周期: {period}"
        raise ValueError(msg)
    nominal = PRICE_USDT[period]  # 名义价(USD 计价)· 传 OxaPay · 查单核验基准
    external_id = secrets.token_urlsafe(24)  # 不可猜 · 给 OxaPay order_id + 回调匹配键
    order = PaymentOrder(
        external_id=external_id, user_id=user_id, plan=_PLAN, period=period,
        amount_usdt=Decimal(nominal), chain="multi", status="pending",  # 多链 · 名义价即核验额
    )
    db.add(order)
    await db.flush()
    # 回调 URL · 复用 public_api_base_url(prod = https://api.midastrade.asia)
    callback_url = f"{settings.public_api_base_url.rstrip('/')}/api/v1/payment/oxapay/callback"
    # 调 OxaPay 建托管收款单 · 失败抛 OxaPayError → 端点 502 → get_db 回滚 · 无 pending 残留
    track_id, payment_url = await create_invoice(
        external_id, nominal, callback_url=callback_url, sandbox=settings.oxapay_sandbox,
    )
    order.pay_address = payment_url   # 复用 pay_address 字段存托管收款页 URL(前端跳转)
    order.gateway_txid = track_id     # ★ 建单即存 track_id · 回调核对绑定(防伪造)
    await db.commit()
    return order, payment_url


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


async def process_oxapay_callback(
    db: AsyncSession, *, raw_body: bytes, hmac_header: str | None,
) -> str:
    """OxaPay 回调处理 · 返回结果标签(端点据标签返 200/400,标签仅日志)。

    ★ 防伪造多重(① 验签 = 安全命门):
      ① HMAC-SHA512(raw_body, merchant_api_key).hexdigest() == HMAC 头(常量时间比对)·
         ★ 必须用【原始字节】验签(json 解析再序列化会变字节 → 签名不符)· 验签后才解析;
      ② status.lower()=="paid" 才开权益(Paying 等中间态忽略);
      ③ order_id 命中 pending 订单(不可猜 · 不存在/已付忽略);
      ④ track_id 须 == 建单存的 gateway_txid(防拿别单 track_id 套现);
      ⑤ 独立查单二次核验:OxaPay 真实 status=paid 且真实金额 ≥ 订单应付额(防伪造回调)。
    rowcount 幂等:pending→paid 只成功一次 → 同回调重复只开一次权益。
    """
    # ① ★ 验签(安全命门)· 用原始字节 · 常量时间比对 · 失败一律拒(端点转 400)
    key = settings.oxapay_merchant_api_key
    calc = hmac.new(key.encode(), raw_body, hashlib.sha512).hexdigest()
    if not hmac_header or not hmac.compare_digest(calc, hmac_header):
        logger.warning("[payment.callback] 验签失败(拒绝伪造)")
        return "rejected: bad signature"

    # 验签通过后才解析 body(顺序不可换:解析在前会给攻击者免费解析)
    try:
        body = json.loads(raw_body)
    except (ValueError, TypeError):
        return "rejected: bad json"
    if not isinstance(body, dict):
        return "rejected: bad json"

    order_id = body.get("order_id")
    status = str(body.get("status") or "")
    track_id = body.get("track_id")

    # ② 状态:只处理 paid(大小写不敏感 · OxaPay 回调 "Paid" / 查单 "paid")· Paying 等中间态忽略
    if status.lower() != "paid":
        return f"ignored: status={status} not paid"
    if not order_id or not track_id:
        return "ignored: missing order_id/track_id"

    # ③ 命中 pending 订单(不可猜 external_id · 不存在/已付 → 幂等忽略)
    order = await db.scalar(
        select(PaymentOrder).where(
            PaymentOrder.external_id == order_id,
            PaymentOrder.status == "pending",
        ),
    )
    if order is None:
        return "ignored: no pending order"

    # ④ track_id 绑定守卫:回调 track_id 须与建单存的 gateway_txid 一致(防拿别单 track_id 套现)
    if str(track_id) != str(order.gateway_txid or ""):
        logger.warning(
            "[payment.callback] track_id 不符 ext=%s cb=%s order=%s",
            order_id, track_id, order.gateway_txid,
        )
        return "rejected: track_id mismatch"

    # ⑤ ★ 查单二次核验(防伪造:独立向 OxaPay 查真实 status/金额,不信回调自带值)
    try:
        info = await get_payment(str(track_id))
    except OxaPayError as exc:
        logger.warning("[payment.callback] get_payment 失败 ext=%s: %s", order_id, exc)
        return "ignored: verify failed"
    real_status = str(info.get("status") or "")
    real_amount = _oxapay_amount(info)
    if real_status.lower() != "paid" or real_amount is None or real_amount < order.amount_usdt:
        logger.warning(
            "[payment.callback] 核验不足 ext=%s real_status=%s real_amt=%s need=%s",
            order_id, real_status, real_amount, order.amount_usdt,
        )
        return "rejected: amount/status insufficient"

    # ★ 幂等闸:pending→paid 只成功一次(照 redeem returning+first 范式 · 并发/重复回调只开一次)·
    #   gateway_txid 建单时已存 track_id,此处不覆写
    res = await db.execute(
        update(PaymentOrder)
        .where(PaymentOrder.external_id == order_id, PaymentOrder.status == "pending")
        .values(status="paid", paid_at=datetime.now(UTC))
        .returning(PaymentOrder.id),
    )
    if res.first() is None:  # pending 行已被另一回调抢走(竞态)→ 已付,只开一次
        return "ignored: already paid (race)"

    # 开权益(同事务原子)· source='paid' 不传 cap_days = 不封顶
    await extend_subscription(db, order.user_id, PERIOD_DAYS[order.period], "paid")
    await db.commit()
    logger.info(
        "[payment.callback] paid ext=%s user=%s period=%s",
        order_id, order.user_id, order.period,
    )
    return "paid"


def _oxapay_amount(info: dict[str, Any]) -> Decimal | None:
    """从查单 data 提真实金额(OxaPay data.amount · USD 计价)· 非数 None。"""
    raw = info.get("amount")
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
