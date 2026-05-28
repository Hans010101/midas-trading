"""安静时段(quiet hours)判定 helper · 0028 N1 · 单一事实源。

供 dispatcher 和 老 price_alerts worker 共用 · 行为一致:
- `is_in_quiet_now(config, now=None)`:用户当前时区下是否处于安静窗口
- `is_quiet_exempt(event)`:事件类是否标记为 quiet_exempt(钱相关 · 0028 DP10)

跨夜窗口处理(start > end · 如 23-7):hour ≥ start OR hour < end。
start==end 视为禁用(等同 enabled=False · 永不在窗口内)。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from app.models.notification import NotificationConfig
    from app.services.notifications.events import NotificationEvent


def _hour_in_quiet_window(hour: int, start: int, end: int) -> bool:
    """判定 `hour` 是否在 `[start, end)` 安静窗口内(支持跨夜)。

    - start < end:普通窗口(如 1–7)· `start ≤ hour < end`
    - start > end:跨夜窗口(如 23–7)· `hour ≥ start` 或 `hour < end`
    - start == end:视为禁用(永不在)· 让用户用 `enabled=False` 关闭即可
    """
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def is_in_quiet_now(
    config: NotificationConfig | None, now: datetime | None = None,
) -> bool:
    """当前(用户时区)是否处于安静窗口。

    - config 为 None / quiet_hours_enabled=False → 总返回 False
    - 时区取 config.quiet_hours_tz(默认 'Asia/Shanghai' · DP5 主力东八)
    - now 可注入用于测试;线上 None 自动取实时
    """
    if config is None or not config.quiet_hours_enabled:
        return False
    tz = ZoneInfo(config.quiet_hours_tz)
    current = now.astimezone(tz) if now is not None else datetime.now(tz=tz)
    return _hour_in_quiet_window(
        current.hour, config.quiet_hours_start, config.quiet_hours_end,
    )


def is_quiet_exempt(event: NotificationEvent) -> bool:
    """事件是否豁免安静时段(0028 DP10)· 读 ClassVar `quiet_exempt`。"""
    return getattr(type(event), "quiet_exempt", False)
