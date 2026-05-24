"""A股榜单 / 情绪 / 行业板块 契约(0023 阶段③ · 3.2)。

数据源:Sina(stock_zh_a_spot 全市场 + stock_sector_spot 行业板块)· 东财 _em 本地不可达。
红线:只读行情。frozen + extra=forbid · ts 全 tz-aware UTC。

本期榜单只做 3 个维度(涨幅/跌幅/成交额)· 换手率/量比 Sina 无该字段、东财不可达 →
本期不做、界面不体现(后续待办)。
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class CnSpotRow(BaseModel):
    """A股个股实时快照单行(Sina stock_zh_a_spot)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1, description="纯代码(去 sh/sz/bj 前缀)· 如 '600519'")
    name: str = Field(min_length=1)
    last_price: float = Field(ge=0, description="最新价(停牌可能为 0)")
    change_pct: float = Field(description="涨跌幅 %(已是百分数 · 可负)")
    change_amount: float = Field(description="涨跌额(可负)")
    amount: float = Field(ge=0, description="成交额(元)")
    volume: float = Field(ge=0, description="成交量(股)")


class CnBreadth(BaseModel):
    """A股市场情绪条 · 全市场快照精确聚合 + 涨跌停估算。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ts: AwareDatetime
    up_count: int = Field(ge=0, description="上涨家数(涨跌幅 > 0)")
    down_count: int = Field(ge=0, description="下跌家数(涨跌幅 < 0)")
    flat_count: int = Field(ge=0, description="平盘家数(涨跌幅 = 0 · 含停牌)")
    limit_up_count: int = Field(
        ge=0, description="涨停家数(估算 · 按板块涨跌幅阈值 · 东财涨跌停池不可达)",
    )
    limit_down_count: int = Field(ge=0, description="跌停家数(估算 · 同上口径)")
    total_amount: float = Field(ge=0, description="两市总成交额(元)")


class CnSector(BaseModel):
    """A股行业板块单行(Sina stock_sector_spot · 新浪行业)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, description="板块名(如 '玻璃行业')")
    change_pct: float = Field(description="板块涨跌幅 %(可负)")
    stock_count: int = Field(ge=0, description="成分股家数")
    total_amount: float = Field(ge=0, description="板块总成交额(元)")
    leader_name: str = Field(default="", description="代表/领涨股名")
    leader_change_pct: float = Field(default=0.0, description="代表股涨跌幅 %")


class CnBoardResponse(BaseModel):
    """`GET /api/v1/cn/board` 响应 · 情绪条 + 3 榜单 + 行业板块。

    榜单是同一份全市场快照的 3 种排序(涨幅/跌幅/成交额)· 前端 Tab 内存切换。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    breadth: CnBreadth | None = Field(default=None, description="情绪条 · 无数据为 null")
    data_as_of: AwareDatetime | None = Field(default=None, description="快照最新时间 · 截至")
    gainers: list[CnSpotRow] = Field(description="涨幅榜(change_pct DESC)")
    losers: list[CnSpotRow] = Field(description="跌幅榜(change_pct ASC)")
    top_amount: list[CnSpotRow] = Field(description="成交额榜(amount DESC)")
    sectors: list[CnSector] = Field(description="行业板块(change_pct DESC)")
