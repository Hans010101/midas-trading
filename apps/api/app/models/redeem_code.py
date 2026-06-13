"""RedeemCode SQLAlchemy model · 兑换码模块刀1。

管理员批量生成 → 任意登录用户兑换 → 开 pro 会员权益(source='redeem')。
- code: Crockford base32 12 位(secrets · 去易混字符 · 不可猜 · 照 invite_code 范式加长)
- period/days: days 冗余固化(生成时按 PERIOD_DAYS 存),防未来改档影响存量码语义
- 一次性:redeemed_by/redeemed_at 非空即已用;rowcount 幂等兑换(用掉作废)
- 有效期:expires_at = created_at + 1 年(过期不可兑)
- 可追溯:created_by(生成的管理员)+ redeemed_by(兑换的用户)
- status 不存列:由 redeemed_at + expires_at 派生(避免冗余 status 与 redeemed_at 漂移)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RedeemCode(Base):
    __tablename__ = "redeem_code"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(12), nullable=False, unique=True, index=True)
    period: Mapped[str] = mapped_column(String(16), nullable=False)  # month|quarter|year
    days: Mapped[int] = mapped_column(Integer, nullable=False)  # 30/90/365 冗余固化
    note: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # created_by/redeemed_by ondelete SET NULL → 账号删了码仍可追溯/兑换 · 故 nullable
    created_by: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_by: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="SET NULL"), nullable=True,
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
