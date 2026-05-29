"""通知事件 dataclass tree · 0009 § 3 / 0028 N1 安静时段豁免标记。

NotificationEvent 是抽象基,具体事件 TradeFilledEvent / PriceAnomalyEvent / AlertTriggeredEvent。
每个事件类带 `quiet_exempt: ClassVar[bool]`(0028 DP10):钱相关 = True(强平 / 成交 /
资金费等不受安静时段限制),普通市场告警 = False。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar, Literal


class NotificationKind(StrEnum):
    TRADE_FILLED = "trade_filled"
    PRICE_ANOMALY = "price_anomaly"
    ALERT_TRIGGERED = "alert_triggered"
    # #296:永续合约成交 / 强平(独立 kind · 便于日志区分;均 quiet_exempt=True)
    PERP_FILLED = "perp_filled"
    LIQUIDATION = "liquidation"


@dataclass(frozen=True)
class TradeFilledEvent:
    """成交通知事件(0009 § 3)· 钱相关 · 不受安静时段限制(0028 DP10)。"""

    quiet_exempt: ClassVar[bool] = True  # 0028 DP10:钱相关不受 quiet 限制

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
    """价格异动通知 · ±5% 触发(0009 § 4)· 普通市场告警 · 受安静时段拦截。"""

    quiet_exempt: ClassVar[bool] = False

    kind: Literal[NotificationKind.PRICE_ANOMALY] = NotificationKind.PRICE_ANOMALY
    symbol: str = ""
    market: str = ""
    current_price: Decimal = Decimal("0")
    reference_price: Decimal = Decimal("0")
    change_pct: Decimal = Decimal("0")  # 正:涨 / 负:跌
    currency: str = ""


@dataclass(frozen=True)
class AlertTriggeredEvent:
    """告警规则命中通知 · 0025 G2b · 普通市场告警 · 受安静时段拦截。"""

    quiet_exempt: ClassVar[bool] = False

    kind: Literal[NotificationKind.ALERT_TRIGGERED] = NotificationKind.ALERT_TRIGGERED
    market: str = ""
    symbol: str | None = None  # 市场级指标(如恐贪)为 None
    indicator_label: str = ""
    operator: str = ""  # gt / gte / lt / lte
    threshold: float = 0.0
    value: float = 0.0
    unit: str | None = None


@dataclass(frozen=True)
class PerpFilledEvent:
    """永续合约成交通知(#296)· 钱相关 · 不受安静时段限制(0028 DP10)。

    与现货 TradeFilledEvent 分开:perp 有 多空方向 / 杠杆 / 开平动作 / 保证金模式,
    现货事件塞不下。读 virtual_perp_order 由 worker task 构造(绑定的不是 0008 VirtualOrder)。
    """

    quiet_exempt: ClassVar[bool] = True

    kind: Literal[NotificationKind.PERP_FILLED] = NotificationKind.PERP_FILLED
    symbol: str = ""
    # 动作标识 · 取自 PerpAction 枚举的 value(开多 / 开空 / 平多 / 平空 之一)
    action: str = ""
    margin_mode: str = "isolated"  # isolated / cross
    leverage: int | None = None
    quantity: Decimal = Decimal("0")
    price: Decimal = Decimal("0")
    notional: Decimal = Decimal("0")
    fee: Decimal = Decimal("0")
    realized_pnl: Decimal | None = None  # 仅平仓填
    currency: str = "USDT"


@dataclass(frozen=True)
class LiquidationEvent:
    """强制平仓通知(#296)· 风控/钱相关 · 不受安静时段限制(0028 DP10)。

    覆盖两种:逐仓单仓(is_cross=False · symbol/side/leverage/liquidation_price 有值)
    与 全仓账户级(is_cross=True · 一次性全平 N 仓 · symbol 为 None · 用 position_count)。
    """

    quiet_exempt: ClassVar[bool] = True

    kind: Literal[NotificationKind.LIQUIDATION] = NotificationKind.LIQUIDATION
    is_cross: bool = False
    symbol: str | None = None
    side: Literal["long", "short"] | None = None
    leverage: int | None = None
    liquidation_price: Decimal | None = None
    realized_pnl: Decimal | None = None  # 逐仓:该仓本次已实现
    position_count: int = 1  # 逐仓=1 · 全仓=N
    remaining_cash: Decimal | None = None  # 全仓:账户剩余可用
    floored: bool = False  # 全仓:是否穿仓地板(净亏封顶)
    currency: str = "USDT"


NotificationEvent = (
    TradeFilledEvent
    | PriceAnomalyEvent
    | AlertTriggeredEvent
    | PerpFilledEvent
    | LiquidationEvent
)
