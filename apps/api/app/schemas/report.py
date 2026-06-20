"""市场周报 admin 复核 schema(P2)。"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ReportListItem(BaseModel):
    """列表行(不含正文 · 列表页轻量)。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: str
    period_start: date | None
    period_end: date | None
    created_at: datetime


class ReportListOut(BaseModel):
    items: list[ReportListItem]
    total: int


class ReportDetail(BaseModel):
    """单篇详情(含正文 · 复核/编辑页)。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    status: str
    period_start: date | None
    period_end: date | None
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    sent_at: datetime | None


class ReportUpdateIn(BaseModel):
    """编辑入参(title / content 至少给一个)。"""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = Field(default=None, min_length=1)


class ReportSendOut(BaseModel):
    """发送广播结果(P3)· admin 点发布后回显投递统计。"""

    report_id: int
    status: str  # 发送后 = sent
    recipients: int  # 订阅用户数
    email_sent: int
    email_failed: int
    notify_sent: int  # TG/飞书 实际投递用户数
    notify_failed: int
