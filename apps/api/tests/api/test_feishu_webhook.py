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
from typing import Any

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.feishu import _card_update_response, _handle_card_action
from app.core.config import settings
from app.models.notification import NotificationConfig
from tests.factories import make_user

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


# ── 阶段三:事件解析(★ open_id 唯一注入点 · 只从已验签事件取)──────────


def test_parse_message_event_open_id_from_sender_only() -> None:
    """🔴 open_id 只取自 event.sender.sender_id.open_id · 文本里的伪 open_id 不被采信。"""
    from app.api.v1.feishu import _parse_message_event

    event = {
        "sender": {"sender_id": {"open_id": "ou_real"}},
        "message": {
            "message_type": "text",
            "content": json.dumps({"text": "hi open_id=ou_FORGED"}),
        },
    }
    open_id, text = _parse_message_event(event)
    assert open_id == "ou_real"          # 来自 sender,不是文本里的 ou_FORGED
    assert "ou_FORGED" in (text or "")   # 伪 open_id 只是普通文本,不影响身份


def test_parse_card_event_open_id_from_operator() -> None:
    from app.api.v1.feishu import _parse_card_event

    event = {
        "operator": {"open_id": "ou_op"},
        "action": {"tag": "button", "value": {"action": "menu:quote"}},
    }
    open_id, action = _parse_card_event(event)
    assert open_id == "ou_op"
    assert action == "menu:quote"


def test_parse_message_event_non_text_returns_none_text() -> None:
    from app.api.v1.feishu import _parse_message_event

    event = {
        "sender": {"sender_id": {"open_id": "ou_x"}},
        "message": {"message_type": "image", "content": "{}"},
    }
    open_id, text = _parse_message_event(event)
    assert open_id == "ou_x"
    assert text is None


@pytest.mark.asyncio
@pytest.mark.usefixtures("feishu_verify")
async def test_message_event_accepted_returns_200(client: AsyncClient) -> None:
    """已验签文本消息事件 → 200(后台处理 · 不抛崩)· 用 fake redis 隔离(未绑定→ignored)。"""
    from app.core.redis_client import get_redis
    from app.main import app

    class _FakeRedis:
        async def get(self, _key: str) -> str | None:
            return None  # 未绑定 / 无 pending token → 当普通消息;ch=None → 直接返回

    app.dependency_overrides[get_redis] = lambda: _FakeRedis()
    try:
        resp = await client.post("/api/v1/feishu/webhook", json={
            "schema": "2.0",
            "header": {"event_type": "im.message.receive_v1", "token": _VTOKEN},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_x"}},
                "message": {
                    "message_type": "text",
                    "content": json.dumps({"text": "/menu"}),
                },
            },
        })
        assert resp.status_code == 200
        assert resp.json() == {"code": 0}
    finally:
        app.dependency_overrides.pop(get_redis, None)


# ── 阶段四-B:card.action.trigger 原地刷新(点按钮 → HTTP 响应返回新卡)──────


class _FakeRedis:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}
        self._c: dict[str, int] = {}

    async def get(self, k: str) -> str | None:
        return self._d.get(k)

    async def setex(self, k: str, _t: int, v: str) -> None:
        self._d[k] = v

    async def delete(self, k: str) -> None:
        self._d.pop(k, None)

    async def incr(self, k: str) -> int:
        self._c[k] = self._c.get(k, 0) + 1
        return self._c[k]

    async def expire(self, _k: str, _t: int) -> None:
        return None


class _FakeCH:
    def __init__(self) -> None:
        self._client = object()

    async def select_kline(self, **_kw: Any) -> list[Any]:
        return []


def _card_action_event(open_id: str, action: str) -> dict[str, Any]:
    return {"operator": {"open_id": open_id}, "action": {"value": {"action": action}}}


def test_card_update_response_structure() -> None:
    """原地更新响应信封:{"card": {"type": "raw", "data": <卡片>}}。"""
    card: dict[str, Any] = {"config": {}, "header": {}, "elements": []}
    assert _card_update_response(card) == {"card": {"type": "raw", "data": card}}


@pytest.mark.asyncio
async def test_card_action_returns_inplace_update(db_session: AsyncSession) -> None:
    """点卡片按钮 → 返回【原地更新】响应(非 None=不发新卡)· 卡片是对应业务结果。"""
    user = await make_user(db_session)
    db_session.add(NotificationConfig(user_id=user.id, feishu_open_id="ou_z"))
    await db_session.commit()
    resp = await _handle_card_action(
        db_session, _FakeRedis(), _FakeCH(), _card_action_event("ou_z", "menu:quote"),  # type: ignore[arg-type]
    )
    assert resp is not None
    assert resp["card"]["type"] == "raw"
    body = resp["card"]["data"]["elements"][0]["text"]["content"]
    assert "先选市场" in body  # menu:quote → 选市场卡(复用 handle_inbound)


@pytest.mark.asyncio
async def test_card_action_multistep_each_returns_card(
    db_session: AsyncSession,
) -> None:
    """🔴 多步:连续点按钮每步都【原地返回卡】(非 None)· 即不堆新卡、逐步演进。"""
    user = await make_user(db_session)
    db_session.add(NotificationConfig(user_id=user.id, feishu_open_id="ou_m"))
    await db_session.commit()
    redis, ch = _FakeRedis(), _FakeCH()
    r1 = await _handle_card_action(
        db_session, redis, ch, _card_action_event("ou_m", "menu:order"),  # type: ignore[arg-type]
    )
    r2 = await _handle_card_action(
        db_session, redis, ch, _card_action_event("ou_m", "omkt:us"),  # type: ignore[arg-type]
    )
    assert r1 is not None
    assert r2 is not None
    assert r1["card"]["data"]["elements"]  # 选市场卡
    assert r2["card"]["data"]["elements"]  # 输代码卡
    # 会话原地推进:omkt:us 后停在 order_symbol(同一 feishu 前缀键)
    assert "feishu_session:ou_m" in redis._d


@pytest.mark.asyncio
async def test_card_action_no_open_id_returns_none(db_session: AsyncSession) -> None:
    """🔴 身份红线:事件无 operator.open_id → None(不处理)。"""
    resp = await _handle_card_action(
        db_session, _FakeRedis(), _FakeCH(),  # type: ignore[arg-type]
        {"action": {"value": {"action": "menu:quote"}}},
    )
    assert resp is None
