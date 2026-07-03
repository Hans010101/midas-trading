"""请求语言解析 · i18n Phase3 刀1(后端文案本地化地基)。

★决策(Hans 拍板 2026-07-03)四级优先级:
  ① 显式 `?lang` query / `X-Lang` header(前端 next-intl locale 注入·点金-3 激活时接)
  ② 登录用户 `user.language_pref`
  ③ `Accept-Language` header(未登录/鉴权前错误的兜底 —— 这是英文用户最需要英文的时刻)
  ④ 默认 `zh`
★zh 零变化:无任何信号 → 返回 "zh" → 全链路走原中文分支(逐字节不变)。
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
    """解析请求语言 · 四级优先级(见模块 docstring)· 兜底 zh。

    pre-auth(鉴权前错误)调用时 language_pref 传 None,只走 header/query;
    端点侧带登录用户时把 user.language_pref 传进来。
    """
    # ① 显式 ?lang / X-Lang(前端可显式注入·最高优先)
    explicit = request.query_params.get("lang") or request.headers.get("x-lang")
    if lang := _normalize(explicit):
        return lang
    # ② 登录用户偏好
    if lang := _normalize(language_pref):
        return lang
    # ③ Accept-Language(按 q 值顺序取首个可识别的 zh/en)
    accept = request.headers.get("accept-language")
    if accept:
        for part in accept.split(","):
            code = part.split(";")[0].strip()
            if lang := _normalize(code):
                return lang
    # ④ 默认 zh(zh 零变化:现有中文用户全走这里)
    return DEFAULT_LANG


__all__ = ["DEFAULT_LANG", "SUPPORTED_LANGS", "resolve_lang"]
