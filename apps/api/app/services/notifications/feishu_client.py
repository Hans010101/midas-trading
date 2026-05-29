"""飞书(Lark)发消息客户端 · ADR 0032 阶段二多通道通知。

职责:
- tenant_access_token 管理:App ID/Secret 换取,Redis 缓存 + 提前刷新(TTL 内复用)。
- send_text:给定 open_id + 纯文本,经飞书 IM API 发文本消息(msg_type=text)。

健壮性对齐 telegram.py:网络/接口错误抛 FeishuApiError(不崩),调用方(adapter)吞掉记日志。
token 过期(接口返回 auth 相关 code)→ 失效缓存 + 重取一次再发。

🔴 凭证只从 settings(env)读 · 绝不进 git / 日志(不打印 secret / token 明文)。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, cast

import httpx

from app.core.config import settings
from app.core.redis_client import get_redis

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# Redis 缓存键 · 全局单 token(企业自建应用 token 是 app 级,不是 per-user)。
_TOKEN_CACHE_KEY = "feishu:tenant_access_token"
# 提前刷新余量(秒):缓存 TTL = 飞书返回 expire − 余量 → 真过期前缓存先失效、自动重取。
_TOKEN_REFRESH_MARGIN = 300
_MIN_CACHE_TTL = 60
# 飞书"token 无效 / 过期"错误码(失效缓存后重取一次)· 见飞书开放平台错误码表。
_AUTH_ERROR_CODES = {99991663, 99991661, 99991664, 99991668}


class FeishuApiError(Exception):
    """飞书接口错误 · code = 飞书业务码(网络错误用 0)。"""

    def __init__(self, code: int, detail: str) -> None:
        super().__init__(f"Feishu {code}: {detail}")
        self.code = code
        self.detail = detail


def _api(path: str) -> str:
    return f"{settings.feishu_api_base.rstrip('/')}{path}"


async def _post(
    url: str,
    *,
    json_body: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: float,
    client: httpx.AsyncClient | None,
) -> dict[str, Any]:
    """通用飞书 POST · 解析 {code,msg,...} · 失败抛 FeishuApiError。"""
    owned = client is None
    if owned:
        client = httpx.AsyncClient(timeout=timeout)
    assert client is not None  # noqa: S101

    try:
        resp = await client.post(url, json=json_body, headers=headers)
    except httpx.HTTPError as e:
        raise FeishuApiError(0, f"网络错误:{e}") from e
    finally:
        if owned:
            await client.aclose()

    try:
        body = resp.json()
    except ValueError as e:
        raise FeishuApiError(resp.status_code, "响应不是有效 JSON") from e

    code = body.get("code")
    if code != 0:
        # 不记 token / secret;只记 code + msg
        raise FeishuApiError(int(code) if code is not None else resp.status_code,
                             str(body.get("msg") or f"HTTP {resp.status_code}"))
    return cast("dict[str, Any]", body)


async def _fetch_tenant_token(client: httpx.AsyncClient | None) -> tuple[str, int]:
    """App ID/Secret → (tenant_access_token, expire 秒)· 失败抛 FeishuApiError。"""
    body = await _post(
        _api("/open-apis/auth/v3/tenant_access_token/internal"),
        json_body={
            "app_id": settings.feishu_app_id,
            "app_secret": settings.feishu_app_secret,
        },
        timeout=5.0,
        client=client,
    )
    token = body.get("tenant_access_token")
    expire = int(body.get("expire") or 7200)
    if not token:
        raise FeishuApiError(0, "响应缺 tenant_access_token")
    return str(token), expire


async def get_tenant_access_token(
    *,
    redis: Redis | None = None,
    client: httpx.AsyncClient | None = None,
    force_refresh: bool = False,
) -> str:
    """取 tenant_access_token · Redis 缓存命中即复用,否则重取并缓存(提前刷新)。"""
    r = redis if redis is not None else await get_redis()
    if not force_refresh:
        cached = await r.get(_TOKEN_CACHE_KEY)
        if cached:
            return str(cached)
    token, expire = await _fetch_tenant_token(client)
    ttl = max(expire - _TOKEN_REFRESH_MARGIN, _MIN_CACHE_TTL)
    await r.setex(_TOKEN_CACHE_KEY, ttl, token)
    return token


async def _send_message(
    open_id: str,
    msg_type: str,
    content: str,
    *,
    redis: Redis | None,
    client: httpx.AsyncClient | None,
) -> None:
    """发消息到 open_id(msg_type=text/interactive)· token 失效自动重取一次再发。

    content 为飞书要求的【JSON 字符串】(text:{"text":..};interactive:卡片 JSON 串)。
    """
    r = redis if redis is not None else await get_redis()
    url = _api("/open-apis/im/v1/messages?receive_id_type=open_id")
    payload = {"receive_id": open_id, "msg_type": msg_type, "content": content}

    token = await get_tenant_access_token(redis=r, client=client)
    try:
        await _post(
            url, json_body=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=5.0, client=client,
        )
        return
    except FeishuApiError as e:
        if e.code not in _AUTH_ERROR_CODES:
            raise
        # token 过期/无效:失效缓存 → 强制重取 → 重发一次
        logger.info("[feishu] token 失效(code=%s)· 重取后重发", e.code)

    token = await get_tenant_access_token(redis=r, client=client, force_refresh=True)
    await _post(
        url, json_body=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=5.0, client=client,
    )


async def send_text(
    open_id: str,
    text: str,
    *,
    redis: Redis | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """发纯文本消息到 open_id · 失败抛 FeishuApiError。"""
    content = json.dumps({"text": text}, ensure_ascii=False)
    await _send_message(open_id, "text", content, redis=redis, client=client)


async def send_card(
    open_id: str,
    card: dict[str, object],
    *,
    redis: Redis | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """发交互式卡片(msg_type=interactive)到 open_id · 失败抛 FeishuApiError。

    card 为飞书卡片 JSON(dict)· 这里序列化成 content 串(ADR 0032 阶段三交互渲染)。
    """
    content = json.dumps(card, ensure_ascii=False)
    await _send_message(open_id, "interactive", content, redis=redis, client=client)
