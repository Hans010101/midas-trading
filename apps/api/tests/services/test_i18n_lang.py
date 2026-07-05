"""i18n · 后端本地化地基测试(resolve_lang ★收窄=X-Lang>zh + translate + ★zh 逐字节铁证)。

★2026-07-05 收窄(docs/decisions/0047):resolve_lang 停用 ② language_pref 与 ③ Accept-Language
  两级 —— 无语言切换 UI 时任何自动 en 判定都是 bug。现仅 ① 显式 X-Lang/?lang → ④ zh。
"""

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


# ===== resolve_lang ★收窄:X-Lang > zh(② language_pref / ③ Accept-Language 已停用)=====


def test_resolve_lang_default_zh() -> None:
    """★zh 零变化:无任何语言信号 → zh(现有中文用户全走这里)。"""
    assert resolve_lang(_req()) == "zh"
    assert resolve_lang(_req(), None) == "zh"


def test_resolve_lang_explicit_header_top_priority() -> None:
    """① 显式 X-Lang / ?lang 是【唯一】自动来源(海外版 / 联调注入)· 仍压过一切。"""
    r = _req({"x-lang": "en", "accept-language": "zh-CN"})
    assert resolve_lang(r, "zh") == "en"
    assert resolve_lang(cast("Any", _req(query="lang=en")), "zh") == "en"


def test_resolve_lang_ignores_language_pref() -> None:
    """★收窄:② language_pref 已停用 —— 无显式 X-Lang 时 language_pref='en' 也返 zh。

    这是生产 bug 根治点:Hans 账号 pref='en' 曾致决策卡英文;现 pref 彻底不参与解析。
    """
    r = _req({"accept-language": "zh-CN"})
    assert resolve_lang(r, "en") == "zh"          # pref='en' 被忽略 → zh
    assert resolve_lang(_req(), "en") == "zh"     # 无任何头 · pref='en' → zh
    # 但显式 X-Lang 仍生效(能力保留):pref 无关
    assert resolve_lang(_req({"x-lang": "en"}), "zh") == "en"


def test_resolve_lang_ignores_accept_language() -> None:
    """★收窄:③ Accept-Language 已停用 —— 英文浏览器(无 X-Lang)也返 zh(纯中文产品)。"""
    assert resolve_lang(_req({"accept-language": "en-US,en;q=0.9,zh;q=0.8"}), None) == "zh"
    assert resolve_lang(_req({"accept-language": "en-US,en;q=0.9"}), "en") == "zh"  # pref 也忽略
    # X-Lang 显式仍出英文(能力铁证)
    assert resolve_lang(_req({"x-lang": "en", "accept-language": "en-US"}), None) == "en"


def test_resolve_lang_normalize_x_lang() -> None:
    """X-Lang 归一:EN→en · 不识别 → zh 兜底(② ③ 停用后 X-Lang 是唯一自动来源)。"""
    assert resolve_lang(_req({"x-lang": "EN"})) == "en"
    assert resolve_lang(_req({"x-lang": "en-US"})) == "en"       # locale 串归一
    assert resolve_lang(_req({"x-lang": "ja"})) == "zh"          # 不支持 → 兜底 zh
    assert resolve_lang(_req({"x-lang": "zh-CN"})) == "zh"


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
