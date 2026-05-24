"""美股榜单 / 行业·中概板块 契约(0023 阶段③ · 3.3)。

数据源:yfinance 批量拉策展池(决策⑥)· 榜单 = 策展池内排行(非全市场 · 诚实标注)。
成交额为美元估算(close × volume · yfinance 无直接美元成交额)。
frozen + extra=forbid · ts 全 tz-aware UTC。红线:只读行情。
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class UsSpotRow(BaseModel):
    """美股策展池个股快照单行。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1, description="yfinance 代码 · 如 'AAPL'")
    name: str = Field(min_length=1, description="中文名")
    sector: str = Field(min_length=1, description="板块(11 GICS 行业 / 中概股)")
    last_price: float = Field(ge=0)
    change_pct: float = Field(description="涨跌幅 %(可负)")
    amount: float = Field(ge=0, description="成交额(美元估 · close × volume)")
    volume: float = Field(ge=0, description="成交量(股)")


class UsSector(BaseModel):
    """美股板块聚合(策展池内 · 行业 / 中概股)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, description="板块名(科技 / 金融 / 中概股 …)")
    change_pct: float = Field(description="板块涨跌幅 %(成分等权均值 · 可负)")
    stock_count: int = Field(ge=0, description="池内成分股数")
    total_amount: float = Field(ge=0, description="板块成交额(美元估)")


class UsBoardResponse(BaseModel):
    """`GET /api/v1/us/board` 响应 · 重点关注池排行 + 行业/中概板块。

    榜单为同一份策展池快照的 3 种排序(涨幅/跌幅/成交额)· 前端 Tab 内存切换。
    sectors 含「中概股」板块(即中概股板块)。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    data_as_of: AwareDatetime | None = Field(default=None, description="快照最新时间 · 截至")
    pool_size: int = Field(ge=0, description="策展池实际有数据的股票数")
    gainers: list[UsSpotRow] = Field(description="涨幅榜(池内 · change_pct DESC)")
    losers: list[UsSpotRow] = Field(description="跌幅榜(池内 · change_pct ASC)")
    top_amount: list[UsSpotRow] = Field(description="成交额榜(池内 · amount DESC)")
    sectors: list[UsSector] = Field(description="行业板块 + 中概股板块(change_pct DESC)")
