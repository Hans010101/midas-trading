"""BotOrderPreset SQLAlchemy model · 0026 G5 · bot 下单后台预设。

per-user 一行(user_id 既 PK 又 FK · 跟 NotificationConfig 同模式)。
行不存在 = 用安全默认常量(等价 G4 行为)· 读不 lazy-create。

字段默认值与 G4 `services/bot/order.py` 的 DEFAULT_* 常量一致(零回归)。
本期仅逐仓:perp_margin_mode 固定 'isolated';字段预留,将来 M2-C 补全仓后加 'cross'。

🔴 红线:这些只是 bot 下单时套用的【默认参数】· 下单本身全程虚拟引擎,绝不接真实交易。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BotOrderPreset(Base):
    __tablename__ = "bot_order_preset"

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # 永续:杠杆(校验 1–20 在路由层)· 每单名义额(USDT)· 保证金模式(本期固定逐仓)
    perp_leverage: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("3"),
    )
    perp_notional_usdt: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, server_default=text("100"),
    )
    perp_margin_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'isolated'"),
    )
    # 现货:每单名义额(原币种)· A股 CNY / 美股 USD
    spot_notional_cny: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, server_default=text("10000"),
    )
    spot_notional_usd: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, server_default=text("1000"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )
