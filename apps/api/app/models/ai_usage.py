"""AI LLM 用量日志 · 0012 ADR § 监控。

每次真实 LLM 调用写一行(mock 模式不写)· Celery beat daily 累计跑统计。
80% 月预算时邮件告警(走 0009 Resend 通道)。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AIUsageLog(Base):
    """LLM 单次调用日志 · append-only · 不可变。"""

    __tablename__ = "ai_usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 调用上下文
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    period: Mapped[str] = mapped_column(String(8), nullable=False)

    # LiteLLM 用的 model 名(eg. "deepseek/deepseek-chat")
    model: Mapped[str] = mapped_column(String(64), nullable=False)

    # token 用量 · litellm response.usage
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)

    # 估算成本(CNY · 折算汇率 7.2)· 累计可对账 ¥200 月预算
    cost_cny: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, server_default=text("0"),
    )

    # 节点身份(workflow 里哪个节点调的)· "technical_agent" / "decision_card" 等
    node: Mapped[str] = mapped_column(String(32), nullable=False)

    # success / parse_error / timeout / etc.
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
