"""Bot 下单后台预设 schemas · 0026 G5 / 0027 MC-4(放开全仓选项)。

MC-4 起 PUT 接受 perp_margin_mode ∈ {isolated, cross}(默认 isolated · 老 PUT 不传
即等同 G5 行为 · 零回归)。下单时 bot 读取此偏好走对应引擎(perp_dispatcher 分流)。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

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
    # MC-4 放开全仓 · 默认 isolated(老 PUT 不传 = 行为等同 G5 · 零回归)
    perp_margin_mode: Literal["isolated", "cross"] = Field(
        default="isolated", description="永续保证金模式 · isolated 逐仓 / cross 全仓",
    )
    spot_notional_cny: Decimal = Field(gt=0, description="A股每单名义额(CNY)")
    spot_notional_usd: Decimal = Field(gt=0, description="美股每单名义额(USD)")
