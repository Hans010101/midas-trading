"""会员订阅支付端点(Phase 2a 刀1 · Bcon USDT/BSC)。

- POST /payment/order          · 建订单 + Bcon 收款地址(CurrentUserDep · 任意登录用户)
- GET  /payment/bcon/callback  · Bcon 到账回调(无鉴权 · Bcon 调 · 防伪造三重 + 幂等 · 恒返 200)

🔴 红线:支付域只读写 payment_order + 调 extend_subscription(开 pro 权益)·
   【不 import virtual_trading/engine】(收订阅费非交易)· 凭证在 bcon_client 内只从 env 读不入日志。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.core.database import get_db
from app.schemas.payment import CreateOrderIn, CreateOrderOut, OrderStatusOut
from app.services.payment.bcon_client import BconError
from app.services.payment.order import (
    create_payment_order,
    get_order_status,
    process_bcon_callback,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["payment"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("/payment/order", response_model=CreateOrderOut)
async def create_order(
    payload: CreateOrderIn, current_user: CurrentUserDep, db: DbDep,
) -> CreateOrderOut:
    """建会员订阅支付订单 → Bcon 收款地址(前端据此展示收款二维码/地址)。"""
    try:
        order, payment_amount = await create_payment_order(
            db, current_user.id, payload.period,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BconError as exc:
        # 网关暂不可用 · 不泄露内部细节(凭证/URL 不进响应)
        logger.warning("[payment.order] Bcon 建单失败 user=%s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=502, detail="支付网关暂不可用,请稍后重试",
        ) from exc
    return CreateOrderOut(
        address=order.pay_address or "",
        payment_amount=payment_amount,
        external_id=order.external_id,
        period=order.period,
    )


@router.get("/payment/order/{external_id}/status", response_model=OrderStatusOut)
async def order_status(
    external_id: str, current_user: CurrentUserDep, db: DbDep,
) -> OrderStatusOut:
    """查本人订单状态(前端到账轮询)· 限本人 · 不存在/非本人 → 404。"""
    order = await get_order_status(db, current_user.id, external_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    return OrderStatusOut(
        external_id=order.external_id, status=order.status, period=order.period,
    )


@router.get("/payment/bcon/callback")
async def bcon_callback(
    db: DbDep,
    status: str | None = None,
    addr: str | None = None,
    txid: str | None = None,
    external_id: str | None = None,
) -> Response:
    """Bcon 到账回调 · 防伪造三重(status==2 + 查单金额 + external_id)+ rowcount 幂等。

    恒返 200(Bcon 要求 = 已收到)· 处理结果只进日志,不据回调自带 value 开权益(只信查单)。
    """
    label = await process_bcon_callback(
        db, status=status, txid=txid, external_id=external_id, addr=addr,
    )
    logger.info("[payment.callback] result=%s", label)
    return Response(status_code=200, content="ok")
