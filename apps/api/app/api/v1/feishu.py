"""飞书事件回调 + 绑定 · /api/v1/feishu/* · ADR 0032 阶段二(通知)+ 阶段三(交互)。

- POST /feishu/bind-token · 登录态 · 生成一次性绑定码(对称 TG · 用户在飞书发码完成绑定)
- POST /feishu/webhook    · 飞书事件回调:
  1. ★ URL 验证握手:配事件订阅时回 challenge
  2. 验签:Verification Token(必配,常量时间)+ 可选 Encrypt Key(AES-256-CBC)+ 可选签名
  3. 阶段三/四:im.message.receive_v1 / card.action.trigger / application.bot.menu_v6
     → InboundMessage → handle_inbound(复用阶段一中立核心 · 飞书不另写交互逻辑)
     → render_for_feishu → 发卡(菜单/文本走后台发新卡;卡片按钮原地刷新)。

🔴 红线:
- 身份只从【已验签事件体】的 open_id 取(_parse_message_event / _parse_card_event 是唯一注入点)·
  绝不从消息文本取(文本里写的任何 open_id 都不被采信)。
- 验签未配置(verification_token 空)→ 一律 403。
- 凭证只从 env 读 · 日志只记 event_type / 结果,不记消息内容 / open_id。
- 阶段三只读交互,不含下单;execute 仍只由 router order_confirm 态的 ordok 触发(飞书无法绕过)。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from typing import TYPE_CHECKING, Annotated, Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep, OptionalClickHouseDep
from app.core.config import settings
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.notification import NotificationConfig
from app.services.bot.renderers.feishu import render_for_feishu
from app.services.bot.replies import InboundMessage
from app.services.bot.router import handle_inbound
from app.services.notifications import feishu_client
from app.services.notifications.feishu_bind import (
    create_bind_token,
    handle_feishu_bind,
)

if TYPE_CHECKING:
    from app.services.clickhouse_client import ClickHouseClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feishu", tags=["feishu"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[Redis, Depends(get_redis)]

_AES_BLOCK = 16
_FORBIDDEN = JSONResponse(
    status_code=status.HTTP_403_FORBIDDEN, content={"detail": "invalid feishu request"},
)


# ── 绑定码端点(登录态)──────────────────────────────────────────────


class FeishuBindTokenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(description="一次性绑定码 · 在飞书发给 bot(可直接粘贴或 /bind <码>)")
    expires_in: int = Field(description="绑定码有效秒数")
    app_id: str = Field(
        description=(
            "飞书应用 App ID(公开标识 · 非密钥)· 前端用它拼 applink"
            " 一键打开机器人会话。app_secret 绝不下发。"
        ),
    )


@router.post(
    "/bind-token",
    response_model=FeishuBindTokenResponse,
    summary="生成飞书绑定一次性码(登录态)",
)
async def create_feishu_bind_token(
    current_user: CurrentUserDep, redis: RedisDep,
) -> FeishuBindTokenResponse:
    if not (settings.feishu_app_id and settings.feishu_app_secret):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="飞书应用未配置(FEISHU_APP_ID/SECRET 未设)",
        )
    token = await create_bind_token(redis, current_user.id)
    # app_id 是公开标识(applink 用)· 这里随绑定码一起下发;app_secret 绝不出后端。
    return FeishuBindTokenResponse(
        token=token,
        expires_in=settings.tg_bind_token_ttl_seconds,
        app_id=settings.feishu_app_id,
    )


@router.post("/unbind", summary="解绑当前账号的飞书(清空 feishu_open_id · 登录态)")
async def unbind_feishu(
    current_user: CurrentUserDep, db: DbDep,
) -> dict[str, bool]:
    """解绑 · 清空当前用户自己的 feishu_open_id · 幂等 · 不碰其它字段 / 无迁移。"""
    config = await db.scalar(
        select(NotificationConfig).where(
            NotificationConfig.user_id == current_user.id,
        ),
    )
    if config is not None and config.feishu_open_id is not None:
        config.feishu_open_id = None
        await db.commit()
    return {"unbound": True}


# ── 验签 / 解密(阶段二)─────────────────────────────────────────────


def _decrypt_event(encrypt_b64: str, encrypt_key: str) -> dict[str, Any]:
    """AES-256-CBC 解密飞书加密事件体 · key=sha256(encrypt_key) · IV=密文前 16 字节。"""
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    raw = base64.b64decode(encrypt_b64)
    iv, ciphertext = raw[:_AES_BLOCK], raw[_AES_BLOCK:]
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    pad_len = padded[-1]  # PKCS7 去填充
    plaintext = padded[:-pad_len] if 0 < pad_len <= _AES_BLOCK else padded
    return json.loads(plaintext.decode("utf-8"))  # type: ignore[no-any-return]


def _signature_ok(req_headers: Any, raw_body: bytes, encrypt_key: str) -> bool:
    """X-Lark-Signature 校验(配了 Encrypt Key 时飞书带签名)· 缺头则跳过(不强制)。"""
    signature = req_headers.get("X-Lark-Signature")
    timestamp = req_headers.get("X-Lark-Request-Timestamp")
    nonce = req_headers.get("X-Lark-Request-Nonce")
    if not (signature and timestamp and nonce):
        return True
    base = timestamp.encode() + nonce.encode() + encrypt_key.encode() + raw_body
    expected = hashlib.sha256(base).hexdigest()
    return hmac.compare_digest(expected, signature)


def _token_ok(payload: dict[str, Any]) -> bool:
    """Verification Token 校验:v2 在 header.token,v1/握手在顶层 token · 常量时间比较。"""
    configured = settings.feishu_verification_token
    if not configured:
        return False
    token = payload.get("token") or (payload.get("header") or {}).get("token") or ""
    return hmac.compare_digest(str(token), configured)


# ── 事件体解析(★ open_id 唯一注入点 · 只从已验签事件取)──────────────


def _parse_message_event(event: dict[str, Any]) -> tuple[str | None, str | None]:
    """im.message.receive_v1 → (open_id, text)。

    🔴 open_id 只取自 event.sender.sender_id.open_id(已验签事件体)· 绝不从消息内容取。
    """
    sender_id = (event.get("sender") or {}).get("sender_id") or {}
    open_id = sender_id.get("open_id")
    message = event.get("message") or {}
    text: str | None = None
    if message.get("message_type") == "text":
        try:
            text = json.loads(message.get("content") or "{}").get("text")
        except (ValueError, TypeError):
            text = None
    return (open_id, text)


def _parse_card_event(event: dict[str, Any]) -> tuple[str | None, str | None]:
    """card.action.trigger → (open_id, action)。

    🔴 open_id 只取自 event.operator.open_id(已验签事件体)· action 取自按钮 value.action。
    """
    open_id = (event.get("operator") or {}).get("open_id")
    value = (event.get("action") or {}).get("value") or {}
    action = value.get("action") if isinstance(value, dict) else None
    return (open_id, action)


def _parse_menu_event(event: dict[str, Any]) -> tuple[str | None, str | None]:
    """application.bot.menu_v6(机器人常驻菜单点击)→ (open_id, event_key)。

    🔴 open_id 只取自 event.operator.operator_id.open_id(已验签事件体)——
       注意菜单事件是【嵌套 operator_id】,与 card 事件的扁平 operator.open_id 不同。
    event_key 是飞书后台为菜单项配置的自定义标识(我们让它复用现有 action 命名)。
    """
    operator_id = (event.get("operator") or {}).get("operator_id") or {}
    open_id = operator_id.get("open_id")
    event_key = event.get("event_key")
    return (open_id, event_key)


# ── 后台发送(fail-soft · 不影响已返回的 200)─────────────────────────


async def _send_card_safe(open_id: str, card: dict[str, Any]) -> None:
    try:
        await feishu_client.send_card(open_id, card)
    except Exception as e:  # noqa: BLE001
        logger.warning("[feishu-webhook] 发卡失败:%s", e)


async def _send_text_safe(open_id: str, text: str) -> None:
    try:
        await feishu_client.send_text(open_id, text)
    except Exception as e:  # noqa: BLE001
        logger.warning("[feishu-webhook] 发文本失败:%s", e)


# ── webhook 主入口 ───────────────────────────────────────────────────


@router.post(
    "/webhook",
    summary="飞书事件回调(URL 握手 + 验签 + 收消息/卡片回调)",
    include_in_schema=False,
)
async def feishu_webhook(
    request: Request,
    db: DbDep,
    redis: RedisDep,
    ch: OptionalClickHouseDep,
    background: BackgroundTasks,
) -> JSONResponse:
    raw_body = await request.body()
    try:
        body: dict[str, Any] = json.loads(raw_body) if raw_body else {}
    except (ValueError, UnicodeDecodeError):
        return JSONResponse(content={"code": 0})

    # 1. 解密(若配置了 Encrypt Key 且事件体加密)
    if "encrypt" in body:
        encrypt_key = settings.feishu_encrypt_key
        if not encrypt_key:
            logger.warning("[feishu-webhook] 收到加密事件但未配 Encrypt Key · 拒绝")
            return _FORBIDDEN
        if not _signature_ok(request.headers, raw_body, encrypt_key):
            logger.warning("[feishu-webhook] X-Lark-Signature 校验失败 · 拒绝")
            return _FORBIDDEN
        try:
            payload = _decrypt_event(str(body["encrypt"]), encrypt_key)
        except (ValueError, KeyError) as e:
            logger.warning("[feishu-webhook] 事件解密失败:%s · 拒绝", e)
            return _FORBIDDEN
    else:
        payload = body

    # 2. ★ URL 验证握手
    if payload.get("type") == "url_verification":
        if not _token_ok(payload):
            logger.warning("[feishu-webhook] url_verification token 校验失败 · 拒绝")
            return _FORBIDDEN
        logger.info("[feishu-webhook] url_verification 握手成功")
        return JSONResponse(content={"challenge": payload.get("challenge", "")})

    # 3. 校验 Verification Token
    if not _token_ok(payload):
        logger.warning("[feishu-webhook] 事件 token 校验失败 · 拒绝")
        return _FORBIDDEN

    # 4. 路由事件(已验签)
    header = payload.get("header") or {}
    event_type = header.get("event_type") or payload.get("type") or "unknown"
    event = payload.get("event") or {}

    if event_type == "im.message.receive_v1":
        # 用户发文本(如输标的)→ 发【新消息卡】(本就该新消息,不原地刷新)
        await _handle_message(db, redis, ch, background, event)
    elif event_type == "card.action.trigger":
        # 点按钮 → 在 HTTP 响应里【原地返回新卡】· 飞书替换当前卡(对齐 TG editMessageText)
        card_resp = await _handle_card_action(db, redis, ch, event)
        if card_resp is not None:
            return JSONResponse(content=card_resp)
    elif event_type == "application.bot.menu_v6":
        # 点常驻菜单 → 异步事件 → 后台发【新卡】(event_key 当 action 走 handle_inbound)
        await _handle_menu_action(db, redis, ch, background, event)
    else:
        logger.info("[feishu-webhook] 忽略事件 event_type=%s", event_type)

    return JSONResponse(content={"code": 0})


def _card_update_response(card: dict[str, Any]) -> dict[str, Any]:
    """card.action.trigger 回调的【原地更新】响应体。

    飞书规范:回调响应里带 card → 替换触发该回调的那张卡(无需另发新消息)。
    用 type=raw 直接塞我们 render_for_feishu 产出的卡片 JSON。
    待真机确认:若飞书要求其它信封键,这里是唯一改动点(业务逻辑不受影响)。
    """
    return {"card": {"type": "raw", "data": card}}


async def _handle_message(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient | None,
    background: BackgroundTasks,
    event: dict[str, Any],
) -> None:
    """文本消息:先尝试绑定,否则归一为 InboundMessage 走 handle_inbound。"""
    open_id, text = _parse_message_event(event)
    if open_id is None:
        return

    # 1. 绑定优先(对称 TG /start)· open_id 来自已验签事件
    bind = await handle_feishu_bind(db, redis, open_id=open_id, text=text)
    if bind.kind != "ignored":
        if bind.reply_text:
            background.add_task(_send_text_safe, open_id, bind.reply_text)
        return

    # 2. 非绑定 → handle_inbound(中立核心 · 需 CH 查询;prod 必有,本地无则跳过)
    if ch is None:
        return
    msg = InboundMessage(
        channel="feishu", channel_uid=open_id, kind="text", text=text,
    )
    reply = await handle_inbound(db, redis, ch, msg)
    background.add_task(_send_card_safe, open_id, render_for_feishu(reply))


async def _handle_card_action(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient | None,
    event: dict[str, Any],
) -> dict[str, Any] | None:
    """卡片按钮回调 → InboundMessage(kind=button)→ handle_inbound → 【原地更新】响应。

    返回 card-update 响应体(飞书原地替换当前卡);无法处理(缺 open_id/action/CH)→ None。
    🔴 open_id 仍只从 _parse_card_event(已验签事件)取 · 业务全走 handle_inbound(不另写)。
    """
    open_id, action = _parse_card_event(event)
    if open_id is None or not action:
        return None
    if ch is None:
        return None
    msg = InboundMessage(
        channel="feishu", channel_uid=open_id, kind="button", action=action,
    )
    reply = await handle_inbound(db, redis, ch, msg)
    return _card_update_response(render_for_feishu(reply))


async def _handle_menu_action(
    db: AsyncSession,
    redis: Redis,
    ch: ClickHouseClient | None,
    background: BackgroundTasks,
    event: dict[str, Any],
) -> None:
    """常驻菜单点击(application.bot.menu_v6)· event_key 复用现有 action 命名 →
    归一为 InboundMessage(kind=button)→ handle_inbound → 发【新消息卡】。

    菜单事件是异步事件(非 card.action.trigger 的原地回调),故走后台发新卡(对齐 _handle_message)。
    🔴 身份只从 _parse_menu_event(已验签 operator.operator_id.open_id)取;event_key 当 action,
       业务全走 handle_inbound —— 菜单点击 ≡ 点了对应按钮,核心层零改动。
    🔴 下单二次确认不被弱化:即便 event_key 配成 ordok,execute 仍只由 order_confirm 态触发
       (无会话 → 回主菜单,不成交)· 见 _handle_confirm gate。
    """
    open_id, event_key = _parse_menu_event(event)
    if open_id is None or not event_key:
        return
    if ch is None:
        return
    msg = InboundMessage(
        channel="feishu", channel_uid=open_id, kind="button", action=event_key,
    )
    reply = await handle_inbound(db, redis, ch, msg)
    background.add_task(_send_card_safe, open_id, render_for_feishu(reply))
