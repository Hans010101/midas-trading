"""按天来源桶聚合 · SEO 批6 度量闭环(流量来源归因)。

★ 只存按天 × 来源桶的聚合计数(date+source 复合唯一),绝不存每条访问明细/IP/UA。
   来源桶 = classify_source(referrer host, utm_source) 的有界枚举
   (direct / google / bing / chatgpt / perplexity / kimi / doubao / referral / utm:* …)。
   实时计数在 Redis(visit:src:{date} HASH),Celery beat 每 10 分钟 flush → 此表(upsert)。
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import BigInteger, Date, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DailySourceStat(Base):
    __tablename__ = "daily_source_stat"
    __table_args__ = (UniqueConstraint("date", "source", name="uq_source_date_source"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[date_type] = mapped_column(Date, index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    pv: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )
