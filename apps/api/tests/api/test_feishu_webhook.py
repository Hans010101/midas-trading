"""飞书 webhook pytest · ADR 0032 阶段二:URL 握手 + 验签 + 加密解密。

覆盖:
- 明文 url_verification 握手 → 原样回 challenge(token 正确)
- token 错误 → 403(防伪造)
- 未配 verification_token → 403(拒绝无法验真的请求)
- 加密事件 → AES-256-CBC 解密后取 challenge(Encrypt Key 模式)
- 已验签普通事件 → 200(阶段二只记录)
"""

from __future__ import annotations

import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from httpx import AsyncClient

from app.core.config import settings

_VTOKEN = "vtok_test_123"
_EKEY = "ekey_test_abcdef"


@pytest.fixture
def feishu_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "feishu_verification_token", _VTOKEN)
    monkeypatch.setattr(settings, "feishu_encrypt_key", "")


@pytest.fixture
def feishu_verify_encrypted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "feishu_verification_token", _VTOKEN)
    monkeypatch.setattr(settings, "feishu_encrypt_key", _EKEY)


def _aes_encrypt(plaintext: str, encrypt_key: str) -> str:
    """模拟飞书加密:AES-256-CBC + PKCS7 · key=sha256(encrypt_key) · IV 前置。"""
    key = hashlib.sha256(encrypt_key.encode()).digest()
    iv = b"\x00" * 16
    data = plaintext.encode("utf-8")
    pad = 16 - (len(data) % 16)
    data += bytes([pad]) * pad
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ct = encryptor.update(data) + encryptor.finalize()
    return base64.b64encode(iv + ct).decode()


@pytest.mark.asyncio
@pytest.mark.usefixtures("feishu_verify")
async def test_url_verification_handshake_echoes_challenge(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/feishu/webhook", json={
        "type": "url_verification", "challenge": "abc123", "token": _VTOKEN,
    })
    assert resp.status_code == 200
    assert resp.json() == {"challenge": "abc123"}


@pytest.mark.asyncio
@pytest.mark.usefixtures("feishu_verify")
async def test_url_verification_wrong_token_rejected(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/feishu/webhook", json={
        "type": "url_verification", "challenge": "abc123", "token": "WRONG",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_webhook_rejects_when_verification_not_configured(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未配 verification_token(空)→ 一律 403(不接受无法验真的请求)。"""
    monkeypatch.setattr(settings, "feishu_verification_token", "")
    resp = await client.post("/api/v1/feishu/webhook", json={
        "type": "url_verification", "challenge": "abc123", "token": "",
    })
    assert resp.status_code == 403


@pytest.mark.asyncio
@pytest.mark.usefixtures("feishu_verify_encrypted")
async def test_encrypted_url_verification_decrypts(client: AsyncClient) -> None:
    """Encrypt Key 模式:加密体解密后取出 challenge,token 正确 → 回 challenge。"""
    inner = json.dumps({
        "type": "url_verification", "challenge": "enc_ch_999", "token": _VTOKEN,
    })
    resp = await client.post("/api/v1/feishu/webhook", json={
        "encrypt": _aes_encrypt(inner, _EKEY),
    })
    assert resp.status_code == 200
    assert resp.json() == {"challenge": "enc_ch_999"}


@pytest.mark.asyncio
@pytest.mark.usefixtures("feishu_verify_encrypted")
async def test_encrypted_event_without_key_rejected(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """收到 encrypt 体但服务端未配 Encrypt Key → 403(无法验真)。"""
    enc = _aes_encrypt(json.dumps({"type": "url_verification", "challenge": "x",
                                   "token": _VTOKEN}), _EKEY)
    monkeypatch.setattr(settings, "feishu_encrypt_key", "")  # 清掉 key
    resp = await client.post("/api/v1/feishu/webhook", json={"encrypt": enc})
    assert resp.status_code == 403


@pytest.mark.asyncio
@pytest.mark.usefixtures("feishu_verify")
async def test_event_v2_accepted_with_valid_token(client: AsyncClient) -> None:
    """v2 事件(header.token 正确)→ 200(阶段二仅记录,不处理)。"""
    resp = await client.post("/api/v1/feishu/webhook", json={
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "token": _VTOKEN},
        "event": {"message": {"content": "{\"text\":\"hi\"}"}},
    })
    assert resp.status_code == 200
    assert resp.json() == {"code": 0}


@pytest.mark.asyncio
@pytest.mark.usefixtures("feishu_verify")
async def test_event_v2_bad_token_rejected(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/feishu/webhook", json={
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "token": "BAD"},
        "event": {},
    })
    assert resp.status_code == 403
