"""支付工单 / 退款申请端点(support 模块)。

- POST /support/ticket   · 登录用户提工单(multipart · 图走 Resend 附件不落盘)
- GET  /support/tickets  · 查本人工单列表(提交历史 · 限本人)

🔴 红线:独立 support 模块 —— 不 import virtual_trading/engine、不 import 收款逻辑(payment 服务)。
身份从 CurrentUserDep 取(不接受请求体伪造 user_id)· 凭证在 service 内 env 读不入日志。
★ 图片只读字节 → 交 service base64 作邮件附件,绝不落盘/落库/传 OSS。
"""

from __future__ import annotations

import logging
import re
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserDep
from app.core.config import settings
from app.core.database import get_db
from app.models.support_ticket import SupportTicket
from app.schemas.support import TicketCreateOut, TicketListItem
from app.services.support.ticket import create_ticket, send_ticket_email

logger = logging.getLogger(__name__)

router = APIRouter(tags=["support"])

DbDep = Annotated[AsyncSession, Depends(get_db)]

_ALLOWED_CATEGORIES = {"payment", "refund", "other"}
_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png"}
_MAX_DESC = 2000
_DESC_SUMMARY = 200
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("/support/ticket", response_model=TicketCreateOut)
async def submit_ticket(
    current_user: CurrentUserDep,
    db: DbDep,
    category: Annotated[str, Form()],
    description: Annotated[str, Form()],
    contact_email: Annotated[str | None, Form()] = None,
    related_order_id: Annotated[str | None, Form()] = None,
    images: Annotated[list[UploadFile] | None, File()] = None,
) -> TicketCreateOut:
    """提工单 → 存 DB → Resend 通知客服(图附件)。校验失败 422;邮件失败不阻塞(工单已存)。"""
    if category not in _ALLOWED_CATEGORIES:
        raise HTTPException(status_code=422, detail="未知工单类型")

    desc = (description or "").strip()
    if not desc:
        raise HTTPException(status_code=422, detail="问题描述不能为空")
    if len(desc) > _MAX_DESC:
        raise HTTPException(status_code=422, detail=f"问题描述过长(上限 {_MAX_DESC} 字)")

    # 联系邮箱 未填默认账号邮箱,提供则校验格式
    email = (contact_email or "").strip() or current_user.email
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="联系邮箱格式不正确")

    # 关联订单:只记字符串(只读关联展示)· 不查/不碰收款表
    order_id = (related_order_id or "").strip() or None

    # 图片:数量/类型/大小校验 + 读字节(★ 不落盘,仅内存交给邮件附件)
    files = [f for f in (images or []) if f.filename]
    if len(files) > settings.support_max_images:
        raise HTTPException(
            status_code=422, detail=f"最多上传 {settings.support_max_images} 张图片",
        )
    max_bytes = settings.support_max_image_mb * 1024 * 1024
    decoded: list[tuple[str, bytes]] = []
    for f in files:
        if f.content_type not in _ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=422, detail="图片仅支持 JPEG / PNG")
        data = await f.read()
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=422,
                detail=f"单张图片不得超过 {settings.support_max_image_mb} MB",
            )
        decoded.append((f.filename or "image", data))

    ticket = await create_ticket(
        db,
        current_user.id,
        contact_email=email,
        category=category,
        description=desc,
        related_order_id=order_id,
        image_count=len(decoded),
    )

    # ★ 邮件失败绝不让已建工单 500(工单已存 DB 是第一位)· send 内部已 swallow,这里再兜一层
    try:
        email_sent = await send_ticket_email(
            ticket=ticket, user_email=current_user.email, images=decoded,
        )
    except Exception:  # noqa: BLE001 — 邮件任何异常都不能让已建工单失败
        logger.warning("[support] 工单 #%s 邮件发送异常(已存 DB)", ticket.id)
        email_sent = False

    message = (
        "工单已提交,我们会通过邮件与你联系" if email_sent else "工单已记录,邮件通知可能延迟"
    )
    return TicketCreateOut(
        ticket_id=ticket.id, status=ticket.status, message=message, email_sent=email_sent,
    )


@router.get("/support/tickets", response_model=list[TicketListItem])
async def my_tickets(current_user: CurrentUserDep, db: DbDep) -> list[TicketListItem]:
    """查本人工单列表(提交历史)· 限本人 user_id · 按时间倒序 · 最多 50 条。"""
    rows = await db.scalars(
        select(SupportTicket)
        .where(SupportTicket.user_id == current_user.id)
        .order_by(SupportTicket.created_at.desc())
        .limit(50),
    )
    return [
        TicketListItem(
            id=t.id,
            category=t.category,
            status=t.status,
            description=t.description[:_DESC_SUMMARY],
            related_order_id=t.related_order_id,
            created_at=t.created_at,
        )
        for t in rows
    ]
