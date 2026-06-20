"""标准化市场周报(market_report)· 第一刀 P1/P2。

Celery 定时生成草稿 → admin 后台人工复核/编辑/批准 → (第二刀)统一发送。
全平台一份(标准化 · 非个性化)· 成本固定 · 人工把关。

状态机(参 support_ticket.status 范式):draft → approved → sent。
- draft:Celery / admin 手动触发生成的草稿(占位内容 · 待内容立项替换专业 prompt)。
- approved:admin 复核编辑后批准(记 approved_at / approved_by)。
- sent:已统一发送(★第二刀做发送 · 本刀只到 approved)。

🔴 红线:报告 AI 输出必带免责「仅供参考,不构成投资建议」(ADR 0012 · validate_advisory + 兜底)。
本表不碰交易 / 收款 / 引擎,纯内容草稿 + 状态。
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MarketReport(Base):
    """标准化市场周报 · draft → approved → sent。"""

    __tablename__ = "market_report"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 报告标题(如「市场周报 · 2026-06-16 ~ 2026-06-22」)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # 报告正文(★本刀占位内容 · 待内容立项替换专业 prompt 生成)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), server_default="draft", nullable=False,  # draft|approved|sent
    )
    # 报告覆盖周期(可选 · 生成时按自然周填;admin 可不依赖)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # 批准信息(approve 时写 · approved_by = 操作 admin · 删 admin 置空不连带删报告)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
    )
    # 发送时间(★第二刀发送时写 · 本刀恒 NULL)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # admin 列表「按状态筛 + 时间倒序」
    __table_args__ = (Index("ix_market_report_status_created", "status", "created_at"),)
