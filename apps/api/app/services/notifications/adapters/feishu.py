"""飞书通知适配器 · ADR 0032 阶段二(纯文本)。

与 adapters/telegram.py 同契约(CHANNEL + send_event + send_test),core(dispatcher)
不关心 token / 渲染细节。本期【纯文本】:复用现有文字模板(render_telegram 产出的 TG
Markdown),剥掉 *粗体* / _斜体_ / `代码` 标记 → 飞书 text 消息(text 类型不渲染 Markdown)。

交互式卡片(card · lark_md)留阶段四,与下单二次确认一起做。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.notifications import feishu_client
from app.services.notifications.templates import (
    render_telegram,
    render_telegram_test,
)

if TYPE_CHECKING:
    import httpx

    from app.services.notifications.events import NotificationEvent

CHANNEL = "feishu"


def _to_plain_text(md: str) -> str:
    """剥 TG Markdown 强调标记(* _ `)→ 飞书 text 纯文本。

    通知模板里 * _ ` 仅用于强调(标题加粗 / 免责斜体),正文(代码 / 数字 / 市场名)
    不含这些字符,直接 replace 安全。飞书 text 消息按字面显示,故必须去掉标记免得露出。
    """
    return md.replace("*", "").replace("`", "").replace("_", "")


async def send_event(
    open_id: str,
    event: NotificationEvent,
    *,
    client: httpx.AsyncClient | None = None,
) -> None:
    """渲染事件 → 飞书纯文本 → 发到 open_id。token 来自全局 settings.feishu_app_*。"""
    text = _to_plain_text(render_telegram(event))
    await feishu_client.send_text(open_id, text, client=client)


async def send_test(
    open_id: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> None:
    """「发送测试消息」· 飞书纯文本。"""
    text = _to_plain_text(render_telegram_test())
    await feishu_client.send_text(open_id, text, client=client)
