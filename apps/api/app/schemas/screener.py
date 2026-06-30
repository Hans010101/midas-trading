"""选股筛选器 schema · 股票第一批 功能1 · 1a MVP(只读 · 分析非建议)。

🔴 红线:结果是"符合条件的标的"客观列表 + 免责,**非荐股**;纯只读不下单。
1a 现成条件:价格 / 涨跌幅(spot 快照预筛 · 方案A)+ RSI 区间 / 均线多头排列(K线现算 · 方案C)。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ScreenerFilters(BaseModel):
    """1a MVP 筛选条件(全可选 · 组合 AND)。"""

    model_config = ConfigDict(extra="forbid")

    price_min: float | None = Field(default=None, ge=0)
    price_max: float | None = Field(default=None, ge=0)
    change_pct_min: float | None = None
    change_pct_max: float | None = None
    rsi_min: float | None = Field(default=None, ge=0, le=100)
    rsi_max: float | None = Field(default=None, ge=0, le=100)
    ma_bull_aligned: bool | None = None  # 多头排列 MA5 > MA20 > MA60
    # 1b 穿越类(算法复用 strategy_signals / indicators · 都需 K线)
    macd_golden_cross: bool | None = None  # 最近一根 MACD 金叉(DIF 上穿 DEA)
    kdj_golden_cross: bool | None = None   # 最近一根 KDJ 金叉(K 上穿 D)
    boll_bandwidth_max: float | None = Field(default=None, ge=0)  # 布林带宽 ≤ 此值 %(收窄)
    volume_ratio_min: float | None = Field(default=None, ge=0)    # 量比 ≥ 此值

    def needs_kline(self) -> bool:
        """是否需 K线算技术指标(RSI / 均线 / 金叉 / 带宽 / 量比)→ 决定是否走批量算指标分支。"""
        return any(
            v is not None
            for v in (
                self.rsi_min, self.rsi_max, self.ma_bull_aligned,
                self.macd_golden_cross, self.kdj_golden_cross,
                self.boll_bandwidth_max, self.volume_ratio_min,
            )
        )

    def is_empty(self) -> bool:
        """无任何条件 → 端点拒(避免返回全市场)。"""
        return all(
            v is None
            for v in (
                self.price_min, self.price_max, self.change_pct_min,
                self.change_pct_max, self.rsi_min, self.rsi_max, self.ma_bull_aligned,
                self.macd_golden_cross, self.kdj_golden_cross,
                self.boll_bandwidth_max, self.volume_ratio_min,
            )
        )


class ScreenerHit(BaseModel):
    """单个命中标的(客观数据 · 含匹配的指标值)。"""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    name: str
    last_price: float
    change_pct: float
    rsi_14: float | None = None
    ma_5: float | None = None
    ma_20: float | None = None
    ma_60: float | None = None
    macd_golden: bool | None = None
    kdj_golden: bool | None = None
    boll_bandwidth: float | None = None
    volume_ratio: float | None = None


class ScreenerResponse(BaseModel):
    """筛选结果 · 分页 + 诚实标注(技术指标候选上限)+ 红线免责。"""

    model_config = ConfigDict(extra="forbid")

    market: str
    total: int = Field(description="匹配总数(分页前)")
    page: int
    page_size: int
    scanned: int = Field(description="实际扫描的候选数")
    candidate_capped: bool = Field(
        description="技术指标筛选是否触及候选上限(true = 仅覆盖成交最活跃的前 N 只)",
    )
    hits: list[ScreenerHit]
    disclaimer: str
