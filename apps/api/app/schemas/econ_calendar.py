"""财经日历页响应 schema(PR-A · 纯展示零 LLM)。

🔴 红线:响应只含客观事实字段(时间/事件名/市场/星级/来源)——无任何解读字段;
前值/预期/公布值 P0 数据模型没有(不扩源 · 官方日程源只给日程不给值),不放空字段编造。
★保鲜:updated_at = 各源 last-run 成功时间的最新者(绝不是 max(事件ts),那个永远假新鲜)。
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.crypto import EconJobStatus


class EconEventOut(BaseModel):
    """一条日程事件(库字段直出 · 零加工零解读)。"""

    model_config = ConfigDict(from_attributes=True)

    event_key: str
    event_type: str
    title: str
    markets: list[str]
    importance: int = Field(description="重要度 3/2/1(星级)")
    scheduled_at: AwareDatetime
    time_confirmed: bool = Field(description="False=窗口/惯例占位(展示标「待定/以官方为准」)")
    source: str = Field(description="fed_json/bea_json/rule/seed")


class EconCalendarResponse(BaseModel):
    events: list[EconEventOut]
    sources: list[EconJobStatus] = Field(default_factory=list)
    # 数据更新时间 = 最近一次任一采集源成功(last-run 口径)· None=从未跑/读取失败
    updated_at: AwareDatetime | None = None
    any_stale: bool = False
