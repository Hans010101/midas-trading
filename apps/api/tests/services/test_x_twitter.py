"""X(Twitter)发布 adapter 单测(纯逻辑 · mock tweepy · 不真发)。

覆盖:enabled 4 密钥门控 · 加权字数 · ★超限拒发不截断(保免责红线)· 成功/401/429/意外 映射 ·
publish 永不 raise。真发端到端由 Hans 后台点发验(刀4)。asyncio_mode=auto → 无需 marker。
"""

from __future__ import annotations

import pytest

from app.services.x_marketing.publish.base import PublishResult
from app.services.x_marketing.publish.x_twitter import (
    XTwitterAdapter,
    _x_weighted_len,
)


@pytest.fixture
def _keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """配齐 4 密钥(enabled=True)· 值是假的(不真连 X)。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "x_consumer_key", "ck", raising=False)
    monkeypatch.setattr(settings, "x_consumer_secret", "cs", raising=False)
    monkeypatch.setattr(settings, "x_access_token", "at", raising=False)
    monkeypatch.setattr(settings, "x_access_token_secret", "ats", raising=False)


def test_enabled_requires_all_four_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    a = XTwitterAdapter()
    for k in ("x_consumer_key", "x_consumer_secret", "x_access_token", "x_access_token_secret"):
        monkeypatch.setattr(settings, k, "", raising=False)
    assert a.enabled is False  # 全空 → 禁用
    monkeypatch.setattr(settings, "x_consumer_key", "ck", raising=False)
    monkeypatch.setattr(settings, "x_consumer_secret", "cs", raising=False)
    monkeypatch.setattr(settings, "x_access_token", "at", raising=False)
    assert a.enabled is False  # 缺 1 个 → 仍禁用
    monkeypatch.setattr(settings, "x_access_token_secret", "ats", raising=False)
    assert a.enabled is True   # 4 个齐 → 启用


def test_weighted_len_cjk_counts_two() -> None:
    assert _x_weighted_len("abc") == 3               # ASCII 各 1
    assert _x_weighted_len("中文") == 4               # CJK 各 2
    assert _x_weighted_len("a中") == 3               # 混合
    assert _x_weighted_len("") == 0


def test_adapt_text_never_truncates() -> None:
    """★红线:adapt_text 绝不截断(截断会砍尾部免责)· 原样返回。"""
    long_text = "中" * 500 + "仅供参考,不构成投资建议"
    assert XTwitterAdapter().adapt_text(long_text) == long_text


async def test_publish_oversize_rejects_not_truncates(_keys: None) -> None:
    """★超 280 加权 → 拒发(不截断不真发)· error 提示精简/开 Premium · 不丢免责。"""
    a = XTwitterAdapter()
    text = "中" * 200 + " 仅供参考,不构成投资建议"  # 加权 ≈ 400+ 远超 280
    res = await a.publish(text=text, image_path=None)
    assert res.success is False
    assert "280" in (res.error or "")
    assert "Premium" in (res.error or "")


async def test_publish_success(monkeypatch: pytest.MonkeyPatch, _keys: None) -> None:
    """成功路径:mock _post_sync 返回带 id 的响应 → PublishResult(success, id, url)。"""
    a = XTwitterAdapter()

    class _Resp:
        data = {"id": "1234567890"}

    monkeypatch.setattr(a, "_post_sync", lambda _text: _Resp())
    res = await a.publish(text="BTC 走强。仅供参考,不构成投资建议", image_path=None)
    assert res.success is True
    assert res.platform_post_id == "1234567890"
    assert "1234567890" in (res.url or "")


async def test_publish_no_id_in_response(monkeypatch: pytest.MonkeyPatch, _keys: None) -> None:
    a = XTwitterAdapter()

    class _Resp:
        data = None

    monkeypatch.setattr(a, "_post_sync", lambda _text: _Resp())
    res = await a.publish(text="仅供参考,不构成投资建议", image_path=None)
    assert res.success is False
    assert "id" in (res.error or "")


async def test_publish_maps_tweepy_errors_never_raises(
    monkeypatch: pytest.MonkeyPatch, _keys: None,
) -> None:
    """401/429/意外 都返 PublishResult(success=False)· 绝不 raise(worker 不崩)。"""
    import tweepy

    a = XTwitterAdapter()

    def _raise(exc: BaseException):
        def _inner(_text: str) -> object:
            raise exc
        return _inner

    # ★用 __new__ 绕开 tweepy 异常的 response 解析(只需异常【类型】被 except 匹配)
    unauthorized = tweepy.Unauthorized.__new__(tweepy.Unauthorized)
    too_many = tweepy.TooManyRequests.__new__(tweepy.TooManyRequests)

    # 401 认证失败
    monkeypatch.setattr(a, "_post_sync", _raise(unauthorized))
    r401 = await a.publish(text="仅供参考", image_path=None)
    assert r401.success is False
    assert "401" in (r401.error or "")

    # 429 限流
    monkeypatch.setattr(a, "_post_sync", _raise(too_many))
    r429 = await a.publish(text="仅供参考", image_path=None)
    assert r429.success is False
    assert "429" in (r429.error or "")

    # 意外错(非 tweepy)也兜住
    monkeypatch.setattr(a, "_post_sync", _raise(ValueError("boom")))
    rerr = await a.publish(text="仅供参考", image_path=None)
    assert rerr.success is False
    assert "意外" in (rerr.error or "")
    assert isinstance(rerr, PublishResult)
