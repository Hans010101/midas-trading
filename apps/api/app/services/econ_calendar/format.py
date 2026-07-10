"""事件 → 决策卡文本(prompt 注入段 + 用户可见风险提示)· 全纯模板零 LLM。

🔴🔴 红线(机器验证 · test_econ_redline):
- 事件只作「结构体检的风险提示」:陈述事件与时间 + 波动可能放大,★绝不含任何
  方向词(买/卖/做多/做空/抄底/逃顶/加仓/减仓/入场/离场/上车/清仓/建仓)。
- 用户可见提示 = 纯字符串模板(非 LLM 生成)→ 方向词结构性不可能出现
  (标题来自 rules/fetchers 白名单 · 本模块只拼接)。
- 免责口径不变:提示尾带完整「仅供参考,不构成投资建议」(产品 AI 输出红线)。
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from app.models.econ_event import EconEvent

_CST = ZoneInfo("Asia/Shanghai")


def _fmt_line(ev: EconEvent) -> str:
    """单事件行(北京时间口径 · 未确认时刻标「待定」)。"""
    local = ev.scheduled_at.astimezone(_CST)
    when = f"{local:%m-%d %H:%M}" if ev.time_confirmed else f"{local:%m-%d}(时刻待定)"
    return f"{when} {ev.title}"


def format_events_for_prompt(events: list[EconEvent], language: str = "zh") -> str:
    """LLM prompt 注入段:未来 7 天重大事件(仅风险背景)。空事件 → 空串(prompt 零变化)。"""
    if not events:
        return ""
    lines = [_fmt_line(e) for e in events]
    if language == "en":
        head = "## Upcoming major macro events (next 7 days · risk context ONLY)"
        tail = (
            "IMPORTANT: treat these events ONLY as volatility-risk context. "
            "NEVER derive any directional view or action from them."
        )
    else:
        head = "## 未来7天重大事件(仅作波动风险背景)"
        tail = "★以上事件仅提示事件前后波动可能放大,绝不能据此给出方向判断或操作暗示。"
    return "\n".join(["", head, *[f"  {ln}" for ln in lines], tail])


def build_event_risk(events: list[EconEvent], language: str = "zh") -> str | None:
    """用户可见「近期重大事件风险提示」· ★纯模板(零 LLM · 红线机器可证)· 无事件 → None。"""
    if not events:
        return None
    items = "、".join(_fmt_line(e) for e in events[:3])  # 最多 3 条免噪音
    if language == "en":
        items_en = "; ".join(_fmt_line(e) for e in events[:3])
        return (
            f"Upcoming major events: {items_en}. Market volatility has historically been "
            "elevated around such events. For reference only; not investment advice."
        )
    return (
        f"近期重大事件:{items}。历史上此类事件前后市场波动可能放大,请留意风险。"
        "仅供参考,不构成投资建议。"
    )
