"""i18n · 后端本地化地基测试(resolve_lang 三级=X-Lang>language_pref>zh + translate + ★zh 逐字节铁证)。

★2026-07-16 海外版激活:扩回 ② language_pref(与前端语言切换 UI 原子上线)。现三级:
  ① 显式 X-Lang/?lang → ② 登录用户 language_pref → ④ zh。
★★守住 0047 红线不变式:③ Accept-Language 仍【停用】—— 浏览器语言【绝不】自动判 en
  (那是 0047 的 bug 源);en 只能来自用户显式动作(切换 UI 的 X-Lang 注入 / 落库的 language_pref)。
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


def test_resolve_lang_honors_language_pref() -> None:
    """★扩回:② language_pref 已启用 —— 无显式 X-Lang 时按登录用户 language_pref 出语言。

    安全前提=前端已有语言切换 UI:language_pref 由用户显式设定(切换 UI PATCH 落库),
    可随时切回 zh,不再是"被自动判成 en 却切不回"(0047 的 bug 已由切换 UI 消除)。
    """
    assert resolve_lang(_req(), "en") == "en"     # 无头 · pref='en' → en(扩回生效)
    assert resolve_lang(_req(), "zh") == "zh"     # pref='zh' → zh
    assert resolve_lang(_req(), None) == "zh"     # 未设 pref → 默认 zh
    # ① X-Lang 仍压过 ② pref:X-Lang=zh 显式切回 → zh(即便 pref=en)
    assert resolve_lang(_req({"x-lang": "zh"}), "en") == "zh"
    assert resolve_lang(_req({"x-lang": "en"}), "zh") == "en"


def test_resolve_lang_ignores_accept_language() -> None:
    """★★守住 0047 红线:③ Accept-Language 仍【停用】—— 英文浏览器【绝不】自动判 en。

    这是 0047 bug 的根源(浏览器语言自动判 en 用户切不回),扩回 ② 时坚决不扩 ③。
    en 只能来自显式动作(X-Lang / 落库 language_pref),浏览器 Accept-Language 一律不参与。
    """
    # 英文浏览器 · 无 pref · 无 X-Lang → 仍 zh(Accept-Language 不参与)
    assert resolve_lang(_req({"accept-language": "en-US,en;q=0.9,zh;q=0.8"}), None) == "zh"
    assert resolve_lang(_req({"accept-language": "en-US,en;q=0.9"}), "zh") == "zh"
    # 显式来源仍生效:X-Lang(en)或落库 pref(en)才出英文,与 Accept-Language 无关
    assert resolve_lang(_req({"x-lang": "en", "accept-language": "zh-CN"}), None) == "en"
    assert resolve_lang(_req({"accept-language": "zh-CN"}), "en") == "en"  # pref=en(显式)→ en


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
