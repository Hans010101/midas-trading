"""后端文案本地化表 · i18n Phase3(后端返本地化文本·前端零查表·决策C)。

★复用 validator.py 黄金范式:`{key: {zh, en}}` 表 + zh 恒等(zh 逐字节 = 今天的中文字面量)。
★不引 gettext/babel(全库零依赖)· 不复用前端 messages/*.json(跨进程读前端文件是坏耦合)。
★含运行时插值的文案用命名占位 `{name}` · translate(..., **params) 走 str.format。

刀1(本刀)只登记地基验证用的鉴权错误(deps.py · pre-auth 高价值);
刀2 补 C 端用户面错误 detail(~77)· 刀3 补规则层 label/reason(~54)· 逐刀扩表。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# {key: {"zh": 模板, "en": 模板}} · zh 为今天线上中文字面量【逐字节复刻】(zh 零变化铁证)。
_CATALOG: dict[str, dict[str, str]] = {
    # ── 鉴权层(deps.py · pre-auth · 命中每个受保护/铂金请求)──────────────
    "auth.no_token": {
        "zh": "未携带 Bearer session token",
        "en": "No Bearer session token provided",
    },
    "auth.session_invalid": {
        "zh": "session 无效或已过期 · 请重新登录",
        "en": "Session invalid or expired · please sign in again",
    },
    "auth.account_disabled": {
        "zh": "账号已被停用",
        "en": "Account has been disabled",
    },
    "auth.platinum_required": {
        "zh": "需铂金权限",
        "en": "Platinum access required",
    },
}


def translate(key: str, lang: str = "zh", /, **params: object) -> str:
    """按 key + 语言返回本地化文案(含插值)· 未登记 key / 缺该语言 → 兜底 zh(绝不炸)。

    ★zh 零变化:lang='zh' 命中的永远是 _CATALOG[key]['zh'] = 今天的中文字面量。
    ★兜底链:未登记 key → 返回 key 本身(记 warning);登记但缺 en → 回退 zh(永不缺文案)。
    """
    entry = _CATALOG.get(key)
    if entry is None:
        logger.warning("[i18n] 未登记文案 key=%r · 返回 key 兜底", key)
        return key
    template = entry.get(lang) or entry["zh"]
    return template.format(**params) if params else template


__all__ = ["translate"]
