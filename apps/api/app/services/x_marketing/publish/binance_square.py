"""币安广场 adapter(发布层 PR-2 文本 + PR-4-img 图片)· 真 API。

文本发布:POST .../v1/.../content/add  body {"bodyTextOnly": text}
图片发布(★Hans 实测 Phase A 通过 · 官方 skill 源码实证的 4 步):
  ① POST .../v2/.../image/presignedUrl {"imageName"} → data.presignedUrl + data.fileTicket
  ② PUT <presignedUrl>  Content-Type: image/png  body=图片原始字节(传 S3)
  ③ POST .../v2/.../image/imageStatus {"fileTicket"} 轮询到 data.status==1 → data.imageUrl
  ④ POST .../v1/.../content/add {"contentType":1,"bodyTextOnly":text,"imageList":[imageUrl]}
限制:每帖最多 4 图(我们 1 张 K线截图)· 400 uploads/天 · 图与视频互斥。

★凭证 settings.binance_square_openapi_key 只进 Header · 绝不进日志/error/返回。
★图片 best-effort:传图任一步失败 → 退回纯文本发布(不是整个发布失败,有图发图、传图挂至少发文)。
★publish 永不 raise(网络/非2xx/非JSON/业务/意外都返 PublishResult(success=False))→ worker 不崩。
★响应里帖子 id/url 确切字段待校准 → INFO 记 code/success/data。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.services.x_marketing.publish.base import PublishAdapter, PublishResult

logger = logging.getLogger(__name__)

_V1 = "https://www.binance.com/bapi/composite/v1/public/pgc/openApi"
_V2 = "https://www.binance.com/bapi/composite/v2/public/pgc/openApi"
_CONTENT_ADD = f"{_V1}/content/add"
_PRESIGN = f"{_V2}/image/presignedUrl"
_IMG_STATUS = f"{_V2}/image/imageStatus"
_TIMEOUT_S = 30.0
_SUCCESS_CODES = ("000000", "0")
_POLL_MAX = 15            # 实测 15×2s 够 · 上限防死循环
_POLL_INTERVAL_S = 2.0


class BinanceSquareError(Exception):  # noqa: N818 — 传输错 · publish 据此转 failed
    """币安广场调用传输失败(网络 / 非 2xx / 非 JSON / 图片处理超时)。"""


def _headers() -> dict[str, str]:
    return {
        "X-Square-OpenAPI-Key": settings.binance_square_openapi_key,
        "Content-Type": "application/json",
        "clienttype": "binanceSkill",
    }


def _build_body(text: str, image_urls: list[str] | None) -> dict[str, Any]:
    """content/add 请求体 · 有图 → contentType=1 + imageList;无图 → 纯文本 bodyTextOnly。"""
    body: dict[str, Any] = {"bodyTextOnly": text}
    if image_urls:
        body["contentType"] = 1
        body["imageList"] = image_urls
    return body


async def _post_content(text: str, image_urls: list[str] | None = None) -> dict[str, Any]:
    """POST content/add(文本 or 带图)· 返回响应 JSON dict · 传输失败抛 BinanceSquareError。"""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.post(
                _CONTENT_ADD, json=_build_body(text, image_urls), headers=_headers(),
            )
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


async def _upload_image(image_path: str) -> str:
    """presigned → PUT 字节 → 轮询 imageStatus → imageUrl · 任一步失败抛 BinanceSquareError。"""
    name = Path(image_path).name
    data = Path(image_path).read_bytes()
    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
        # ① 预签名
        r1 = await client.post(_PRESIGN, json={"imageName": name}, headers=_headers())
        if not r1.is_success:
            raise BinanceSquareError(f"presignedUrl HTTP {r1.status_code}")
        d1 = (r1.json() or {}).get("data") or {}
        presigned, ticket = d1.get("presignedUrl"), d1.get("fileTicket")
        if not presigned or not ticket:
            raise BinanceSquareError("presignedUrl 响应缺 presignedUrl/fileTicket")
        # ② PUT 原始字节到 S3(★Content-Type 走图片 mime,不带 OpenAPI Header)
        r2 = await client.put(presigned, content=data, headers={"Content-Type": "image/png"})
        if not r2.is_success:
            raise BinanceSquareError(f"图片 PUT HTTP {r2.status_code}")
        # ③ 轮询处理状态 → imageUrl(上限防死循环)
        for _ in range(_POLL_MAX):
            r3 = await client.post(_IMG_STATUS, json={"fileTicket": ticket}, headers=_headers())
            d3 = (r3.json() or {}).get("data") or {} if r3.is_success else {}
            if d3.get("status") == 1 and d3.get("imageUrl"):
                return str(d3["imageUrl"])
            await asyncio.sleep(_POLL_INTERVAL_S)
    raise BinanceSquareError("图片处理轮询超时")


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
        return PublishResult(success=False, error=f"币安拒绝 [{code}] {msg}")
    post_id = _extract_post_id(body.get("data"))
    url = f"https://www.binance.com/square/post/{post_id}" if post_id else None
    return PublishResult(success=True, platform_post_id=post_id, url=url)


class BinanceSquareAdapter(PublishAdapter):
    """币安广场发布适配器(文本 + 图片)。"""

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
        # ★有截图 → 先传图(失败退纯文本 best-effort)· 无图 → 纯文本
        image_urls: list[str] | None = None
        if image_path and Path(image_path).is_file():
            try:
                image_urls = [await _upload_image(image_path)]
            except Exception as exc:  # noqa: BLE001 · ★传图失败退纯文本,不阻塞发布
                logger.warning("[binance-square] 图上传失败,退纯文本 · %s", exc)
                image_urls = None
        try:
            body = await _post_content(text, image_urls)
        except BinanceSquareError as exc:
            logger.warning("[binance-square] 发布失败 · %s", exc)
            return PublishResult(success=False, error=str(exc))
        except Exception as exc:  # noqa: BLE001 · 兜底:任何意外不让 worker 崩
            logger.warning("[binance-square] 意外错 · %s", type(exc).__name__)
            return PublishResult(success=False, error=f"意外错:{type(exc).__name__}")
        logger.info(
            "[binance-square] 响应 code=%s success=%s data=%s withImage=%s",
            body.get("code"), body.get("success"), body.get("data"), bool(image_urls),
        )
        return _parse(body)
