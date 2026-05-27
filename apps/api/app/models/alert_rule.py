"""AlertRule SQLAlchemy model · 0025 G2b 告警规则引擎(纯新增表)。

每条规则 = 用户对「某标的(或市场级)某指标」设的阈值告警。扫描 worker 周期读
ClickHouse 已采数据、命中则经 G2a 核心层 dispatch 推送。

纯新增表 · 不碰任何现有表。指标元信息(标签 / 适用市场 / 是否需 symbol)由
services/alerts/registry.py 定义,本表只存「用户选了哪个指标 + 什么阈值」。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AlertRule(Base):
    __tablename__ = "alert_rule"
    # 扫描 worker 按 enabled 过滤遍历 → 建 (user_id) + (enabled) 索引辅助。
    __table_args__ = (
        Index("ix_alert_rule_user_id", "user_id"),
        Index("ix_alert_rule_enabled", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
    )

    # 市场 cn/us/crypto · 指标决定可选市场(registry 校验)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    # 标的代码 · 市场级指标如恐贪 / BTC 占比为 NULL · registry 声明 scope
    symbol: Mapped[str | None] = mapped_column(String(64))

    # 指标 key(registry.py 的注册键 · 如 price_change_pct / rsi_14 / funding_rate)
    indicator: Mapped[str] = mapped_column(String(48), nullable=False)
    # 比较算子 · gt gte lt lte
    operator: Mapped[str] = mapped_column(String(8), nullable=False)
    threshold: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    # K 线类指标的周期(1d/1h/...)· 快照类指标忽略 · 默认 1d
    timeframe: Mapped[str | None] = mapped_column(String(8))

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
    )
    # 命中后冷却秒数(Redis 去重 TTL)· DP6 护栏
    cooldown_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("300"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )
