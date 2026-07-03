"""后端文案本地化 · i18n Phase3(后端返本地化文本·前端零查表·决策C)。

- resolve_lang(request, language_pref):四级优先级解析请求语言(见 lang.py)。
- translate(key, lang, **params):按 key + 语言返回本地化文案(见 catalog.py)。
★zh 零变化:无语言信号 → zh → 命中今天的中文字面量,逐字节不变。
"""

from __future__ import annotations

from app.services.i18n.catalog import translate
from app.services.i18n.lang import DEFAULT_LANG, SUPPORTED_LANGS, resolve_lang

__all__ = ["DEFAULT_LANG", "SUPPORTED_LANGS", "resolve_lang", "translate"]
