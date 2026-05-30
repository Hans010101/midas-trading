"""全球指标概览 Pydantic 契约(ADR 0035 阶段 A)。

★ 与交易维度【完全解耦】:`market` 是自由地区码字符串(us/jp/hk/de/global/fx/crypto),
  **不是** 交易 `Market` Literal(cn/us/crypto/hk)· 全球指标只读展示、不可交易。
所有 ts 字段为 tz-aware UTC。
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class OverviewQuote(BaseModel):
    """全球指标单点报价(指数/商品/外汇/债券/加密统一形状)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    market: str = Field(min_length=1, description="地区码 · 非交易市场(us/jp/hk/global/fx/crypto)")
    symbol: str = Field(min_length=1, description="ticker(^GSPC / GC=F / JPY=X / ^TNX / BTC/USDT)")
    name: str = Field(min_length=1, description="中文名")
    category: str = Field(min_length=1, description="index/commodity/forex/bond/crypto")
    unit: str = Field(description="point/price/rate/yield_pct(bond 涨跌用 bp)")
    ts: AwareDatetime = Field(description="快照时间 · UTC")
    last_point: float = Field(gt=0, description="最新值(点位/价格/汇率/收益率%)")
    prev_close: float = Field(ge=0, description="昨收/前值")
    change_point: float = Field(description="涨跌(可负)· bond 为收益率变动(×100=bp)")
    change_pct: float = Field(description="涨跌幅 %(可负)")


class OverviewGroup(BaseModel):
    """一个分类的指标组(环球指数 / 商品 / 外汇 / 债券 / 加密)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: str
    label: str
    items: list[OverviewQuote]


class GlobalOverviewResponse(BaseModel):
    """`GET /api/v1/overview/global` 响应 · 按分类分组。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    groups: list[OverviewGroup]
    as_of: AwareDatetime = Field(description="服务端响应时刻 · UTC")
