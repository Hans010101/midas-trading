"""飞书自定义机器人 webhook client · 0009 § 2.1。

安全模式:自定义关键词「点金」· 由 templates.py 保证消息含此字样。
"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

logger = logging.getLogger(__name__)


class FeishuApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"Feishu {status}: {detail}")
        self.status = status
        self.detail = detail


async def send(
    webhook_url: str,
    payload: dict[str, Any],
    *,
    timeout: float = 5.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """POST payload 到飞书 webhook · 返回响应 JSON · 失败抛 FeishuApiError。

    成功响应:`{"StatusCode": 0, ...}`(注意飞书用 StatusCode 不是 status_code)
    关键词未命中:`{"StatusCode": 19021, "StatusMessage": "Key Words Not Found"}`
    """
    owned = client is None
    if owned:
        client = httpx.AsyncClient(timeout=timeout)
    assert client is not None

    try:
        resp = await client.post(webhook_url, json=payload)
    except httpx.HTTPError as e:
        msg = f"网络错误:{e}"
        raise FeishuApiError(0, msg) from e
    finally:
        if owned:
            await client.aclose()

    if resp.status_code != 200:
        raise FeishuApiError(resp.status_code, resp.text[:200])

    try:
        body = resp.json()
    except ValueError as e:
        raise FeishuApiError(200, "响应不是有效 JSON") from e

    # 飞书业务码:0 表示成功;非 0 表示业务失败(关键词不匹配 / webhook 失效 / ...)
    status_code = body.get("StatusCode") or body.get("code", 0)
    if status_code != 0:
        detail = body.get("StatusMessage") or body.get("msg", "未知错误")
        raise FeishuApiError(status_code, str(detail))

    return cast(dict[str, Any], body)
