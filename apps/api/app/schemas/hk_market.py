"""港股榜单 / 情绪契约(港股首页全市场 · 对标 A股 cn_market)。

数据源:新浪 `stock_hk_spot`(全市场 ~2764 只 · 最新价/涨跌幅/成交额)· 东财 _em 生产不可达。
港股特性 vs A股:
  ① 港股**无涨跌停制度** → breadth 不含 limit 字段(对比 CnBreadth 的涨跌停估算)。
  ② 板块暂不做(港股全市场无现成行业聚合源)· /hk/board 无 sectors · 留后续。
红线:只读行情 · frozen + extra=forbid · ts 全 tz-aware UTC。
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class HkSpotRow(BaseModel):
    """港股个股实时快照单行(新浪 stock_hk_spot)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1, description="5 位港股代码 · 如 '00700'")
    name: str = Field(min_length=1, description="中文名称")
    last_price: float = Field(ge=0, description="最新价(停牌可能为 0)")
    change_pct: float = Field(description="涨跌幅 %(已是百分数 · 可负)")
    change_amount: float = Field(description="涨跌额(可负)")
    amount: float = Field(ge=0, description="成交额(港币元)")
    volume: float = Field(ge=0, description="成交量(股)")


class HkBreadth(BaseModel):
    """港股市场情绪条 · 全市场涨跌平家数 + 总成交额。

    ★ 港股无涨跌停制度 → 不含 limit_up/limit_down(对比 A股 CnBreadth)。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ts: AwareDatetime
    up_count: int = Field(ge=0, description="上涨家数(涨跌幅 > 0)")
    down_count: int = Field(ge=0, description="下跌家数(涨跌幅 < 0)")
    flat_count: int = Field(ge=0, description="平盘家数(涨跌幅 = 0 · 含停牌)")
    total_amount: float = Field(ge=0, description="全市场总成交额(港币元)")


class HkBoardResponse(BaseModel):
    """`GET /api/v1/hk/board` 响应 · 情绪条 + 3 榜单。

    榜单是同一份全市场快照(~2764 只)的 3 种排序(涨幅/跌幅/成交额)· 前端 Tab 内存切换。
    ★ 板块暂不做(港股全市场无现成行业源)· 留后续。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    breadth: HkBreadth | None = Field(default=None, description="情绪条 · 无数据为 null")
    data_as_of: AwareDatetime | None = Field(default=None, description="快照最新时间 · 截至")
    gainers: list[HkSpotRow] = Field(description="涨幅榜(change_pct DESC)")
    losers: list[HkSpotRow] = Field(description="跌幅榜(change_pct ASC)")
    top_amount: list[HkSpotRow] = Field(description="成交额榜(amount DESC)")


class HkBoardLotScanResult(BaseModel):
    """`GET /api/v1/hk/board-lot-scan` 响应 · 阶段三方案 A1 生产实测可达。

    HKEX 官方 List of Securities 下载 + 解析摘要(只读不写库)· 验证生产 VPS 可达 + 解析正确。
    不返完整 ~2406 lot 字典(太大)· 只返计数 + 抽验样本。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool = Field(description="下载+解析整体成功")
    http_code: int = Field(description="HKEX xlsx 下载 HTTP 状态(应 200)")
    bytes_downloaded: int = Field(description="下载字节数(本机实测 ~1.4MB)")
    updated_as_at: str | None = Field(default=None, description="文件头 Updated as at · 新鲜度")
    total_rows: int = Field(description="文件全部证券行数(~17880 · 含衍生/债)")
    mainboard_hkd_count: int = Field(description="主板 HKD 普通股数(= 下单池目标 · 应 ~2406)")
    parse_errors: int = Field(description="board lot 解析失败数(应 0)")
    samples: dict[str, int] = Field(
        default_factory=dict,
        description="抽验样本(00700=100 / 00005=400 / 01211=100 验解析对)",
    )
    error: str | None = Field(default=None, description="失败原因(ok=False 时)")


class HkKlineSourceProbe(BaseModel):
    """`GET /api/v1/hk/kline-source-probe` 响应 · 方案A 阶段1 生产实测可达(只读)。

    探测新浪 stock_hk_daily(主源候选)+ yfinance(现备用)对同一冷门股的可达性 + 行数。
    确认新浪生产可达后,阶段2 再正式接入降级链主源。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    sina_ok: bool = Field(description="新浪 stock_hk_daily 生产可达 + 有数据")
    sina_rows: int = Field(description="新浪返回行数(本机 00980=5388)")
    sina_last: str | None = Field(default=None, description="新浪最后一根 date close")
    sina_error: str | None = Field(default=None, description="新浪失败原因")
    yfinance_ok: bool = Field(description="yfinance 现备用源可达")
    yfinance_rows: int = Field(description="yfinance 返回行数(探测用 1mo)")
    yfinance_error: str | None = Field(default=None, description="yfinance 失败原因")


class HkSectorProbeResult(BaseModel):
    """`GET /api/v1/hk/sector-probe` 响应 · 港股板块源 yfinance `.info` sector 生产探测(只读)。

    验唯一可达免费行业源(yfinance GICS sector)的【批量速率 + 限流 + 拿到率】· 不写库不改板块。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    requested: int = Field(description="抽样请求数(行情池成交额前 N)")
    ok: int = Field(description="拿到非空 sector 数")
    empty_sector: int = Field(description=".info 成功但 sector 空(小盘常见 → 归其他)")
    failed: int = Field(description="调用异常数(含限流 / 超时)")
    total_seconds: float = Field(description="批量总耗时(并发 wall-clock)· 折算 ~900 看撑不撑得起")
    avg_seconds: float = Field(description="摊到每只")
    sector_dist: dict[str, int] = Field(default_factory=dict, description="sector → 命中数(看分布)")
    samples: dict[str, str] = Field(default_factory=dict, description="code → sector 抽样(人眼看)")
    errors: list[str] = Field(default_factory=list, description="失败原因抽样(★看有没有 429 限流)")
