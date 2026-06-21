"""周报素材 OSS 上传(第三刀-B)pytest · mock oss2,不打真 OSS。

覆盖:
- ★键格式 report-materials/{period}/{uid}{ext}。
- ★凭证缺失 → ObjectStoreError(不静默)。
- ★upload_material 调 _put_object(键 + 数据正确)+ 成功返回键。
- ★上传失败 → ObjectStoreError(不静默)。
- ★_put_object 真实 oss2 接线:Auth(id,secret) + Bucket(auth,endpoint,bucket) + put_object(key,data)。
"""

from __future__ import annotations

import sys
from datetime import date
from types import SimpleNamespace

import pytest

from app.services.report import object_store as obj
from app.services.report.object_store import (
    ObjectStoreError,
    build_object_key,
    upload_material,
)


def _set_creds(monkeypatch: pytest.MonkeyPatch, *, key_id: str = "fake_id", secret: str = "fake_sec") -> None:
    monkeypatch.setattr(obj.settings, "oss_access_key_id", key_id)
    monkeypatch.setattr(obj.settings, "oss_access_key_secret", secret)


def test_build_object_key_format():
    assert (
        build_object_key(period_start=date(2026, 6, 15), uid="abc123", ext=".pdf")
        == "report-materials/2026-06-15/abc123.pdf"
    )
    assert (
        build_object_key(period_start=None, uid="x", ext=".md")
        == "report-materials/undated/x.md"
    )


@pytest.mark.asyncio
async def test_upload_no_creds_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(obj.settings, "oss_access_key_id", "")
    monkeypatch.setattr(obj.settings, "oss_access_key_secret", "")
    with pytest.raises(ObjectStoreError, match="凭证"):
        await upload_material("report-materials/x/y.md", b"data")


@pytest.mark.asyncio
async def test_upload_calls_put_object(monkeypatch: pytest.MonkeyPatch):
    _set_creds(monkeypatch)
    captured: dict[str, object] = {}

    def _fake_put(key: str, data: bytes) -> None:
        captured["key"] = key
        captured["data"] = data

    monkeypatch.setattr(obj, "_put_object", _fake_put)
    out = await upload_material("report-materials/2026-06-15/abc.md", b"hello")

    assert out == "report-materials/2026-06-15/abc.md"
    assert captured["key"] == "report-materials/2026-06-15/abc.md"
    assert captured["data"] == b"hello"


@pytest.mark.asyncio
async def test_upload_failure_raises(monkeypatch: pytest.MonkeyPatch):
    _set_creds(monkeypatch)

    def _boom(*_a: object) -> None:
        msg = "network down"
        raise RuntimeError(msg)

    monkeypatch.setattr(obj, "_put_object", _boom)
    with pytest.raises(ObjectStoreError, match="上传失败"):
        await upload_material("report-materials/x/y.md", b"data")


def test_put_object_wires_oss2(monkeypatch: pytest.MonkeyPatch):
    """★验真实 oss2 接线:Auth(id,secret) → Bucket(auth,endpoint,bucket) → put_object(key,data)。"""
    _set_creds(monkeypatch, key_id="ID1", secret="SEC1")
    monkeypatch.setattr(obj.settings, "oss_endpoint", "oss-test-endpoint")
    monkeypatch.setattr(obj.settings, "oss_bucket", "test-bucket")

    calls: dict[str, object] = {}

    class _FakeBucket:
        def __init__(self, auth: object, endpoint: str, bucket: str) -> None:
            calls["bucket_args"] = (auth, endpoint, bucket)

        def put_object(self, key: str, data: bytes) -> None:
            calls["put"] = (key, data)

    def _fake_auth(key_id: str, secret: str) -> str:
        calls["auth"] = (key_id, secret)
        return "AUTHOBJ"

    monkeypatch.setitem(sys.modules, "oss2", SimpleNamespace(Auth=_fake_auth, Bucket=_FakeBucket))

    obj._put_object("report-materials/p/u.pdf", b"bytes")

    assert calls["auth"] == ("ID1", "SEC1")
    assert calls["bucket_args"] == ("AUTHOBJ", "oss-test-endpoint", "test-bucket")
    assert calls["put"] == ("report-materials/p/u.pdf", b"bytes")
