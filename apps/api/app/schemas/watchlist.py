"""自选股(watchlist)Pydantic 契约 · 0007 扁平结构。

约束:
- symbol / market 跟着 schemas/market.py 的 Market Literal
- 不带 user_id 字段(后端从 JWT 取,不让客户端伪造)
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.market import Market


class WatchlistItemResponse(BaseModel):
    """自选股 item 响应体。"""

    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)

    id: int
    symbol: str = Field(min_length=1)
    market: Market
    sort_order: int
    added_at: AwareDatetime


class WatchlistItemCreate(BaseModel):
    """POST /watchlist 入参。"""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=64)
    market: Market


class WatchlistReorderIn(BaseModel):
    """PUT /watchlist/reorder 入参 · item_ids 按目标顺序排好。"""

    model_config = ConfigDict(extra="forbid")

    item_ids: list[int] = Field(min_length=1, max_length=500)
