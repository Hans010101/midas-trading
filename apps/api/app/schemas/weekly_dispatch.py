"""周报投递 admin schema(上传/列表/详情/发送)。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WeeklyUploadOut(BaseModel):
    """上传响应 · 解析摘要 + 缺失校验 + 邮件预览(★上传只入库 status=uploaded,不自动发)。"""

    id: int
    year: int
    week: int
    status: str
    extracted: dict[str, Any]  # 提取的结构化数据(导语/结论/强弱/下周关注/missing)
    missing: list[str]  # 缺失的关键模块(供前端高亮)
    email_html: str  # 邮件 HTML 预览
    pdf_filename: str


class WeeklyDispatchListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    year: int
    week: int
    period_start: date
    period_end: date
    title: str
    status: str
    uploaded_at: datetime
    sent_at: datetime | None


class WeeklyDispatchList(BaseModel):
    items: list[WeeklyDispatchListItem]


class WeeklyDispatchDetail(BaseModel):
    """详情 · 含提取数据 + 邮件 HTML 预览(在端点渲染注入)。"""

    id: int
    year: int
    week: int
    period_start: date
    period_end: date
    title: str
    status: str
    pdf_filename: str
    uploaded_at: datetime
    sent_at: datetime | None
    extracted: dict[str, Any]
    email_html: str


class WeeklySendOut(BaseModel):
    dispatch_id: int
    year: int
    week: int
    recipients: int
    email_sent: int
    email_failed: int
    notify_sent: int
    notify_failed: int
    skipped: bool
