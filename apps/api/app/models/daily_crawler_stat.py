"""按天 AI/搜索爬虫访问聚合 · SEO 批6 度量闭环(GEO 领先指标)。

★ 记 AI 爬虫(GPTBot/ClaudeBot/PerplexityBot/Bytespider…)与搜索爬虫(Googlebot/Bingbot)
   按 bot 名分桶的访问次数 —— 这是「内容是否被 AI 引擎抓取」的领先指标(先于流量到来)。
   bot 名由前端 middleware 依 UA 瞬时分类,★UA 字符串本身不发后端、不落库(隐私)。
   实时计数 Redis(visit:crawler:{date} HASH)→ beat flush → 此表。date+bot 复合唯一。
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import BigInteger, Date, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DailyCrawlerStat(Base):
    __tablename__ = "daily_crawler_stat"
    __table_args__ = (UniqueConstraint("date", "bot", name="uq_crawler_date_bot"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[date_type] = mapped_column(Date, index=True, nullable=False)
    bot: Mapped[str] = mapped_column(String(120), nullable=False)
    hits: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )
