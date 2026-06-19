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

from app.schemas.market import Market, Period

# 经典策略 key(拍板① + 第一刀 macd/kdj 四市场通用 + 第二刀 extreme 仅 crypto perp)
StrategyKind = Literal[
    "ma_cross", "rsi_reversal", "boll_reversion", "macd_cross", "kdj_cross",
    # 极端信号(★仅 crypto perp · 合约 funding/OI/多空比情绪 · 现货不出)
    "extreme",
]

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
    # ⑤ 关键价位(形态A 批2 · 信号点已算值 · 策略相关键值对)·
    #   ma_cross {"MA5":x,"MA20":y} · rsi {"RSI":x,"超卖线":30} · boll {"上轨":x,"中轨":y,"下轨":z}
    levels: dict[str, float] = Field(default_factory=dict)
    # ⑥ 成色(形态A 批2 · 只 rsi/boll 算 · ma_cross 不做 → None)· strength 数值越大越强 + note 可读
    strength: float | None = Field(default=None)
    strength_note: str | None = Field(default=None, max_length=40)


# ===== 单元2:推荐 + 只读 API 契约 =====


class StrategyRecommendation(BaseModel):
    """纯规则推荐结果 · 推荐适配层(strategy_recommend.py)输出 · 零 LLM。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: StrategyKind
    reason: str = Field(min_length=1, max_length=120)   # 可读推荐依据(趋势/震荡+RSI/贴轨)


class StrategySignalsResponse(BaseModel):
    """GET /api/v1/analysis/strategy-signals 响应 · 某标的某策略的历史信号点序列。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1)
    market: Market
    period: Period
    instrument: str                                     # spot / perp(拍板⑦ · crypto 跟随详情页)
    strategy: StrategyKind
    bar_count: int = Field(ge=0)                        # 扫描用的 K 线根数
    signals: list[StrategySignal]                       # ts 升序(拍板⑥ · 全部可见历史信号点)
    # 最新一根 K 是否为信号点 → 前端「当前是否触发」提示
    current_triggered: bool
    # 最近一个信号(无则 None)· 给「当前/最近信号」提示
    last_signal: StrategySignal | None = None
    # ★ Pro 门控:True = 非 Pro(未登录/免费)· 此时 signals 为空(无真实信号 · 防 F12)·
    #   前端据此 + 登录态出遮罩(未登录→注册墙 / 免费→付费墙)。
    locked: bool = False


class StrategyRecommendResponse(BaseModel):
    """GET /api/v1/analysis/strategy-recommend 响应 · 推荐该标的现在适合哪个策略。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1)
    market: Market
    period: Period
    instrument: str
    recommended_strategy: StrategyKind
    reason: str = Field(min_length=1, max_length=120)
