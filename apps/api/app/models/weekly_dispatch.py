"""周报投递(weekly_dispatch)· 运营上传成品周报(PDF+md)→ 提取 → 定时/补传发送。

★与 AI 生成的 market_report 解耦:本表是【运营上传的成品周报】投递记录(内容侧最终方案)。
  market_report(占位 AI 生成)保留不动 · 本表职责单一:一周一条、幂等、定时周日 21:00 发。

状态机:uploaded(上传待发)→ sent(已发)· skipped(可选 · 记某周未上传被跳过)。
★唯一约束 (year, week):每周次只一条,防重复发送(upsert + 发送前再查 status 幂等)。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WeeklyDispatch(Base):
    """周报投递行 · 一周一条(year+week 唯一)· 上传成品 → 定时发送。"""

    __tablename__ = "weekly_dispatch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # ISO 周次定位(跨年用 year+week 唯一)· year = period_start 的 ISO 年
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # PDF 存 OSS(prefix weekly-dispatch/ · ★避开 report-materials/ 7天 lifecycle · 周报留存可回溯)
    pdf_oss_key: Mapped[str] = mapped_column(String(512), nullable=False)
    pdf_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # md 原文(存库供提取/复查)+ 提取出的结构化数据(导语/结论/强弱/下周关注 + 缺失标记)
    md_text: Mapped[str] = mapped_column(Text, nullable=False)
    extracted: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    # uploaded(待发)| sent(已发)| skipped(某周未上传被跳过的记录 · 可选)
    status: Mapped[str] = mapped_column(
        String(16), server_default="uploaded", nullable=False,
    )
    uploaded_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # ★一周一条 · 防重复发送(upsert ON CONFLICT 用)
        UniqueConstraint("year", "week", name="uq_weekly_dispatch_year_week"),
    )
