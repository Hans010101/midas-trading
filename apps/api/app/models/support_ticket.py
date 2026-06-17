"""会员支付工单 / 退款申请(独立 support 模块)。

🔴 红线:本表是【客服工单记录】—— 独立于支付收款,只读引用订单 external_id 做关联展示,
不碰 virtual_trading/engine、不碰收款/开权益逻辑。凭证(Resend key)不入表。
★ 图片绝不落库:image_count 仅记数量,图片只作 Resend 邮件附件发出后即弃(不存 DB/磁盘/OSS)。

保留策略(项目"新表带策略"红线 · 工单与日志不同 = 要留证):
- 工单是客服 / 退款凭证,【不设激进 TTL 自动删】· 默认长期保留。
- 拟保留 1 年后人工归档(本期不自动删,留 TODO);created_at 索引支撑将来按期归档查询。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SupportTicket(Base):
    """支付工单 · open → resolved/closed(人工处理 · 本期只存 + 邮件通知客服)。"""

    __tablename__ = "support_ticket"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
    )
    # 用户填的联系邮箱(可与账号邮箱不同 · 退款回联用)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    # 工单类型 payment / refund / other(前端下拉)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # 关联订单 payment_order.external_id(只读关联展示 · 可空 · 不外键,避免耦合收款表)
    related_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # ★ 附了几张图(0-3)· 仅记数量,图片不落库(只走 Resend 附件)
    image_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), server_default="open", nullable=False,  # open|resolved|closed
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    # 「用户查自己工单(按时间倒序)」+ 将来按 created_at 归档
    __table_args__ = (Index("ix_support_ticket_user_created", "user_id", "created_at"),)
