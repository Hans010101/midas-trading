"""i18n Phase3 刀1 · 后端本地化地基测试(resolve_lang 四级优先级 + translate + ★zh 逐字节铁证)。"""

from __future__ import annotations

from typing import Any, cast

from starlette.datastructures import Headers, QueryParams

from app.services.i18n import resolve_lang, translate
from app.services.i18n.catalog import _CATALOG


def _req(headers: dict[str, str] | None = None, query: str = "") -> Any:  # noqa: ANN401
    """轻量 Request 替身(只需 headers / query_params · Headers 大小写不敏感同真实)。"""

    class _FakeRequest:
        def __init__(self) -> None:
            self.headers = Headers(headers or {})
            self.query_params = QueryParams(query)

    return _FakeRequest()


# ===== resolve_lang 四级优先级 =====


def test_resolve_lang_default_zh() -> None:
    """★zh 零变化:无任何语言信号 → zh(现有中文用户全走这里)。"""
    assert resolve_lang(_req()) == "zh"
    assert resolve_lang(_req(), None) == "zh"


def test_resolve_lang_explicit_header_top_priority() -> None:
    """① 显式 X-Lang / ?lang 最高优先(压过 language_pref 与 Accept-Language)。"""
    r = _req({"x-lang": "en", "accept-language": "zh-CN"})
    assert resolve_lang(r, "zh") == "en"
    assert resolve_lang(cast("Any", _req(query="lang=en")), "zh") == "en"


def test_resolve_lang_language_pref_second() -> None:
    """② 无显式头时用登录用户 language_pref(压过 Accept-Language)。"""
    r = _req({"accept-language": "zh-CN"})
    assert resolve_lang(r, "en") == "en"


def test_resolve_lang_accept_language_third() -> None:
    """③ 未登录(pref=None)时用 Accept-Language 兜底(★英文用户注册/登录页的关键)。"""
    assert resolve_lang(_req({"accept-language": "en-US,en;q=0.9,zh;q=0.8"}), None) == "en"
    assert resolve_lang(_req({"accept-language": "fr-FR,fr;q=0.9,en;q=0.5"}), None) == "en"
    assert resolve_lang(_req({"accept-language": "zh-CN,zh;q=0.9"}), None) == "zh"


def test_resolve_lang_normalize_and_unknown() -> None:
    """en-US→en · zh-CN→zh · 不识别语言跳过 → 最终 zh 兜底。"""
    assert resolve_lang(_req({"x-lang": "EN"})) == "en"
    assert resolve_lang(_req({"x-lang": "ja"})) == "zh"          # 不支持 → 兜底 zh
    assert resolve_lang(_req({"accept-language": "fr,de"}), None) == "zh"  # 无 zh/en → zh


# ===== translate =====


def test_translate_zh_byte_identical() -> None:
    """★zh 逐字节铁证:catalog 的 zh 值 = 今天线上 deps.py 中文字面量,一字不差。"""
    assert translate("auth.no_token", "zh") == "未携带 Bearer session token"
    assert translate("auth.session_invalid", "zh") == "session 无效或已过期 · 请重新登录"
    assert translate("auth.account_disabled", "zh") == "账号已被停用"
    assert translate("auth.platinum_required", "zh") == "需铂金权限"
    # 默认 lang 即 zh
    assert translate("auth.no_token") == "未携带 Bearer session token"


def test_translate_en() -> None:
    assert translate("auth.no_token", "en") == "No Bearer session token provided"
    assert "Platinum" in translate("auth.platinum_required", "en")


def test_translate_unknown_key_falls_back_to_key() -> None:
    """未登记 key → 返回 key 本身(绝不炸)。"""
    assert translate("nonexistent.key", "en") == "nonexistent.key"


def test_translate_missing_en_falls_back_to_zh() -> None:
    """登记但缺 en → 回退 zh(永不缺文案)。"""
    _CATALOG["_test.zh_only"] = {"zh": "只有中文"}
    try:
        assert translate("_test.zh_only", "en") == "只有中文"
    finally:
        del _CATALOG["_test.zh_only"]


def test_translate_params_interpolation() -> None:
    """含命名占位的模板走 str.format(**params)。"""
    _CATALOG["_test.tpl"] = {"zh": "市场 {market} 不支持", "en": "Market {market} not supported"}
    try:
        assert translate("_test.tpl", "zh", market="crypto") == "市场 crypto 不支持"
        assert translate("_test.tpl", "en", market="crypto") == "Market crypto not supported"
    finally:
        del _CATALOG["_test.tpl"]


def test_catalog_every_key_has_zh() -> None:
    """★不变式:每个 key 必有 zh(zh 是兜底语言·缺 zh 会 KeyError)。"""
    for key, entry in _CATALOG.items():
        assert "zh" in entry, f"catalog key {key!r} 缺 zh"
