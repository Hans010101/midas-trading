"""币安广场 adapter(发布层 PR-2 · 真 API)。

POST https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add
  Header: X-Square-OpenAPI-Key=<key> · Content-Type: application/json · clienttype: binanceSkill
  Body:  {"bodyTextOnly": <text>}(官方文档纯文本 · ★图片支持待 Hans 拿 Key 实测 uploads 端点)
  响应:币安 bapi 标准信封 {code, success, data, message}· 成功 success=true 或 code="000000"。

★凭证 settings.binance_square_openapi_key 只进 Header · 绝不进日志/error/返回(同 oxapay 范式)。
★publish 永不 raise:网络/非2xx/非JSON/业务错/意外 → 返回 PublishResult(success=False, error=...)
  → run_publish 据此标 dispatch failed,绝不让 worker 崩。
★响应里帖子 id/url 的【确切字段】官方文档没给全 → 防御性多路提取 + INFO 记 code/success/data,
  Hans 首次真发后据实校准(若 id 字段名不同,改 _parse 的提取即可)。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.services.x_marketing.publish.base import PublishAdapter, PublishResult

logger = logging.getLogger(__name__)

_ENDPOINT = "https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add"
_TIMEOUT_S = 20.0
_SUCCESS_CODES = ("000000", "0")


class BinanceSquareError(Exception):  # noqa: N818 — 传输错 · publish 据此转 failed
    """币安广场调用传输失败(网络 / 非 2xx / 非 JSON)。"""


async def _post_content(text: str) -> dict[str, Any]:
    """POST 文本到币安广场 · 返回响应 JSON dict · 传输失败抛 BinanceSquareError。

    ★凭证只在 Header · 错误只带 HTTP 码/异常类名(不带 URL/body,防泄露)。
    """
    headers = {
        "X-Square-OpenAPI-Key": settings.binance_square_openapi_key,
        "Content-Type": "application/json",
        "clienttype": "binanceSkill",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.post(_ENDPOINT, json={"bodyTextOnly": text}, headers=headers)
    except httpx.HTTPError as exc:
        raise BinanceSquareError(f"网络错:{type(exc).__name__}") from exc
    if not resp.is_success:
        raise BinanceSquareError(f"HTTP {resp.status_code}")
    try:
        body = resp.json()
    except ValueError as exc:
        raise BinanceSquareError("响应非 JSON") from exc
    if not isinstance(body, dict):
        raise BinanceSquareError("响应非对象")
    return body


def _extract_post_id(data: Any) -> str | None:
    """从 success 响应的 data 防御性提取帖子 id(确切字段待校准 · 多路兜底)。"""
    if isinstance(data, dict):
        for k in ("id", "contentId", "postId", "post_id"):
            v = data.get(k)
            if v:
                return str(v)
        return None
    if isinstance(data, (str, int)):
        return str(data)
    return None


def _parse(body: dict[str, Any]) -> PublishResult:
    """币安 bapi 信封 → PublishResult(成功提 id/拼 url · 业务失败带 code+message)。"""
    code = str(body.get("code", ""))
    ok = body.get("success") is True or code in _SUCCESS_CODES
    if not ok:
        msg = body.get("message") or body.get("messageDetail") or "未知错误"
        # 错误码(20002 敏感词 / 100条天 等)+ 文案 → 存 dispatch.error 供 admin 看
        return PublishResult(success=False, error=f"币安拒绝 [{code}] {msg}")
    post_id = _extract_post_id(body.get("data"))
    url = f"https://www.binance.com/square/post/{post_id}" if post_id else None
    return PublishResult(success=True, platform_post_id=post_id, url=url)


class BinanceSquareAdapter(PublishAdapter):
    """币安广场发布适配器(真 API)。"""

    platform = "binance_square"
    _MAX_LEN = 4000  # 币安广场字数上限(占位 · 真发若超限会被币安拒,据 error 校准)

    @property
    def enabled(self) -> bool:
        # ★key 在 .env(与交易 API 隔离)· 空=禁用 · 照 oxapay/feishu 密钥范式
        return bool(settings.binance_square_openapi_key)

    def adapt_text(self, text: str) -> str:
        # 平台特定格式 · 超长则截断到上限 · 这是格式适配,不是重做门禁
        return text if len(text) <= self._MAX_LEN else text[: self._MAX_LEN]

    async def publish(self, *, text: str, image_path: str | None) -> PublishResult:
        # ★v1 纯文本(bodyTextOnly)· 图片待 Hans 实测 uploads 端点(image_path 暂不传)
        _ = image_path
        try:
            body = await _post_content(text)
        except BinanceSquareError as exc:
            logger.warning("[binance-square] 发布失败 · %s", exc)
            return PublishResult(success=False, error=str(exc))
        except Exception as exc:  # noqa: BLE001 · 兜底:任何意外不让 worker 崩(best-effort)
            logger.warning("[binance-square] 意外错 · %s", type(exc).__name__)
            return PublishResult(success=False, error=f"意外错:{type(exc).__name__}")
        # ★INFO 记 code/success/data(不含凭证)· Hans 首次真发据此校准 id 字段
        logger.info(
            "[binance-square] 响应 code=%s success=%s data=%s",
            body.get("code"), body.get("success"), body.get("data"),
        )
        return _parse(body)
