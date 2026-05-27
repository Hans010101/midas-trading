"""Bot 下单后台预设 schemas · 0026 G5。

PUT 不接受 perp_margin_mode(本期固定逐仓 · 防误设全仓);响应里返回固定 'isolated'。
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

_MAX_LEVERAGE = 20


class BotPresetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    perp_leverage: int
    perp_notional_usdt: Decimal
    perp_margin_mode: str
    spot_notional_cny: Decimal
    spot_notional_usd: Decimal


class BotPresetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    perp_leverage: int = Field(ge=1, le=_MAX_LEVERAGE, description="永续杠杆 1–20x")
    perp_notional_usdt: Decimal = Field(gt=0, description="永续每单名义额(USDT)")
    spot_notional_cny: Decimal = Field(gt=0, description="A股每单名义额(CNY)")
    spot_notional_usd: Decimal = Field(gt=0, description="美股每单名义额(USD)")
