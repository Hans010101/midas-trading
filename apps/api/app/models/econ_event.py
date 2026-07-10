"""宏观事件日程(事件日程提醒层 P0 · 前瞻日历)。

★只存「日程」(何时发布什么),不存实际值、不做实时快讯(调研 A 线边界)。
★PG 而非 CH(调研 §5.2·自主决策):事件是可变实体(改期要 UPDATE·按 event_key
  幂等 upsert),年增量 ~150 行——PG 场景;CH append 型反而别扭。
★保鲜口径:事件 ts 在未来,绝不用 max(scheduled_at) 判 stale(永远假新鲜)——
  用采集任务 last-run 成功时间(Redis econ:cal:last_success:*)进 ingest 监控。
🔴 红线:事件只作决策卡「风险提示」背景,零交易逻辑(本模型无任何下单/引擎关联)。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EconEvent(Base):
    """一条宏观事件日程 · event_key 幂等(如 fomc-2026-07-29 / cn_credit-2026-08)。"""

    __tablename__ = "econ_event"

    event_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 事件类型(白名单见 services/econ_calendar/rules.py 注册的 12 类)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    # 影响市场列表(JSONB · 如 ["us","crypto"] / ["cn","hk"])· 查询用 @> 包含
    markets: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    importance: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 3/2/1
    # ★tz-aware(项目铁律)· Fed 无时区标注按 America/New_York 换算,统计局 Asia/Shanghai
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True,
    )
    # False = 窗口/惯例占位(社融 9-15 日窗口 · 非农第一个周五惯例)· 展示时标「待定/以官方为准」
    time_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # fed_json/bea_json/rule/seed
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(tz=UTC), onupdate=lambda: datetime.now(tz=UTC),
        server_default=func.now(),
    )
