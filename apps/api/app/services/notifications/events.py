"""通知事件 dataclass tree · 0009 § 3。

NotificationEvent 是抽象基,具体事件 TradeFilledEvent / PriceAnomalyEvent。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Literal


class NotificationKind(StrEnum):
    TRADE_FILLED = "trade_filled"
    PRICE_ANOMALY = "price_anomaly"


@dataclass(frozen=True)
class TradeFilledEvent:
    """成交通知事件(0009 § 3)。"""

    kind: Literal[NotificationKind.TRADE_FILLED] = NotificationKind.TRADE_FILLED
    symbol: str = ""
    market: str = ""
    side: Literal["buy", "sell"] = "buy"
    quantity: Decimal = Decimal("0")
    price: Decimal = Decimal("0")
    notional: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    realized_pnl: Decimal | None = None
    currency: str = ""


@dataclass(frozen=True)
class PriceAnomalyEvent:
    """价格异动通知 · ±5% 触发(0009 § 4)。"""

    kind: Literal[NotificationKind.PRICE_ANOMALY] = NotificationKind.PRICE_ANOMALY
    symbol: str = ""
    market: str = ""
    current_price: Decimal = Decimal("0")
    reference_price: Decimal = Decimal("0")
    change_pct: Decimal = Decimal("0")  # 正:涨 / 负:跌
    currency: str = ""


NotificationEvent = TradeFilledEvent | PriceAnomalyEvent
