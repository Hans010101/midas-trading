"""按天访问聚合 · 网站访问看板(PV/UV)。

★ 只存按天聚合一行(date 唯一),绝不存每条访问明细(避免表爆炸);
   也不存 IP / UA / 路径明细(隐私:仅匿名计数)。
   实时计数在 Redis(visit:pv:{date} INCR · visit:uv:{date} SET → SCARD),
   Celery beat 每 10 分钟 flush Redis → 此表(upsert · 见 services/visit_stats.py)。

访问数据自上线起累积、历史不可回溯(部署前无任何访问日志)。
注册增长趋势另从 user.created_at 回溯(不依赖此表)。
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import BigInteger, Date, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DailyVisitStat(Base):
    __tablename__ = "daily_visit_stat"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 自然日(CN 本地口径 · 与 beat timezone Asia/Shanghai 一致)· 唯一一行/天
    date: Mapped[date_type] = mapped_column(Date, unique=True, index=True, nullable=False)
    # PV = 页面访问次数;UV = 当日去重访客数(匿名 visitor_id)
    pv: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    uv: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
