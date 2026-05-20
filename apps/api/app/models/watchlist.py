"""WatchlistItem SQLAlchemy model · 0007 自选股扁平结构。

字段:
- id: Integer autoincrement(自选股是用户私有数据,不需 UUID 全局唯一)
- user_id: UUID FK → user.id · ondelete CASCADE(注销账户连同清理)
- symbol / market: 标的 + 三市场之一(cn / us / crypto)
- sort_order: Integer · 拖拽 reorder 时整数重写(M2+ 可换 fractional indexing)
- added_at: tz-aware UTC server-side default

约束:
- UniqueConstraint(user_id, symbol, market) 同用户同标的不重复
- Index(user_id, sort_order) 列表查询主索引
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)  # cn / us / crypto
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "symbol", "market", name="uq_watchlist_user_symbol"),
        Index("ix_watchlist_user_sort", "user_id", "sort_order"),
    )
