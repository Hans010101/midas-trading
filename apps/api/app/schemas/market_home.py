"""A股 / 美股 市场首页契约(0023 阶段③ · 3.1 基建)。

借用加密 schemas/crypto.py 同款:`model_config = ConfigDict(extra="forbid", frozen=True)`,
所有 ts 字段为 tz-aware UTC datetime。

3.1 范围:大盘指数卡(IndexQuote)+ 市场状态/交易时段(MarketStatusInfo)+
首页总览(MarketHomeOverview = status + indices)。榜单 / 涨跌家数 / 板块 = 3.2 / 3.3。
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# 本期只 cn / us(crypto 有独立 /crypto/* 通道 · 不复用本契约)
MarketKind = Literal["cn", "us"]

# 状态机(0023 §3)· canonical 枚举供前端上色;label 文案可更细(午间休市 / 待开盘)
MarketStatusCode = Literal[
    "open",            # 盘中(连续竞价)
    "pre_market",      # 盘前(仅美股)
    "post_market",     # 盘后(仅美股)
    "closed",          # 交易日内非交易时段(午休 / 待开盘 / 已收盘)
    "closed_holiday",  # 休市(周末 / 节假日)
]


class IndexQuote(BaseModel):
    """大盘指数单点快照 · 上证/深成/创业板/沪深300 · 道指/纳指/标普/罗素。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    market: MarketKind
    symbol: str = Field(min_length=1, description="cn=Sina 代码 'sh000001' · us=yfinance '^DJI'")
    name: str = Field(min_length=1, description="指数名(上证指数 / 标普500 …)")
    ts: AwareDatetime = Field(description="快照时间 · UTC")
    last_point: float = Field(gt=0, description="最新点位")
    prev_close: float = Field(ge=0, description="昨收点位")
    change_point: float = Field(description="涨跌点(可负)")
    change_pct: float = Field(description="涨跌幅 % · 已是百分数(可负)")


class MarketStatusInfo(BaseModel):
    """市场状态 / 交易时段(0023 §3 · 避免用户误以为实时)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    market: MarketKind
    status: MarketStatusCode
    label: str = Field(description="中文展示文案(盘中 / 盘前 / 盘后 / 午间休市 / 已收盘 / 休市)")
    is_trading_now: bool = Field(description="当前是否连续竞价盘中(status == open)")
    as_of: AwareDatetime = Field(description="状态计算时刻 · 服务端 now · UTC")
    data_as_of: AwareDatetime | None = Field(
        default=None, description="指数快照最新时间(展示「截至 …」)· 无数据为 null",
    )


class MarketHomeOverview(BaseModel):
    """`GET /api/v1/{cn|us}/overview` 响应 · 给市场首页骨架(3.1)。

    3.1 = status + indices。3.2(A股榜单)/ 3.3(美股榜单)再往里加 rankings / breadth / sectors。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    market: MarketKind
    status: MarketStatusInfo
    indices: list[IndexQuote]
