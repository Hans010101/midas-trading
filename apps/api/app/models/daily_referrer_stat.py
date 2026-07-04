"""按天来源域名聚合 · SEO 批6 度量闭环(top 来源域名 · 归因细粒度补充)。

★ 只存来源【域名 hostname】(不存 path/query — 每篇文章 URL 不同会爆炸且归因价值低,
   host 天然有界)· 绝不存 IP/UA。date+referrer 复合唯一。
   实时计数 Redis(visit:ref:{date} HASH · host 基数 500 上限兜底)→ beat flush → 此表。
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import BigInteger, Date, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DailyReferrerStat(Base):
    __tablename__ = "daily_referrer_stat"
    __table_args__ = (UniqueConstraint("date", "referrer", name="uq_referrer_date_referrer"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[date_type] = mapped_column(Date, index=True, nullable=False)
    referrer: Mapped[str] = mapped_column(String(120), nullable=False)  # 来源域名 host
    pv: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )
