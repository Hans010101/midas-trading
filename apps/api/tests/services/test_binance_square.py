"""币安广场 adapter(发布层 PR-2 · 真 API)单测:_parse / _extract_post_id / publish(mock 传输)。

传输层 _post_content 走 monkeypatch(不连真 API · 同 oxapay 测范式)· _parse 纯逻辑直测。
★响应字段确切名待 Hans 真发校准 · 这里覆盖标准 bapi 信封 + 业务错码 + 防御提取。
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.x_marketing.publish import binance_square as bs
from app.services.x_marketing.publish.binance_square import (
    BinanceSquareAdapter,
    BinanceSquareError,
    _extract_post_id,
    _parse,
)


def test_parse_success_extracts_id_and_url() -> None:
    body = {"code": "000000", "success": True, "data": {"id": "12345"}}
    r = _parse(body)
    assert r.success is True
    assert r.platform_post_id == "12345"
    assert r.url == "https://www.binance.com/square/post/12345"


def test_parse_success_via_success_flag_only() -> None:
    # success=true 但 code 非 000000(信封变体)· data 直接是 id 标量
    r = _parse({"success": True, "data": "777"})
    assert r.success is True
    assert r.platform_post_id == "777"


def test_parse_business_error_keeps_code_and_message() -> None:
    # 20002 敏感词等业务拒绝 → 失败 + 带 code+文案(存 dispatch.error 供 admin 看)
    r = _parse({"code": "20002", "success": False, "message": "敏感词检测未通过"})
    assert r.success is False
    assert "20002" in r.error
    assert "敏感词" in r.error


def test_parse_success_no_id_still_ok() -> None:
    # 成功但没提取到 id(字段名待校准)→ 仍判成功,id/url 为 None(不误判失败)
    r = _parse({"code": "000000", "success": True, "data": {}})
    assert r.success is True
    assert r.platform_post_id is None
    assert r.url is None


def test_extract_post_id_multi_path() -> None:
    assert _extract_post_id({"contentId": "c1"}) == "c1"
    assert _extract_post_id({"postId": 99}) == "99"
    assert _extract_post_id("scalar-id") == "scalar-id"
    assert _extract_post_id({}) is None
    assert _extract_post_id(None) is None


@pytest.mark.asyncio
async def test_publish_success(monkeypatch) -> None:  # noqa: ANN001
    async def fake_post(text: str) -> dict[str, Any]:  # noqa: ARG001
        return {"code": "000000", "success": True, "data": {"id": "p1"}}

    monkeypatch.setattr(bs, "_post_content", fake_post)
    r = await BinanceSquareAdapter().publish(text="$BTC 偏多 仅供参考", image_path=None)
    assert r.success is True
    assert r.platform_post_id == "p1"


@pytest.mark.asyncio
async def test_publish_transport_error_returns_failure_not_raise(monkeypatch) -> None:  # noqa: ANN001
    async def boom(text: str) -> dict[str, Any]:  # noqa: ARG001
        raise BinanceSquareError("HTTP 500")

    monkeypatch.setattr(bs, "_post_content", boom)
    # ★永不 raise:传输错 → 返回 failure result(run_publish 据此标 failed,worker 不崩)
    r = await BinanceSquareAdapter().publish(text="x", image_path=None)
    assert r.success is False
    assert "HTTP 500" in r.error


@pytest.mark.asyncio
async def test_publish_unexpected_error_caught(monkeypatch) -> None:  # noqa: ANN001
    async def boom(text: str) -> dict[str, Any]:  # noqa: ARG001
        raise RuntimeError("unexpected")

    monkeypatch.setattr(bs, "_post_content", boom)
    r = await BinanceSquareAdapter().publish(text="x", image_path=None)
    assert r.success is False  # 兜底 except 接住,不冒泡


def test_enabled_and_adapt_text(monkeypatch) -> None:  # noqa: ANN001
    a = BinanceSquareAdapter()
    monkeypatch.setattr("app.core.config.settings.binance_square_openapi_key", "")
    assert a.enabled is False  # 空 key = 禁用
    monkeypatch.setattr("app.core.config.settings.binance_square_openapi_key", "k")
    assert a.enabled is True
    assert a.adapt_text("a" * 5000) == "a" * 4000  # 超长截断到 4000
