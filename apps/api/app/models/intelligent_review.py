"""智能交易复盘历史(智能交易第二期 PR-8)· DeepSeek 复盘生成结果落库。

★只读交易数据生成的【分析报告】· 🔴绝不碰交易执行(旁观分析师)· 与引擎完全解耦。
存储目的:① 幂等(period + period_start 唯一 · 同周期重跑覆盖)② 月报读本月周报/上期对比(★存 1 月)。
period = day / week / month · period_start = 周期起点(复用 review.period_start)。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IntelligentReview(Base):
    """智能交易复盘报告(日/周/月)· DeepSeek 生成全文 + 结构化数据备查。"""

    __tablename__ = "intelligent_review"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(8), nullable=False)  # day / week / month
    period_start: Mapped[date] = mapped_column(Date, nullable=False)  # 周期起点(幂等键)
    trade_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    content: Mapped[str] = mapped_column(Text, nullable=False)  # ★DeepSeek 复盘全文
    review_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # 结构化数据备查
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        # ★幂等:一周期一条(同 period + period_start 重跑覆盖)
        UniqueConstraint("period", "period_start", name="uq_intelligent_review_period_start"),
    )
