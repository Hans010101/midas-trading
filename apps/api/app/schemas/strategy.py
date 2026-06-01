"""AI 策略信号 Pydantic 契约 · 模拟交易第二层形态A 单元1(ADR 0037 §2)。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:策略信号是【展示型】只读数据 —— 不下单 / 不执行 / 不撮合 / 不打实时上游。
   信号 kind 统一抽象 buy/sell(拍板③ · 不分现货/合约),用户看完走第一层一键下单。
═══════════════════════════════════════════════════════════════════════════

3 个经典策略(拍板① · 纯价格 · 四市场通用 · 穿越式离散信号):
- ma_cross       · 均线金叉/死叉(MA5 上穿/下穿 MA20)
- rsi_reversal   · RSI 超卖反弹/超买回落(RSI14 上穿 30 / 下穿 70 · 反弹确认式)
- boll_reversion · 布林带均值回归(收盘价触下轨/上轨 · BOLL20,2σ)
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# 3 个经典策略 key(拍板①)
StrategyKind = Literal["ma_cross", "rsi_reversal", "boll_reversion"]

# 信号方向 · 统一抽象(拍板③ · 不分现货/合约 · 看完走第一层)
SignalKind = Literal["buy", "sell"]


class StrategySignal(BaseModel):
    """单个策略买卖信号点 · 与缠论买卖点同构(前端复用 midas-fractal overlay 标注)。

    穿越式离散信号:某根 K 线发生「金叉 / 上穿 30 / 触下轨」等穿越事件时产一个点。
    price 取该根收盘价(拍板② 布林也用收盘价穿越);ts 为该根 K 线时间。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ts: AwareDatetime                                   # 信号发生的 K 线时间
    price: float                                        # 该 K 线收盘价
    kind: SignalKind                                    # buy / sell(抽象方向)
    reason: str = Field(min_length=1, max_length=80)    # 可读依据(金叉/超卖反弹/触轨)
