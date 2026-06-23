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
    """多空比单点 · 5min 栅格 · 同时含四套指标。

    上游 Binance:
    - topLongShortAccountRatio    → top_account_*(top trader 账户多空比)
    - topLongShortPositionRatio   → top_position_*(top trader 持仓多空比)
    - takerlongshortRatio         → taker_*(taker buy/sell 量比)
    - globalLongShortAccountRatio → global_account_*(全市场人数比 · 刀C)

    一次 Celery 任务拉四个上游 · 合并写入 ClickHouse。
    ★ global 是 left-join 语义(top 三件套 ts 交集为主干 · global 配不上留 0,
      绝不因 global 缺失丢整行);0 = 未采哨兵(真值恒 >0 · 前端据此过滤老行)。
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
    # 刀C · 全市场人数比 · default 0 = 该 ts 未采到 global(老行/上游错位)
    global_account_long: float = Field(default=0.0, ge=0, le=1)
    global_account_short: float = Field(default=0.0, ge=0, le=1)
    global_account_ratio: float = Field(default=0.0, ge=0)


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


# ── 布林做T结构信号(做T功能 A-1)· 只读 boll:snapshot:latest 快照 ──────────────
# ★全是结构描述 · bias 仅 偏多/偏空/中性 · 绝无买卖祈使词 · 响应顶层带免责(锁死红线)。


class BollScanItem(BaseModel):
    """单币布林结构信号(纯描述 · 复用 M1 boll_state 计算 · 不预测、不建议)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1, description="Binance 风格 'BTCUSDT'(无斜杠)")
    state: str = Field(description="6 口诀状态枚举值(trend_up/range/squeeze/…)")
    state_label: str = Field(description="状态中文口诀(三线齐上·上升结构 等)")
    bias: str = Field(description="结构倾向 · 仅 偏多/偏空/中性(描述非建议)")
    pct_b: float = Field(description="通道位置 %B = (close-lower)/(upper-lower)")
    zone_label: str = Field(description="通道位置中文(破上轨/近上轨/近中轨/近下轨/破下轨/中间)")
    bandwidth: float = Field(description="带宽 = (upper-lower)/mid · 布林衍生(结构数据,无方向)")
    close: float = Field(gt=0)
    mid: float = Field(gt=0, description="布林中轨 MA20")
    upper: float = Field(gt=0, description="布林上轨 +2σ")
    lower: float = Field(gt=0, description="布林下轨 −2σ")
    change_pct_24h: float | None = Field(default=None, description="24h 涨跌% · 缺采集为 None")
    funding_rate: float | None = Field(default=None, description="最新资金费率 · 缺为 None")
    transition: bool = Field(default=False, description="本轮是否发生状态转换(边沿)")
    transition_from: str | None = Field(
        default=None, description="转换前状态中文(仅 transition=true 时有)",
    )


class BollScanResponse(BaseModel):
    """`/api/v1/crypto/boll-scan` 响应 · 做T结构信号列表(只读快照 · 无快照返空列表)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of: AwareDatetime | None = Field(default=None, description="快照时间 · None=暂无快照")
    count: int = Field(ge=0, description="筛选后条数")
    disclaimer: str = Field(
        default="结构描述非建议 · 仅供参考,不构成投资建议",
        description="免责口径(供前端展示 · 锁死红线)",
    )
    items: list[BollScanItem]


class BollStructureResponse(BaseModel):
    """`/api/v1/crypto/boll-structure/{symbol}` 响应 · 单币布林做T结构(做T B-1)。

    数据来源:Top150 命中 A-1 快照(零重算)· 长尾按需现算 · 无数据/数据不足优雅降级
    (available=False · 不报错)。结构口径与 A-1 列表 / TG 影子同源(boll_state.classify)。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1, description="Binance 风格 'BTCUSDT'(无斜杠)")
    available: bool = Field(description="是否有结构数据(False=无数据/不足20根/非加密 · 不报错)")
    source: Literal["snapshot", "computed", "none"] = Field(
        description="数据来源:snapshot=复用 A-1 快照 · computed=按需现算 · none=不可用",
    )
    layer: str = Field(
        default="布林结构",
        description="★层级标注 · 这是【布林结构层面】的描述(区别于 AI 决策卡综合研判)",
    )
    as_of: AwareDatetime | None = Field(default=None, description="结构时间 · None=不可用")
    item: BollScanItem | None = Field(default=None, description="结构数据 · 不可用时 None")
    disclaimer: str = Field(
        default="结构描述非建议 · 仅供参考,不构成投资建议",
        description="免责口径(锁死红线)",
    )


class FuturesMetricItem(BaseModel):
    """榜单级合约指标单条 · 字段缺采集时为 None(前端显示「—」· 不造假)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(description="Binance 风格 · 'BTCUSDT'")
    funding_rate: float | None = Field(default=None, description="最新资金费率 · decimal")
    account_long_short_ratio: float | None = Field(
        default=None, description="账户多空比 long/short",
    )
    oi_change_pct_24h: float | None = Field(default=None, description="OI 近 24H 变化%")


class FuturesMetricsBatchResponse(BaseModel):
    """`/api/v1/crypto/futures/metrics-batch` 响应 · 给列表页 3 列批量取数。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[FuturesMetricItem]


# ============================================================================
# 4.5 · Premium Index(标记价 / 指数价 / 资金费 实时快照)· M2-C.2.1 · ADR-0020
# ============================================================================


class PremiumIndex(BaseModel):
    """premiumIndex 单点 · 标记价 / 指数价 / 资金费实时快照。

    上游 Binance fapi/v1/premiumIndex(无 symbol = 全市场单请求)· symbol 用
    `BTCUSDT` 无斜杠风格(跟 funding / OI / long-short 表一致)。
    - mark_price:标记价 → 撮合 / 强平价源(M2-C.2.1 起替代 perp ticker last_price)
    - index_price:指数价(现货综合)· 基差 = mark - index(补 M2-B 基差缺口)
    - last_funding_rate / next_funding_time:给 futures/info(修 +8h bug)+ M2-C.2.2 资金费结算
    - funding_interval_hours:资金费周期 · 暂统一 8(per-symbol 周期 M2-C.2.2 再回源 fundingInfo)
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1, description="Binance Futures symbol · 'BTCUSDT'")
    ts: AwareDatetime = Field(description="快照时间 · UTC")
    mark_price: float = Field(gt=0, description="标记价")
    index_price: float = Field(gt=0, description="指数价(现货综合)")
    last_funding_rate: float = Field(description="最近资金费率 · decimal 0.0001=0.01%")
    next_funding_time: AwareDatetime = Field(description="下次资金费结算时间 · UTC")
    funding_interval_hours: int = Field(
        default=8, gt=0, le=24, description="资金费周期(小时)· M2-C.2.2 用 · 暂统一 8",
    )


# 盘口深度档位数(沙盘三期第二批 · flatten 成 bid1..10 / ask1..10 列)
DEPTH_LEVELS = 10


class OrderbookDepth(BaseModel):
    """盘口深度快照 · Binance fapi/v1/depth top-N 档(沙盘三期第二批 · 刀1 采集)。

    symbol Binance 风格 `BTCUSDT`(跟 funding/OI/premium 一致)。
    bids 买盘价降序 · asks 卖盘价升序 · 各定长 DEPTH_LEVELS 档(不足由解析层补 (0,0))·
    每档 (price, qty)。落库 flatten 成 bid1_price..bid10_qty / ask… 列(crypto_orderbook_depth)。
    🔴 红线:只读盘口快照 · 采集层只 GET · 绝不接真实交易。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1, description="Binance Futures symbol · 'BTCUSDT'")
    ts: AwareDatetime = Field(description="盘口快照时间 · UTC")
    bids: tuple[tuple[float, float], ...] = Field(description="买盘 top-N · (price, qty) 价降序")
    asks: tuple[tuple[float, float], ...] = Field(description="卖盘 top-N · (price, qty) 价升序")


# ============================================================================
# 4.6 · 基差时序(详情页 ⑥ 基差图)· M2-C.2.4
# ============================================================================


class BasisPoint(BaseModel):
    """基差时序单点 · 来自 crypto_premium_index(每分钟一条)。

    基差率 basis_pct = (mark − index) / index × 100(% · 可正可负)。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ts: AwareDatetime
    mark_price: float = Field(gt=0, description="标记价")
    index_price: float = Field(gt=0, description="指数价")
    basis_pct: float = Field(description="基差率 % · (mark−index)/index×100 · 可负")


class BasisSeriesResponse(BaseModel):
    """`/api/v1/crypto/futures/{symbol}/basis` 响应 · 给 ⑥ 基差图。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    items: list[BasisPoint]


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


# ============================================================================
# 8 · 采集新鲜度监控(刀D 还债 · /api/v1/crypto/ingest-status)
# ============================================================================


class IngestSourceStatus(BaseModel):
    """加密采集源新鲜度(判 stale)· 阈值 = max(数据栅格, 任务频率) × 3。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    table: str
    latest_ts: AwareDatetime | None = Field(default=None, description="None = 从未采")
    age_seconds: float | None = Field(default=None, ge=0)
    expected_max_age_seconds: int = Field(ge=0)
    stale: bool


class EquityIngestStatus(BaseModel):
    """股票表裸报(v1 不判 stale:周末滞后是交易时段语义,非故障)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    table: str
    latest_ts: AwareDatetime | None = None
    age_seconds: float | None = Field(default=None, ge=0)


class IngestStatusResponse(BaseModel):
    """采集监控总览 · any_stale 给一眼/脚本判断。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of: AwareDatetime
    any_stale: bool
    crypto: list[IngestSourceStatus]
    equities: list[EquityIngestStatus]
