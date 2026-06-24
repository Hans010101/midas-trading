"""做T 定时全景(体系1 · M2-3a · ★影子模式)纯逻辑 —— 读 A-1 快照分类组装,不重算。

体系1 = 每小时整点读 boll:snapshot:latest(150 币 6 态结构)→ 按结构倾向分【偏多/中性/偏空】三组 →
每组按 %B 极端程度取前 5 → 组装「图1」分组全景消息(SYMBOL 超链接到详情页)。

★与体系2(boll_scan 边沿影子推送)正交:体系2 是「状态转换」事件流,本体系是「定时快照全景」。
★纯逻辑(无 Redis/IO/datetime.now):快照 items 由 worker 读入传进来,now 由 worker 注入(可单测)。
🔴 红线:纯展示 · 倾向只偏多/偏空/中性 · 末尾「· 仅供参考」过 validate_shadow_push · 无买卖词。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.services.ai.boll_state import PUSH_DISCLAIMER, validate_shadow_push
from app.services.notifications.quiet import _hour_in_quiet_window

# 详情页深链(SYMBOL 超链接目标 · Telegram Markdown [text](url))
DETAIL_URL = "https://midastrade.asia/crypto-preview"
_TOP_N = 5  # 每组取前 N(按 %B 极端程度)

# ── M2-3a 全局安静时段(白天 07–22 推 · 夜间 23–06 跳)· 对齐 notification_config 默认窗口 ──
#   ★M2-3a 全局统一时段;M2-5 真发再按用户级 quiet_hours。复用 quiet 单一事实源跨夜逻辑。
QUIET_START, QUIET_END = 23, 7
QUIET_TZ = "Asia/Shanghai"


def is_global_quiet_hour(now: datetime) -> bool:
    """当前是否处于全局安静时段(夜间)· 复用 quiet._hour_in_quiet_window 跨夜判定 · 在内则不推。"""
    hour = now.astimezone(ZoneInfo(QUIET_TZ)).hour
    return _hour_in_quiet_window(hour, QUIET_START, QUIET_END)


def _change_str(change_pct_24h: float | None) -> str:
    return f"{change_pct_24h:+.1f}%" if change_pct_24h is not None else "—"


def _coin_line(item: dict[str, Any]) -> str:
    """单币一行:[SYMBOL](详情页)｜状态 · 通道位置(%B) · 24h涨跌(★超链接 Markdown · 无买卖词)。"""
    sym = item["symbol"]
    url = f"{DETAIL_URL}?symbol={sym}"
    pct_b = float(item["pct_b"])
    chg = _change_str(item.get("change_pct_24h"))
    return (
        f"  [{sym}]({url})｜{item['state_label']} · "
        f"{item['zone_label']}(%B={pct_b:.2f}) · {chg}"
    )


# 三组排序键 · emoji 用方向性 📈➖📉(★不用 🟢🔴 红绿 · 避开用户涨跌色偏好冲突)
def _abs_change(item: dict[str, Any]) -> float:
    return abs(float(item.get("change_pct_24h") or 0.0))


def build_hourly_digest(items: list[dict[str, Any]], *, as_of_label: str) -> str | None:
    """快照 items → 图1 分组全景消息(经 validate_shadow_push)· 无任何可分组候选 → None(不推)。

    分组排序:偏多按 %B 高→低(最破上轨最强)· 偏空按 %B 低→高(最破下轨最强)· 中性按 |24h涨跌| 高→低
    (中性 %B 居中,用活跃度作次级)· 每组取前 5 · 不足按实际 · 空组省略。
    """
    groups: list[tuple[str, str, Any]] = [
        ("📈 偏多", "偏多", lambda it: -float(it["pct_b"])),
        ("➖ 中性", "中性", lambda it: -_abs_change(it)),
        ("📉 偏空", "偏空", lambda it: float(it["pct_b"])),
    ]
    lines = [f"📊 做T扫描 · {as_of_label}"]
    shown = False
    for title, bias, keyfn in groups:
        members = [it for it in items if it.get("bias") == bias]
        if not members:
            continue  # 空组省略
        shown = True
        top = sorted(members, key=keyfn)[:_TOP_N]
        lines.append(f"{title}({len(members)})")  # N = 该倾向全量数 · 下列前 5
        lines.extend(_coin_line(it) for it in top)
    if not shown:
        return None  # 全组皆空(无快照 / 无有效结构)→ 不推
    lines.append(PUSH_DISCLAIMER)  # 末尾唯一「· 仅供参考」· 过门禁
    return validate_shadow_push("\n".join(lines))
