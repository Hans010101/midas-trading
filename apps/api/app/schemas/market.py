"""市场数据 Pydantic 契约。

三市场(A股 / 美股 / 加密)的 K 线、标的元信息抹平差异后的统一表示。
所有数据源适配器都必须返回这里定义的形状,Pydantic 严格校验上下界。

时间约定:所有 ts / updated_at 字段必须是 **tz-aware datetime(UTC)**。
适配器内部把本地时间转 UTC,前端展示时再按用户时区还原。
"""

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Market = Literal["cn", "us", "crypto", "hk"]
Period = Literal["1m", "5m", "15m", "30m", "1h", "1d", "1w"]


class Kline(BaseModel):
    """单根 K 线。OHLCV + 可选成交额(amount)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ts: AwareDatetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    amount: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_ohlc_consistency(self) -> "Kline":
        # OHLC 的几何关系必须成立,否则要么是上游数据腐烂,要么是适配器映射错位
        if not (self.low <= self.open <= self.high):
            msg = f"open {self.open} 不在 [low {self.low}, high {self.high}] 区间"
            raise ValueError(msg)
        if not (self.low <= self.close <= self.high):
            msg = f"close {self.close} 不在 [low {self.low}, high {self.high}] 区间"
            raise ValueError(msg)
        return self


class KlineResponse(BaseModel):
    """统一行情接口 /api/v1/market/kline 的响应体。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1)
    market: Market
    period: Period
    items: list[Kline]


class SymbolMeta(BaseModel):
    """标的元信息。symbol_meta 表的领域模型。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1)
    market: Market
    name: str = Field(min_length=1)
    name_en: str = ""
    listed_date: date | None = None
    is_active: bool = True
    updated_at: AwareDatetime
