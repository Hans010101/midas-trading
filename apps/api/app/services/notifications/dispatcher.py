"""通知派发器 · 0009 § 3 → 0025 G2a 核心层。

平台无关编排:决定「给哪个 user、发哪个 event、走哪些已启用通道」;
具体「怎么发」委托给 adapters(本期只 Telegram 统一 bot)。

派发条件(0025):用户已绑定(notification_config.tg_chat_id 非空)且统一 bot
已配置(全局 settings.tg_bot_token)→ 发 Telegram。不再有飞书 / per-user token。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.notification import NotificationConfig
from app.services.notifications.adapters import feishu as feishu_adapter
from app.services.notifications.adapters import telegram as tg_adapter
from app.services.notifications.events import (
    NotificationEvent,
    NotificationKind,
    PriceAnomalyEvent,
    TradeFilledEvent,
)
from app.services.notifications.quiet import is_in_quiet_now, is_quiet_exempt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChannelResult:
    channel: str  # 本期只 'telegram'
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class DispatchResult:
    results: list[ChannelResult]
    # 0028 N1:被 quiet 时段拦截(true=普通告警在安静窗口内被吞 · alert_scan 用此判定
    # 是否更新 state,避免下次扫描仍判为 edge 反复空转)
    dropped_quiet: bool = False

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


def _kind_enabled(event: NotificationEvent, config: NotificationConfig) -> bool:
    # #296:perp 成交 / 强平 复用现有「成交通知」总开关(不新增列/迁移)
    if event.kind in (
        NotificationKind.TRADE_FILLED,
        NotificationKind.PERP_FILLED,
        NotificationKind.LIQUIDATION,
    ):
        return config.trade_alert_enabled
    if event.kind == NotificationKind.PRICE_ANOMALY:
        return config.price_alert_enabled
    if event.kind == NotificationKind.WEEKLY_REPORT:
        # P3:市场周报订阅开关(weekly_report_enabled 同时也是收件人筛选条件)
        return config.weekly_report_enabled
    if event.kind == NotificationKind.WEEKLY_REPORT_SKIPPED:
        # 运营 ops 提醒(只发 admin · 不受订阅开关控制 · 恒发)
        return True
    return True


async def dispatch(
    db: AsyncSession,
    user_id: UUID,
    event: NotificationEvent,
    *,
    client: httpx.AsyncClient | None = None,
) -> DispatchResult:
    """根据用户配置派发到统一 bot Telegram · 失败独立成 ChannelResult,绝不抛。"""
    config = await get_config(db, user_id)
    if config is None:
        return DispatchResult(results=[])

    if not _kind_enabled(event, config):
        logger.info("[notify] %s disabled · user=%s", event.kind, user_id)
        return DispatchResult(results=[])

    # 0028 N1 安静时段:在 quiet 窗口内吞掉【非豁免】事件(普通市场告警)。
    # 豁免:TradeFilledEvent(钱相关 · 0028 DP10)照常发,夜间也不漏。
    if not is_quiet_exempt(event) and is_in_quiet_now(config):
        logger.info(
            "[notify] quiet hours · dropped event=%s user=%s",
            event.kind, user_id,
        )
        return DispatchResult(results=[], dropped_quiet=True)

    results: list[ChannelResult] = []

    # 统一 bot Telegram:已绑定(tg_chat_id)且全局 bot 已配置才发。
    # 未配 token(统一 bot 未启用)或未绑定 → 静默跳过(不报错),与「未启用」一致。
    if config.tg_chat_id and settings.tg_bot_token:
        try:
            await tg_adapter.send_event(config.tg_chat_id, event, client=client)
            results.append(ChannelResult(channel=tg_adapter.CHANNEL, ok=True))
        except Exception as e:  # noqa: BLE001 · 通道失败独立 · 不影响调用方
            logger.warning(
                "[notify] telegram failed · user=%s err=%s", user_id, e,
            )
            results.append(
                ChannelResult(channel=tg_adapter.CHANNEL, ok=False, error=str(e)),
            )

    # 飞书(ADR 0032 阶段二):已绑定(feishu_open_id)且飞书应用已配置才发。
    # 与 TG 独立 · 两通道都绑则【都发】(本期无偏好,后续可加)· 任一通道失败不影响另一个。
    feishu_open_id = config.feishu_open_id
    if feishu_open_id and settings.feishu_app_id and settings.feishu_app_secret:
        try:
            await feishu_adapter.send_event(feishu_open_id, event, client=client)
            results.append(ChannelResult(channel=feishu_adapter.CHANNEL, ok=True))
        except Exception as e:  # noqa: BLE001 · 通道失败独立 · 不影响调用方
            logger.warning(
                "[notify] feishu failed · user=%s err=%s", user_id, e,
            )
            results.append(
                ChannelResult(channel=feishu_adapter.CHANNEL, ok=False, error=str(e)),
            )

    return DispatchResult(results=results)


async def send_test(
    config: NotificationConfig,
    channel: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> ChannelResult:
    """「发送测试消息」按钮入口 · 支持 telegram / feishu(ADR 0032 阶段二)。"""
    if channel == tg_adapter.CHANNEL:
        if not config.tg_chat_id:
            return ChannelResult(
                channel=tg_adapter.CHANNEL, ok=False,
                error="未绑定 Telegram · 请先在 bot 里 /start 绑定",
            )
        if not settings.tg_bot_token:
            return ChannelResult(
                channel=tg_adapter.CHANNEL, ok=False, error="统一 bot 未配置",
            )
        try:
            await tg_adapter.send_test(config.tg_chat_id, client=client)
            return ChannelResult(channel=tg_adapter.CHANNEL, ok=True)
        except Exception as e:  # noqa: BLE001
            return ChannelResult(channel=tg_adapter.CHANNEL, ok=False, error=str(e))

    if channel == feishu_adapter.CHANNEL:
        feishu_open_id = config.feishu_open_id
        if not feishu_open_id:
            return ChannelResult(
                channel=feishu_adapter.CHANNEL, ok=False,
                error="未绑定飞书 · 请先在飞书完成绑定",
            )
        if not (settings.feishu_app_id and settings.feishu_app_secret):
            return ChannelResult(
                channel=feishu_adapter.CHANNEL, ok=False, error="飞书应用未配置",
            )
        try:
            await feishu_adapter.send_test(feishu_open_id, client=client)
            return ChannelResult(channel=feishu_adapter.CHANNEL, ok=True)
        except Exception as e:  # noqa: BLE001
            return ChannelResult(channel=feishu_adapter.CHANNEL, ok=False, error=str(e))

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
