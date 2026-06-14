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
    external_id: str, amount_usdt: str, *, chain: str = "binance",
) -> tuple[str, str]:
    """创建收款地址 · POST /api/v2/address(USDT 直接计价 · 禁汇率换算)。

    ★ 方案 A(修 302):origin_amount/origin_currency 仍必填(基础订单参数 · 删了 → Bcon 302);
      payment_amount 是【覆盖】参数(优先于 origin · 禁自动换算 · 直接用指定值)→
      三者都传:origin 满足必填、payment_amount 覆盖换算 → 用户付精确 USDT 额(无零头)。
    返回 (address, amount_usdt):应付额用我方 USDT 额(权威值,不取 Bcon echo · 防零头)。
    """
    body = {
        "payment_currency": "USDT",
        "origin_amount": amount_usdt,    # 必填基础参数(改价前已验 200)· 被 payment_amount 覆盖
        "origin_currency": "USD",        # 必填
        "payment_amount": amount_usdt,   # ★ 覆盖换算 → 实付精确 USDT 额,无零头
        "external_id": external_id,
        "chain": chain,
    }
    data = await _request("POST", f"{settings.bcon_api_base}/api/v2/address", json=body)
    d = data.get("data") if isinstance(data, dict) else None
    if not isinstance(d, dict) or not d.get("address"):
        raise BconError("Bcon create_address 响应缺 address")
    # 应付额返我方精确 USDT 额(payment_amount 禁换算 · Bcon 应原样回显,但以我方为准防零头)
    return str(d["address"]), amount_usdt


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
