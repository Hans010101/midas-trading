"""语言锁 · 第二层(Python CJK 码点检测兜底)· i18n Phase4 刀2。

★为什么要 Python 兜底(不能只靠 prompt):DeepSeek 已知 bug(repo Issue #1226)—— 纯英文
  对话偶尔整段回中文。prompt 里的 [LANGUAGE LOCK] 挡不住 100%。所以英文 AI 产出后,再用
  Python 检测 CJK 码点:一旦检出中文字符 → 触发【重试一次 → 仍中文则降级英文兜底】,
  绝不让中文漏到英文用户(Hans 红线:不让中文漏到英文用户)。

  第一层(prompt 内 [LANGUAGE LOCK])+ 第二层(这里的 CJK 检测)= 双层·缺一不可。

策略(各 agent 统一遵循 · 见 technical.py / plan_note.py 的 en 分支):
  1. 英文 prompt 首次生成。
  2. contains_cjk(输出) → True:用 LANGUAGE_LOCK_RETRY_PREFIX 加强提示【重试一次】。
  3. 重试仍 contains_cjk → **降级**:换成该 agent 的安全英文兜底文本(数字/评分是语言中立的,
     保留;只替换会串台的自由文本),并 log warning【标记】供可观测。
  4. 全程不抛异常 · 不阻断决策卡(同 0012 § 失败回退)。
"""

from __future__ import annotations

import re

# CJK 码点范围(检测「输出里混进了中文」)· 用 \u/\U 转义避免字面字符歧义:
#   3000-303F  CJK 符号和标点(、。「」等)
#   3400-4DBF  CJK 扩展 A
#   4E00-9FFF  CJK 统一表意文字(常用汉字主体)
#   F900-FAFF  CJK 兼容表意文字
#   FF00-FFEF  全角 ASCII / 半角形式(全角标点如逗号句号)
#   20000-2A6DF CJK 扩展 B(生僻字 · 星平面)
_CJK_RE = re.compile(
    "[　-〿㐀-䶿一-鿿豈-﫿＀-￯"
    "\U00020000-\U0002a6df]",
)

# 重试时前置到 user prompt 顶部的强化语言锁提示(DeepSeek 给第二次机会)。
LANGUAGE_LOCK_RETRY_PREFIX = (
    "[STRICT RETRY] Your previous answer contained Chinese characters. Respond ENTIRELY "
    "in English this time — zero Chinese characters, no exceptions.\n\n"
)


def contains_cjk(text: str) -> bool:
    """文本是否含 CJK 码点(中文串台检测)· 空/None 安全。"""
    if not text:
        return False
    return _CJK_RE.search(text) is not None


__all__ = ["LANGUAGE_LOCK_RETRY_PREFIX", "contains_cjk"]
