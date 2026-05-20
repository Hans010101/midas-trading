"""通知派发器 · 0009 § 3。

按用户 config 派发到 0~2 个通道,每通道失败独立(一边挂不影响另一边)。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationConfig
from app.services.notifications import feishu, telegram
from app.services.notifications.events import (
    NotificationEvent,
    NotificationKind,
    PriceAnomalyEvent,
    TradeFilledEvent,
)
from app.services.notifications.templates import (
    render_feishu,
    render_feishu_test,
    render_telegram,
    render_telegram_test,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChannelResult:
    channel: str  # 'feishu' / 'telegram'
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class DispatchResult:
    results: list[ChannelResult]

    @property
    def any_sent(self) -> bool:
        return any(r.ok for r in self.results)

    @property
    def any_error(self) -> bool:
        return any(not r.ok for r in self.results)


async def get_config(
    db: AsyncSession, user_id: UUID,
) -> NotificationConfig | None:
    stmt = select(NotificationConfig).where(
        NotificationConfig.user_id == user_id,
    )
    result: NotificationConfig | None = await db.scalar(stmt)
    return result


async def dispatch(
    db: AsyncSession,
    user_id: UUID,
    event: NotificationEvent,
    *,
    client: httpx.AsyncClient | None = None,
) -> DispatchResult:
    """根据用户配置派发到对应通道 · per-channel 失败独立。"""
    config = await get_config(db, user_id)
    if config is None:
        return DispatchResult(results=[])

    # 总开关 · 事件类型过滤
    if (
        event.kind == NotificationKind.TRADE_FILLED
        and not config.trade_alert_enabled
    ):
        logger.info("[notify] trade alert disabled · user=%s", user_id)
        return DispatchResult(results=[])
    if (
        event.kind == NotificationKind.PRICE_ANOMALY
        and not config.price_alert_enabled
    ):
        logger.info("[notify] price alert disabled · user=%s", user_id)
        return DispatchResult(results=[])

    results: list[ChannelResult] = []

    # 飞书
    if config.feishu_webhook_url:
        try:
            payload = render_feishu(event)
            await feishu.send(config.feishu_webhook_url, payload, client=client)
            results.append(ChannelResult(channel="feishu", ok=True))
        except Exception as e:  # noqa: BLE001
            logger.warning("[notify] feishu failed · user=%s err=%s", user_id, e)
            results.append(
                ChannelResult(channel="feishu", ok=False, error=str(e)),
            )

    # Telegram
    if config.tg_bot_token and config.tg_chat_id:
        try:
            text = render_telegram(event)
            await telegram.send(
                config.tg_bot_token, config.tg_chat_id, text, client=client,
            )
            results.append(ChannelResult(channel="telegram", ok=True))
        except Exception as e:  # noqa: BLE001
            logger.warning("[notify] telegram failed · user=%s err=%s", user_id, e)
            results.append(
                ChannelResult(channel="telegram", ok=False, error=str(e)),
            )

    return DispatchResult(results=results)


async def send_test(
    config: NotificationConfig,
    channel: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> ChannelResult:
    """「发送测试消息」按钮入口 · 单通道。"""
    if channel == "feishu":
        if not config.feishu_webhook_url:
            return ChannelResult(
                channel="feishu", ok=False, error="未配置 webhook URL",
            )
        try:
            await feishu.send(
                config.feishu_webhook_url, render_feishu_test(), client=client,
            )
            return ChannelResult(channel="feishu", ok=True)
        except Exception as e:  # noqa: BLE001
            return ChannelResult(channel="feishu", ok=False, error=str(e))

    if channel == "telegram":
        if not config.tg_bot_token or not config.tg_chat_id:
            return ChannelResult(
                channel="telegram", ok=False, error="未配置 token 或 chat_id",
            )
        try:
            await telegram.send(
                config.tg_bot_token, config.tg_chat_id,
                render_telegram_test(), client=client,
            )
            return ChannelResult(channel="telegram", ok=True)
        except Exception as e:  # noqa: BLE001
            return ChannelResult(channel="telegram", ok=False, error=str(e))

    return ChannelResult(channel=channel, ok=False, error="未知通道")


# Re-export for routes / tasks
__all__ = [
    "ChannelResult",
    "DispatchResult",
    "NotificationEvent",
    "PriceAnomalyEvent",
    "TradeFilledEvent",
    "dispatch",
    "get_config",
    "send_test",
]
