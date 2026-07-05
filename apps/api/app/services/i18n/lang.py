"""请求语言解析 · i18n Phase3 刀1(后端文案本地化地基)。

★2026-07-05 收窄(Hans 拍板 · 生产 bug 修复 · docs/decisions/0047):
  产品当前【纯中文·无语言切换 UI】。原四级(X-Lang > language_pref > Accept-Language > zh)在
  无切换 UI 下会把请求判成 en → 用户看到英文却【无法切回】= bug 不是 feature。故收窄为二级:
    ① 显式 `?lang` query / `X-Lang` header(海外版 / 联调显式注入 · 唯一自动来源)
    ④ 默认 `zh`
  ② 登录用户 `language_pref` 与 ③ `Accept-Language` 两级【停用】(见 resolve_lang docstring)。
★zh 零变化:无 X-Lang → 返回 "zh" → 全链路走原中文分支(逐字节不变)· 现覆盖【全部】无显式头请求。
★双语能力全保留:translate/catalog/en prompt 代码一字不删 · X-Lang:en 仍出英文(能力铁证)·
  未来海外版把 ②③ 两级扩回 resolve_lang 即恢复四级。
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
    """解析请求语言 · ★2026-07-05 收窄:仅显式 X-Lang/?lang override,否则默认 zh。

    收窄前是四级(X-Lang > language_pref > Accept-Language > zh);现【停用】② language_pref
    与 ③ Accept-Language 两级 —— 无语言切换 UI 时任何自动 en 判定都是 bug(用户看到英文却切不回)。
    详见模块 docstring + docs/decisions/0047。

    · `language_pref` 入参【保留】(RequestLangDep / auth 等所有调用点签名不改),但不再读取;
      未来海外版恢复四级时在此扩回即可。X-Lang:en 仍出英文(双语能力铁证)。
    """
    _ = language_pref  # ★收窄:language_pref 停用(保留入参兼容调用点 · 未来海外版扩回)
    # ① 显式 ?lang / X-Lang(唯一自动来源 · 海外版 / 联调注入)
    explicit = request.query_params.get("lang") or request.headers.get("x-lang")
    if lang := _normalize(explicit):
        return lang
    # ④ 默认 zh(② language_pref / ③ Accept-Language 已停用 · zh 逐字节零变化 · 见 docstring)
    return DEFAULT_LANG


__all__ = ["DEFAULT_LANG", "SUPPORTED_LANGS", "resolve_lang"]
