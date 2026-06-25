"""Telegram 通知适配器(0025 core/adapter)。

把核心事件渲染成 Telegram 文本,经【统一官方 bot】(全局 token)发到用户绑定的
chat_id。core(dispatcher)不关心 token / 渲染细节,只调本模块的 send_event。

将来加飞书 = 新增 adapters/feishu.py 实现同样的 send_event / send_test,核心层不动。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import settings
from app.services.notifications import telegram as telegram_client
from app.services.notifications.events import NotificationKind
from app.services.notifications.templates import (
    render_telegram,
    render_telegram_test,
)

if TYPE_CHECKING:
    import httpx

    from app.services.notifications.events import NotificationEvent

CHANNEL = "telegram"

# 做T 推送(体系1 全景 / 体系2 转换)发送时关底部网页预览大卡:消息含官网超链接,TG 会自动抓
# 首页生成一个多余的「点金 Midas 官网」预览卡。★只关预览卡 · 正文 [SYMBOL](详情页) 内联链接仍可点
# (一一对应进详情)。其他推送(成交/价格异动/告警/周报)不在此集合 → 预览行为一字不动。
_NO_PREVIEW_KINDS = frozenset({
    NotificationKind.DOTT_DIGEST,
    NotificationKind.DOTT_TRANSITION,
})


async def send_event(
    chat_id: str,
    event: NotificationEvent,
    *,
    client: httpx.AsyncClient | None = None,
) -> None:
    """渲染事件 → 经统一 bot 发到 chat_id。token 来自全局 settings.tg_bot_token。

    ★做T 推送(_NO_PREVIEW_KINDS)关底部网页预览大卡;其他事件预览行为不变。
    """
    text = render_telegram(event)
    await telegram_client.send(
        settings.tg_bot_token, chat_id, text,
        disable_preview=event.kind in _NO_PREVIEW_KINDS,
        client=client,
    )


async def send_test(
    chat_id: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> None:
    """「发送测试消息」· 经统一 bot 发到 chat_id。"""
    await telegram_client.send(
        settings.tg_bot_token, chat_id, render_telegram_test(), client=client,
    )
