"""NotificationConfig SQLAlchemy model · 0009 推送通知设计。

每用户一行 · lazy create(用户首次保存配置时 INSERT)· user_id 既 PK 又 FK。
跟 0008 VirtualAccount lazy create 同模式 · 不存在 = 未配置任何通道。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NotificationConfig(Base):
    __tablename__ = "notification_config"

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # 飞书自定义机器人 · webhook URL(M0 明文 · M1 加密)
    feishu_webhook_url: Mapped[str | None] = mapped_column(String(512))

    # Telegram bot · token + chat_id
    tg_bot_token: Mapped[str | None] = mapped_column(String(128))
    tg_chat_id: Mapped[str | None] = mapped_column(String(64))

    # 总开关 · 默认开
    trade_alert_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
    )
    price_alert_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )
