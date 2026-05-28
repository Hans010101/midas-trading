"""Bot 安静时段操作(核心层 · 平台无关)· 0028 N3 · 复用 N2 quiet_hours 字段。

bot 内查看 + 启停 + 起止小时步进。时区切换不在 bot 做(留网页 · DP9 决策)。

🔴 红线 R1(N3 身份隔离 · 跟 G3/G4/G5 一脉相承):
- user_id 是【入参】· 由调用方(router)从已验证 chat.id 经 resolve_user_id
  解析后传入。本模块【绝不】解析身份、【绝不】接受 chat_id / target_user_id
  / "另一个用户的 id" 等参数。
- 所有读写都按 NotificationConfig.user_id == 入参 user_id 限定。
  NotificationConfig.user_id 是 PK,user-config 一对一,跨用户隔离由 schema 保证。
- 未配置 → lazy create(同 N2 PUT 路由)· 入库的 user_id 永远是入参 user_id。

🔴 红线 R2(本期只动 quiet_hours 字段):
- 不改 trade_alert_enabled / price_alert_enabled / tg_chat_id 等其他字段。
- 不碰 N1 边沿触发 / dispatcher / alert_scan / price_alerts / quiet helper。
- 不调 N2 的 REST 接口(避免 self-loopback)· 直接走同款 model 写入逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.notification import NotificationConfig

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

# 0-23 循环 · 23 +1 → 0 · 0 -1 → 23(Python `%` 对负数取模天然回卷:`(0-1)%24==23`)
_HOURS_MOD = 24

# 未配置用户的默认 view(对齐 model server_default + N2 default_config_response · DP4/DP5)
_DEFAULT_ENABLED = True
_DEFAULT_START = 23
_DEFAULT_END = 7
_DEFAULT_TZ = "Asia/Shanghai"


@dataclass(frozen=True)
class QuietHoursView:
    """安静时段配置(bot 渲染用 · 平台无关)。"""

    enabled: bool
    start_hour: int  # 0-23
    end_hour: int    # 0-23
    tz: str          # IANA name(bot 不改 · 留网页)


def _to_view(config: NotificationConfig) -> QuietHoursView:
    return QuietHoursView(
        enabled=config.quiet_hours_enabled,
        start_hour=config.quiet_hours_start,
        end_hour=config.quiet_hours_end,
        tz=config.quiet_hours_tz,
    )


async def _get_or_create(db: AsyncSession, user_id: UUID) -> NotificationConfig:
    """lazy create NotificationConfig · 同 N2 PUT 内部逻辑 · user_id 永远是入参。"""
    config = await db.scalar(
        select(NotificationConfig).where(NotificationConfig.user_id == user_id),
    )
    if config is None:
        config = NotificationConfig(user_id=user_id)
        db.add(config)
        # flush 让 INSERT 命中 PG · 拿 server_default 回填 4 个 quiet_hours 字段
        await db.flush()
        await db.refresh(config)
    return config


async def load_quiet_hours(db: AsyncSession, user_id: UUID) -> QuietHoursView:
    """读取当前 quiet_hours · 未配置返回默认 view(不 lazy create · 只读)。

    默认值跟 N2 default_config_response 对齐:23-7 / Asia/Shanghai / 启用。
    """
    config = await db.scalar(
        select(NotificationConfig).where(NotificationConfig.user_id == user_id),
    )
    if config is None:
        return QuietHoursView(
            enabled=_DEFAULT_ENABLED,
            start_hour=_DEFAULT_START,
            end_hour=_DEFAULT_END,
            tz=_DEFAULT_TZ,
        )
    return _to_view(config)


async def toggle_enabled(db: AsyncSession, user_id: UUID) -> QuietHoursView:
    """翻转启用状态 · 仅动入参 user_id 的 config · lazy create。"""
    config = await _get_or_create(db, user_id)
    config.quiet_hours_enabled = not config.quiet_hours_enabled
    await db.commit()
    await db.refresh(config)
    return _to_view(config)


async def step_start_hour(
    db: AsyncSession, user_id: UUID, delta: int,
) -> QuietHoursView:
    """起始小时 ±delta · mod 24 不越界 · 仅动入参 user_id 的 config · lazy create。

    Python `%` 对负数自然回卷:`(0 - 1) % 24 == 23` · `(23 + 1) % 24 == 0`。
    """
    config = await _get_or_create(db, user_id)
    config.quiet_hours_start = (config.quiet_hours_start + delta) % _HOURS_MOD
    await db.commit()
    await db.refresh(config)
    return _to_view(config)


async def step_end_hour(
    db: AsyncSession, user_id: UUID, delta: int,
) -> QuietHoursView:
    """结束小时 ±delta · mod 24 不越界 · 仅动入参 user_id 的 config · lazy create。"""
    config = await _get_or_create(db, user_id)
    config.quiet_hours_end = (config.quiet_hours_end + delta) % _HOURS_MOD
    await db.commit()
    await db.refresh(config)
    return _to_view(config)


__all__ = [
    "QuietHoursView",
    "load_quiet_hours",
    "step_end_hour",
    "step_start_hour",
    "toggle_enabled",
]
