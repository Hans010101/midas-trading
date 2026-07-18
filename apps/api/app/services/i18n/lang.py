"""请求语言解析 · i18n Phase3 刀1(后端文案本地化地基)。

★沿革:
  · 2026-07-05 收窄(docs/decisions/0047):产品纯中文无切换 UI 时,四级里的自动 en 判定会让用户
    看到英文却切不回 = bug。故当时收窄为二级(仅 ① X-Lang / ④ zh),停用 ② + ③ 两级。
  · 2026-07-16 海外版激活(docs/decisions/0056):前端语言切换 UI 上线(LanguageToggle + 设置页),
    ★与本次扩回【原子】。扩回 ② language_pref —— 现在安全:用户可随时切回 zh、language_pref 由用户
    显式设定,不再是"被自动判成 en"。现三级:
      ① 显式 `?lang` / `X-Lang`(前端切换即时注入 · guest 也走它)
      ② 登录用户 `language_pref`(切换 UI 的 PATCH /user/language 落库 · 持久 + 跨设备)
      ④ 默认 `zh`
    ★③ Accept-Language 仍【停用】—— 它按浏览器语言自动判 en,正是 0047 的 bug 源,坚决不扩。
★zh 零变化:无 X-Lang 且 language_pref 空/zh → 返回 "zh" → 全链路走原中文分支(逐字节不变)。
★双语能力全保留:translate/catalog/en prompt 代码一字不删 · X-Lang:en 仍出英文(能力铁证)。
★纯函数(不依赖 DB / current_user)—— 供 deps 的鉴权前错误(pre-auth)直接用 header 取语言;
  端点侧带 language_pref 的 Dep 在 deps.py 组装(避免与 deps 循环 import)。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

# 目前只支持中英双语(与 language_pref 的 `^(zh|en)$` 约束一致)。
SUPPORTED_LANGS = ("zh", "en")
DEFAULT_LANG = "zh"


def _normalize(value: str | None) -> str | None:
    """把任意 locale 串归一到 zh / en(如 'en-US'→'en'·'zh-CN'→'zh')· 无法识别返 None。"""
    if not value:
        return None
    v = value.strip().lower()
    if v.startswith("zh"):
        return "zh"
    if v.startswith("en"):
        return "en"
    return None


def resolve_lang(request: Request, language_pref: str | None = None) -> str:
    """解析请求语言 · ★2026-07-16 海外版激活:扩回 ② language_pref(与前端语言切换 UI 原子上线)。

    三级(★不含 ③ Accept-Language):
      ① 显式 `?lang` / `X-Lang`(前端切换即时注入 · guest 也走它)
      ② 登录用户 `language_pref`(切换 UI 的 PATCH /user/language 落库 · 跨设备/跨请求持久)
      ④ 默认 `zh`
    ★为什么扩回 ② 而不扩 ③(docs/decisions/0047 收窄根因 · 必须守住):无语言切换 UI 时任何自动
      en 判定都是 bug(用户看到英文却切不回)。② 现在安全 = 前端【已有语言切换 UI】(LanguageToggle
      + 设置页),用户可随时切回 zh、language_pref 由用户显式设定,不再是"被自动判成 en"。
      ③ Accept-Language 仍【停用】—— 它按浏览器语言自动判 en,正是当年 bug 源,不扩。
    ★两者【原子】:扩回 ② 必须与切换 UI 同刀上线,单扩 ② 无 UI = #162 重演。
    ★zh 零变化:无 X-Lang 且 language_pref 为空/zh → 返回 "zh" → 全链路走原中文分支(逐字节不变)。
    ★纯函数(不依赖 DB):language_pref 由调用点(deps.py 组装 RequestLangDep 时)传入。
    """
    # ① 显式 ?lang / X-Lang(前端切换即时注入 · guest 也走它 · 唯一自动来源之外的显式 override)
    explicit = request.query_params.get("lang") or request.headers.get("x-lang")
    if lang := _normalize(explicit):
        return lang
    # ② 登录用户 language_pref(扩回 · 与切换 UI 原子 · 见 docstring)
    if lang := _normalize(language_pref):
        return lang
    # ④ 默认 zh(③ Accept-Language 仍停用 · zh 逐字节零变化)
    return DEFAULT_LANG


__all__ = ["DEFAULT_LANG", "SUPPORTED_LANGS", "resolve_lang"]
