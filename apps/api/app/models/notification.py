"""NotificationConfig SQLAlchemy model · 0009 推送 → 0025 v2 统一 bot。

每用户一行 · lazy create · user_id 既 PK 又 FK(跟 VirtualAccount 同模式)。

0025 G2a:移除飞书 + per-user TG token(统一 bot,token 走全局 env);
tg_chat_id 由 /start 绑定写入,加 partial 唯一索引(一 chat 一账号)。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NotificationConfig(Base):
    __tablename__ = "notification_config"
    # 一 chat 一账号:tg_chat_id 非空时唯一(防一个 Telegram 绑多个 Midas 账号)。
    # partial(WHERE tg_chat_id IS NOT NULL)· 允许多用户都未绑定(NULL)。
    __table_args__ = (
        Index(
            "uq_notification_config_tg_chat_id",
            "tg_chat_id",
            unique=True,
            postgresql_where=text("tg_chat_id IS NOT NULL"),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Telegram 统一 bot 绑定的 chat_id(由 /start 绑定写入 · 0025 G1)。
    # 注:统一 bot 的 token 是全局 env(settings.tg_bot_token),不再 per-user。
    tg_chat_id: Mapped[str | None] = mapped_column(String(64))

    # 总开关 · 默认开
    trade_alert_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
    )
    price_alert_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
    )

    # 0028 N1 · 安静时段(quiet hours)· 在该窗口内吞掉普通告警,
    # 钱相关事件(quiet_exempt=True,如 TradeFilledEvent · 0028 DP10)豁免照常发。
    # 默认 23:00–07:00 / Asia/Shanghai / 开启(DP4 + DP5)。
    quiet_hours_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
    )
    # 起止小时 0–23(SMALLINT)· 跨夜(start > end)等同 23-7 这种用法
    quiet_hours_start: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("23"),
    )
    quiet_hours_end: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("7"),
    )
    quiet_hours_tz: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'Asia/Shanghai'"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )
