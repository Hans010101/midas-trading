"""OxaPay 支付网关 client(Phase 2a · 会员订阅收款 · USDT 多链托管页)。

🔴 红线:只对接收款网关(建托管收款单 + 查单核验)· 不碰交易 · 不 import engine。
凭证 settings.oxapay_merchant_api_key 只从 env 读 · 绝不硬编码 / 绝不写进日志 / 不进返回。
错误信息只带 HTTP 码或异常类名(不带 URL/body,避免泄露凭证或敏感响应)。

与 Bcon 的差异:OxaPay 是【托管收款页】模型 —— 建单返回 payment_url(多链托管页,
用户自行选链/币),不分配单地址、不靠唯一金额尾数区分订单(订单靠 order_id/track_id 绑定)。
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class OxaPayError(Exception):  # noqa: N818 — 网关错误 · 调用方据此 502 / 回调忽略
    """OxaPay 网关调用失败(网络 / 非 2xx / 响应格式)。"""


def _headers() -> dict[str, str]:
    # ⚠ 凭证只在请求头用 · 绝不进日志 / 返回值
    return {"merchant_api_key": settings.oxapay_merchant_api_key}


async def create_invoice(
    order_id: str, amount_usdt: str, *, callback_url: str, sandbox: bool = False,
) -> tuple[str, str]:
    """创建托管收款单 · POST /v1/payment/invoice · 返回 (track_id, payment_url)。

    OxaPay 据 amount(USD 计价 · 托管页按当时汇率折算用户实付币种)+ order_id(我方订单号)
    建一张多链托管收款页;不指定单链/单币(用户在托管页自选链/币)。

    返回 (track_id, payment_url):
      track_id   = OxaPay 订单号(建单即存订单,回调/查单据此核对绑定);
      payment_url = 托管收款页(前端跳转,用户在此付款)。
    响应缺 track_id/payment_url → OxaPayError(端点转 502)。
    """
    body: dict[str, Any] = {
        "amount": float(amount_usdt),       # USD 计价金额(名义价 4.9/9.9/19.9)
        "currency": "USD",
        "lifetime": settings.oxapay_lifetime_minutes,
        "order_id": order_id,               # 我方订单号 · 回调按此命中 pending
        "callback_url": callback_url,       # OxaPay 到账 POST 此 URL(HMAC 验签)
        "description": "Midas Pro",
        "sandbox": sandbox,                 # True = 测试网不收真钱
        # 少付容差(百分比数字 · 3 = 3%)· 实付 ≥ 应付 ×97% 即判付清 · 吸收链上手续费不卡单
        "under_paid_coverage": settings.oxapay_under_paid_coverage,
    }
    data = await _request("POST", f"{settings.oxapay_api_base}/v1/payment/invoice", json=body)
    d = data.get("data") if isinstance(data, dict) else None
    if not isinstance(d, dict) or not d.get("track_id") or not d.get("payment_url"):
        raise OxaPayError("OxaPay create_invoice 响应缺 track_id/payment_url")
    return str(d["track_id"]), str(d["payment_url"])


async def get_payment(track_id: str) -> dict[str, Any]:
    """查单二次核验 · GET /v1/payment/{track_id} · 返回 data(真实 status/amount,防伪造回调)。"""
    data = await _request("GET", f"{settings.oxapay_api_base}/v1/payment/{track_id}")
    d = data.get("data") if isinstance(data, dict) else None
    if not isinstance(d, dict):
        raise OxaPayError("OxaPay get_payment 响应非对象")
    return d


async def _request(method: str, url: str, *, json: dict[str, Any] | None = None) -> Any:
    try:
        async with httpx.AsyncClient(timeout=settings.oxapay_timeout_seconds) as client:
            resp = await client.request(method, url, json=json, headers=_headers())
    except httpx.HTTPError as exc:
        raise OxaPayError(f"OxaPay 网络错: {type(exc).__name__}") from exc
    if not resp.is_success:
        raise OxaPayError(f"OxaPay HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise OxaPayError("OxaPay 响应非 JSON") from exc
