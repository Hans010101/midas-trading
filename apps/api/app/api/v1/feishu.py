"""飞书事件回调入站 · /api/v1/feishu/* · ADR 0032 阶段二。

POST /feishu/webhook —— 飞书开放平台事件订阅回调:
1. ★ URL 验证握手:配事件订阅时飞书发 {"type":"url_verification","challenge":...},原样回 challenge。
2. 验签:Verification Token(必配,常量时间比较)+ 可选 Encrypt Key(AES-256-CBC 解密事件体)
   + 可选 X-Lark-Signature(配了 Encrypt Key 时,对 timestamp+nonce+key+body 做 sha256 校验)。
3. 阶段二只【收事件 + 记日志】(交互:收消息→handle_inbound 是阶段三的事)。

🔴 红线:
- 身份只从【已验签事件】的 open_id 取(阶段三 handle_inbound 用)· 绝不从消息文本取。
  本阶段不解析 open_id 业务,但验签是阶段三身份注入的前提,这里先把"握手+验签"做扎实。
- 凭证(verification_token / encrypt_key)只从 env 读 · 不进日志(只记 event_type / 结果)。
- 验签未配置(verification_token 为空)→ 一律 403(拒绝未验明真伪的请求)。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feishu", tags=["feishu"])

_AES_BLOCK = 16
_FORBIDDEN = JSONResponse(
    status_code=status.HTTP_403_FORBIDDEN, content={"detail": "invalid feishu request"},
)


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
        return True  # 未带签名头(明文/未开签名)→ 由 Verification Token 兜底
    base = timestamp.encode() + nonce.encode() + encrypt_key.encode() + raw_body
    expected = hashlib.sha256(base).hexdigest()
    return hmac.compare_digest(expected, signature)


def _token_ok(payload: dict[str, Any]) -> bool:
    """Verification Token 校验:v2 在 header.token,v1/握手在顶层 token · 常量时间比较。"""
    configured = settings.feishu_verification_token
    if not configured:
        return False  # 未配置验签 → 拒绝(不接受无法验明真伪的请求)
    token = payload.get("token") or (payload.get("header") or {}).get("token") or ""
    return hmac.compare_digest(str(token), configured)


@router.post(
    "/webhook",
    summary="飞书事件回调(URL 握手 + 验签 + 收事件)",
    include_in_schema=False,  # 内部端点 · 不进公开 OpenAPI
)
async def feishu_webhook(request: Request) -> JSONResponse:
    raw_body = await request.body()
    try:
        body: dict[str, Any] = json.loads(raw_body) if raw_body else {}
    except (ValueError, UnicodeDecodeError):
        return JSONResponse(content={"code": 0})  # 非 JSON · 回 200 避免飞书重试风暴

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

    # 2. ★ URL 验证握手:校验 token 后原样回 challenge(飞书后台配事件订阅的前提)
    if payload.get("type") == "url_verification":
        if not _token_ok(payload):
            logger.warning("[feishu-webhook] url_verification token 校验失败 · 拒绝")
            return _FORBIDDEN
        logger.info("[feishu-webhook] url_verification 握手成功")
        return JSONResponse(content={"challenge": payload.get("challenge", "")})

    # 3. 事件:校验 Verification Token
    if not _token_ok(payload):
        logger.warning("[feishu-webhook] 事件 token 校验失败 · 拒绝")
        return _FORBIDDEN

    # 4. 阶段二:已验签事件 → 先记日志(交互 handle_inbound 留阶段三)。
    #    只记 event_type · 不记消息内容 / 用户标识(隐私 + 红线)。
    header = payload.get("header") or {}
    event_type = header.get("event_type") or payload.get("type") or "unknown"
    logger.info("[feishu-webhook] 已验签事件 event_type=%s(阶段二仅记录,未处理)", event_type)
    return JSONResponse(content={"code": 0})
