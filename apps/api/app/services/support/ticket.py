"""支付工单服务 · 建工单(存 DB)+ Resend 邮件通知客服(图走附件不落盘)。

🔴 红线:独立 support 模块 —— 不 import virtual_trading/engine、不 import 收款逻辑(payment 服务)。
凭证 RESEND_API_KEY 只从 env 读(复用 email.py 范式)· 绝不入日志/返回/异常。
★ 图片只作 Resend 附件 base64 发出,发完即弃,不落 DB/磁盘/OSS(本服务不接收磁盘路径)。
邮件发送失败【不阻塞工单创建】(工单已存 DB 是第一位),只记 warning 日志。
"""

from __future__ import annotations

import base64
import html as html_lib
import logging
import os
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.support_ticket import SupportTicket

logger = logging.getLogger(__name__)

_RESEND_ENDPOINT = "https://api.resend.com/emails"


async def create_ticket(
    db: AsyncSession,
    user_id: UUID,
    *,
    contact_email: str,
    category: str,
    description: str,
    related_order_id: str | None,
    image_count: int,
) -> SupportTicket:
    """建工单行(status=open)→ commit → 返回。图片不在此处理(只记数量,不落库)。"""
    ticket = SupportTicket(
        user_id=user_id,
        contact_email=contact_email,
        category=category,
        description=description,
        related_order_id=related_order_id,
        image_count=image_count,
        status="open",
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return ticket


async def send_ticket_email(
    *, ticket: SupportTicket, user_email: str, images: list[tuple[str, bytes]],
) -> bool:
    """Resend 通知客服 · 图片 base64 作附件 · 返回是否发送成功(失败不抛,记 warning)。

    from=support@midastrade.asia(已验证域名)· to=客服箱 · 附件 [{filename, content(base64)}]。
    无 RESEND_API_KEY(dev)→ 记 warning + 返回 False(工单已存,不阻塞)。
    """
    api_key = os.getenv("RESEND_API_KEY") or None
    if not api_key:
        logger.warning("[support] RESEND_API_KEY 未配置 · 工单 #%s 邮件跳过(已存 DB)", ticket.id)
        return False

    uid8 = str(ticket.user_id)[:8]
    subject = f"[工单] {ticket.category} - 用户 {uid8} - #{ticket.id}"
    # ★ 图片 base64 → Resend 附件(content 为 base64 字符串)· 不落盘
    attachments = [
        {"filename": fn, "content": base64.b64encode(data).decode("ascii")}
        for fn, data in images
    ]
    body: dict[str, Any] = {
        "from": settings.support_email_from,
        "to": [settings.support_email_to],
        "subject": subject,
        "html": _ticket_email_html(ticket=ticket, user_email=user_email),
    }
    if attachments:
        body["attachments"] = attachments

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                _RESEND_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
    except httpx.HTTPError:
        # 失败不抛 · 不带凭证/URL/响应体进日志 · 工单已存 DB,邮件可后补
        logger.warning("[support] 工单 #%s Resend 通知失败(已存 DB · 邮件延迟)", ticket.id)
        return False

    logger.info("[support] 工单 #%s 已邮件通知客服 · 附件 %d 张", ticket.id, len(attachments))
    return True


def _ticket_email_html(*, ticket: SupportTicket, user_email: str) -> str:
    """工单通知邮件正文(内部客服用)· 用户输入全部 html 转义(防 HTML 注入)。"""
    desc = html_lib.escape(ticket.description)
    contact = html_lib.escape(ticket.contact_email)
    category = html_lib.escape(ticket.category)
    order_line = (
        f'<p><b>关联订单</b>:{html_lib.escape(ticket.related_order_id)}</p>'
        if ticket.related_order_id
        else ""
    )
    return f"""\
<div style="font-family:'Noto Sans SC',sans-serif;color:#1A1A1A;max-width:560px;">
  <h2 style="color:#C8102E;margin:0 0 16px;">支付工单 #{ticket.id}</h2>
  <p style="margin:4px 0;"><b>类型</b>:{category}</p>
  <p style="margin:4px 0;"><b>用户 ID</b>:{ticket.user_id}</p>
  <p style="margin:4px 0;"><b>账号邮箱</b>:{html_lib.escape(user_email)}</p>
  <p style="margin:4px 0;"><b>联系邮箱</b>:{contact}</p>
  {order_line}
  <p style="margin:16px 0 4px;"><b>问题描述</b>:</p>
  <p style="white-space:pre-wrap;border-left:3px solid #B8860B;padding-left:12px;">{desc}</p>
  <p style="color:#94949C;font-size:12px;margin-top:16px;">
    附件图片 {ticket.image_count} 张 · 提交时间 {ticket.created_at}
  </p>
</div>"""
