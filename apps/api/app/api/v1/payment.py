"""会员订阅支付端点(Phase 2a · OxaPay USDT 多链托管收款)。

- POST /payment/order            · 建订单 + OxaPay 托管收款页(CurrentUserDep · 任意登录用户)
- GET  /payment/order/{id}/status · 查本人订单态(到账轮询 · 限本人)
- POST /payment/oxapay/callback   · OxaPay 到账回调(无鉴权 · HMAC-SHA512 验签防伪造 + 幂等)

🔴 红线:支付域只读写 payment_order + 调 extend_subscription(开 pro 权益)·
   【不 import virtual_trading/engine】(收订阅费非交易)· 凭证在 oxapay_client 内只从 env 读。
   回调验签是安全命门 · 用原始字节验签(不可 json 解析再序列化)· 验签失败一律拒。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, RequestLangDep
from app.core.database import get_db
from app.schemas.payment import CreateOrderIn, CreateOrderOut, OrderStatusOut
from app.services.i18n import translate
from app.services.payment.order import (
    create_payment_order,
    get_order_status,
    process_oxapay_callback,
)
from app.services.payment.oxapay_client import OxaPayError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["payment"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("/payment/order", response_model=CreateOrderOut)
async def create_order(
    payload: CreateOrderIn, current_user: CurrentUserDep, db: DbDep, lang: RequestLangDep,
) -> CreateOrderOut:
    """建会员订阅支付订单 → OxaPay 托管收款页(前端跳转此 URL,用户在托管页付款)。"""
    try:
        order, payment_url = await create_payment_order(
            db, current_user.id, payload.period,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OxaPayError as exc:
        # 网关暂不可用 · 不泄露内部细节(凭证/URL 不进响应)
        logger.warning("[payment.order] OxaPay 建单失败 user=%s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=502, detail=translate("payment.gateway_unavailable", lang),
        ) from exc
    return CreateOrderOut(
        payment_url=payment_url,
        external_id=order.external_id,
        period=order.period,
    )


@router.get("/payment/order/{external_id}/status", response_model=OrderStatusOut)
async def order_status(
    external_id: str, current_user: CurrentUserDep, db: DbDep, lang: RequestLangDep,
) -> OrderStatusOut:
    """查本人订单状态(前端到账轮询)· 限本人 · 不存在/非本人 → 404。"""
    order = await get_order_status(db, current_user.id, external_id)
    if order is None:
        raise HTTPException(status_code=404, detail=translate("payment.order_not_found", lang))
    return OrderStatusOut(
        external_id=order.external_id, status=order.status, period=order.period,
    )


@router.post("/payment/oxapay/callback")
async def oxapay_callback(request: Request, db: DbDep) -> PlainTextResponse:
    """OxaPay 到账回调 · ★ HMAC-SHA512 raw-body 验签(安全命门)+ 防伪造多重 + rowcount 幂等。

    ★ 必须用原始字节验签(json 解析再序列化会变字节 → 签名不符)· 验签在 process_oxapay_callback 内。
    成功 / 幂等忽略 / 状态非 paid / 业务拒绝 → 200 "ok"(避免 OxaPay 无谓重试,重试也不会变结果);
    仅【验签失败】→ 400(拒绝伪造/探测)· 结果只进日志,不据回调自带值开权益(只信查单)。
    """
    raw = await request.body()
    hmac_header = request.headers.get("HMAC")
    label = await process_oxapay_callback(db, raw_body=raw, hmac_header=hmac_header)
    logger.info("[payment.callback] result=%s", label)
    if label == "rejected: bad signature":
        return PlainTextResponse("rejected", status_code=400)
    return PlainTextResponse("ok", status_code=200)
