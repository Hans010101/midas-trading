"""Bcon 支付网关 client(Phase 2a 刀1 · 会员订阅收款 · USDT/BSC)。

🔴 红线:只对接收款网关(创建收款地址 + 查单核验)· 不碰交易 · 不 import engine。
凭证 settings.bcon_api_key 只从 env 读 · 绝不硬编码 / 绝不写进日志 / 不进返回。
错误信息只带 HTTP 码或异常类名(不带 URL/body,避免泄露凭证或敏感响应)。
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class BconError(Exception):  # noqa: N818 — 网关错误 · 调用方据此 502 / 回调忽略
    """Bcon 网关调用失败(网络 / 非 2xx / 响应格式)。"""


def _headers() -> dict[str, str]:
    # ⚠ 凭证只在请求头用 · 绝不进日志 / 返回值
    return {"Authorization": f"Bearer {settings.bcon_api_key}"}


async def create_address(
    external_id: str, origin_amount: str, *, chain: str = "binance",
) -> tuple[str, str]:
    """创建收款地址 · POST /api/v2/address(USDT · origin USD)。

    返回 (address, payment_amount):address=收款地址 · payment_amount=用户应付精确额。
    """
    body = {
        "payment_currency": "USDT",
        "origin_amount": origin_amount,
        "origin_currency": "USD",
        "external_id": external_id,
        "chain": chain,
    }
    data = await _request("POST", f"{settings.bcon_api_base}/api/v2/address", json=body)
    d = data.get("data") if isinstance(data, dict) else None
    if not isinstance(d, dict) or not d.get("address") or not d.get("payment_amount"):
        raise BconError("Bcon create_address 响应缺 address/payment_amount")
    return str(d["address"]), str(d["payment_amount"])


async def get_transaction(txid: str) -> dict[str, Any]:
    """查单二次核验 · GET /api/v1/transactions/{txid} · 返回真实 status/sum(防伪造回调)。"""
    data = await _request("GET", f"{settings.bcon_api_base}/api/v1/transactions/{txid}")
    if not isinstance(data, dict):
        raise BconError("Bcon get_transaction 响应非对象")
    return data


async def _request(method: str, url: str, *, json: dict[str, Any] | None = None) -> Any:
    try:
        async with httpx.AsyncClient(timeout=settings.bcon_timeout_seconds) as client:
            resp = await client.request(method, url, json=json, headers=_headers())
    except httpx.HTTPError as exc:
        raise BconError(f"Bcon 网络错: {type(exc).__name__}") from exc
    if not resp.is_success:
        raise BconError(f"Bcon HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise BconError("Bcon 响应非 JSON") from exc
