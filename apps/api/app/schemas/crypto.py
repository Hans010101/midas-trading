"""Crypto Pro · Pydantic 契约(0017 ADR · M2-A)。

对应 ClickHouse 5 张新表 + Binance Futures / CoinGecko / alternative.me
三个上游的领域模型。

时区:所有 ts 字段必须是 tz-aware UTC datetime。
symbol 格式:
- Funding / OI / long-short: Binance Futures 风格 `BTCUSDT`(无斜杠)
- Ticker24h / Kline (perp): ccxt 风格 `BTC/USDT`(跟现有 spot 表对齐)

设计跟 schemas/market.py 同款:`model_config = ConfigDict(extra="forbid", frozen=True)`。
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Instrument = Literal["spot", "perp"]


# ============================================================================
# 1 · Funding Rate(资金费率)
# ============================================================================


class FundingRate(BaseModel):
    """资金费率单点 · 8h 结算一次。

    上游 Binance fapi/v1/fundingRate,symbol 用 `BTCUSDT` 无斜杠风格。
    rate 是 decimal · 0.0001 = 0.01% · **不要乘 100 存**。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1, description="Binance Futures symbol · 'BTCUSDT'")
    ts: AwareDatetime = Field(description="结算时间 · UTC")
    rate: float = Field(description="资金费率 · decimal 0.0001 = 0.01%")
    mark_price: float = Field(gt=0, description="结算时标记价")


class FundingRateResponse(BaseModel):
    """`/api/v1/crypto/futures/{symbol}/funding-rate` 响应。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    items: list[FundingRate]


# ============================================================================
# 2 · Open Interest(未平仓量)
# ============================================================================


class OpenInterest(BaseModel):
    """OI 单点 · 5min 栅格。

    上游 Binance futures/data/openInterestHist · period=5m。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1)
    ts: AwareDatetime
    oi_coin: float = Field(ge=0, description="未平仓量(币计 · BTC etc.)")
    oi_usd: float = Field(ge=0, description="未平仓量(美元计)")


class OpenInterestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    symbol: str
    items: list[OpenInterest]


# ============================================================================
# 3 · Long/Short Ratio(多空比 · 三套指标)
# ============================================================================


class LongShortRatio(BaseModel):
    """多空比单点 · 5min 栅格 · 同时含三套指标。

    上游 Binance:
    - topLongShortAccountRatio   → top_account_*(top trader 账户多空比)
    - topLongShortPositionRatio  → top_position_*(top trader 持仓多空比)
    - takerlongshortRatio        → taker_*(taker buy/sell 量比)

    一次 Celery 任务并发拉三个上游 · 合并写入 ClickHouse。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1)
    ts: AwareDatetime
    top_account_long: float = Field(ge=0, le=1, description="多账户占比 · 0..1")
    top_account_short: float = Field(ge=0, le=1)
    top_account_ratio: float = Field(ge=0, description="long / short")
    top_position_long: float = Field(ge=0, le=1)
    top_position_short: float = Field(ge=0, le=1)
    top_position_ratio: float = Field(ge=0)
    taker_buy_vol: float = Field(ge=0)
    taker_sell_vol: float = Field(ge=0)
    taker_ratio: float = Field(ge=0)


class LongShortRatioResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    symbol: str
    items: list[LongShortRatio]


# ============================================================================
# 4 · 24h Ticker(全币种行情快照 · 涨幅榜)
# ============================================================================


class Ticker24h(BaseModel):
    """24h ticker · 全币种快照 · 1min 节奏。

    symbol 统一 ccxt 风格 `BTC/USDT`(跟现有 spot kline 表对齐)。
    instrument 区分 spot/perp。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1, description="ccxt 风格 'BTC/USDT'")
    instrument: Instrument
    ts: AwareDatetime
    last_price: float = Field(gt=0)
    change_pct_24h: float = Field(description="24h 涨跌(已乘 100 · % 单位)")
    high_24h: float = Field(gt=0)
    low_24h: float = Field(gt=0)
    volume_24h: float = Field(ge=0, description="base 币种成交量")
    quote_volume_24h: float = Field(ge=0, description="USDT 计成交额")
    count_24h: int = Field(default=0, ge=0, description="24h 笔数 · spot 才有")


class Tickers24hResponse(BaseModel):
    """`/api/v1/crypto/tickers/24h` 响应 · 默认按 change_pct_24h DESC。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument: Instrument
    sort_by: Literal["change_pct_24h", "quote_volume_24h", "last_price"] = "change_pct_24h"
    order: Literal["desc", "asc"] = "desc"
    items: list[Ticker24h]


class FuturesMetricItem(BaseModel):
    """榜单级合约指标单条 · 字段缺采集时为 None(前端显示「—」· 不造假)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(description="Binance 风格 · 'BTCUSDT'")
    funding_rate: float | None = Field(default=None, description="最新资金费率 · decimal")
    account_long_short_ratio: float | None = Field(default=None, description="账户多空比 long/short")
    oi_change_pct_24h: float | None = Field(default=None, description="OI 近 24H 变化%")


class FuturesMetricsBatchResponse(BaseModel):
    """`/api/v1/crypto/futures/metrics-batch` 响应 · 给列表页 3 列批量取数。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[FuturesMetricItem]


# ============================================================================
# 5 · 全市场 Overview + Fear & Greed Index
# ============================================================================


class MarketOverview(BaseModel):
    """全市场单点快照 · 5min 节奏(CoinGecko)+ 1day 节奏(alternative.me)。

    CoinGecko `/api/v3/global` 提供 total_market_cap / dominance / derivatives。
    alternative.me `/fng` 提供 fear_greed_value + classification。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ts: AwareDatetime
    total_market_cap_usd: float = Field(ge=0)
    total_volume_24h_usd: float = Field(ge=0)
    btc_dominance: float = Field(ge=0, le=100, description="BTC 市值占比 · 0..100")
    eth_dominance: float = Field(ge=0, le=100)
    fear_greed_value: int = Field(ge=0, le=100, description="0=Extreme Fear, 100=Extreme Greed")
    fear_greed_classification: str = Field(
        default="",
        description="Extreme Fear / Fear / Neutral / Greed / Extreme Greed",
    )
    derivatives_oi_usd: float = Field(default=0, ge=0)
    derivatives_volume_24h_usd: float = Field(default=0, ge=0)


class FearGreedPoint(BaseModel):
    """FGI 单点(给 /api/v1/crypto/fear-greed 时间序列用)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ts: AwareDatetime
    value: int = Field(ge=0, le=100)
    classification: str


class FearGreedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    items: list[FearGreedPoint]


# ============================================================================
# 6 · 合约元信息(下次资金费率 / 标记价 / 最大杠杆 etc.)
# ============================================================================


class FuturesSymbolInfo(BaseModel):
    """`/api/v1/crypto/futures/{symbol}/info` 响应。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    base_asset: str  # e.g. "BTC"
    quote_asset: str  # e.g. "USDT"
    contract_type: Literal["perpetual", "current_quarter", "next_quarter"]
    mark_price: float = Field(gt=0)
    index_price: float = Field(gt=0)
    last_funding_rate: float = Field(description="最近一次资金费率(decimal)")
    next_funding_time: AwareDatetime = Field(description="下次资金费率结算时间")
    max_leverage: int = Field(gt=0, le=200, description="最大杠杆(perp 通常 1-125)")
    open_interest_coin: float = Field(ge=0)
    open_interest_usd: float = Field(ge=0)


# ============================================================================
# 7 · 顶层 Overview 响应(给 /api/v1/crypto/overview 用)
# ============================================================================


class CryptoOverviewResponse(BaseModel):
    """`/api/v1/crypto/overview` 响应 · 给加密 tab landing page 用。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    market_overview: MarketOverview
    top_gainers: list[Ticker24h] = Field(description="涨幅榜 top 5")
    top_losers: list[Ticker24h] = Field(description="跌幅榜 top 5")
    top_volume: list[Ticker24h] = Field(description="成交榜 top 5")
    # 主页 BTC/ETH 价格卡专用 · 按 symbol 精确取(不依赖涨跌幅榜,否则大盘币不在榜上 → 卡空)
    btc_ticker: Ticker24h | None = Field(default=None, description="BTC/USDT 永续最新 ticker")
    eth_ticker: Ticker24h | None = Field(default=None, description="ETH/USDT 永续最新 ticker")
