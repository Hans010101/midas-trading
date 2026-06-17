"""支付工单 Pydantic 契约(support 模块 · 独立于收款)。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TicketCreateOut(BaseModel):
    """提交工单结果 · email_sent=False 时前端提示"邮件可能延迟"(工单已存)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticket_id: int
    status: str          # open
    message: str
    email_sent: bool


class TicketListItem(BaseModel):
    """本人工单列表项(提交历史)· description 为摘要(截断)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    category: str
    status: str
    description: str
    related_order_id: str | None
    created_at: datetime
