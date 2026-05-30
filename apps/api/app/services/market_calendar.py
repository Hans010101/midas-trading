"""交易时段 / 市场状态状态机(0023 阶段③ · 3.1)· 纯逻辑 · 可单测。

0023 §3 状态机:休市(周末/节假日)/ 盘前 / 盘中 / 盘后 / 已收盘。
- A股(CST):连续竞价 9:30–11:30 / 13:00–15:00 · 无盘前盘后(午休/待开盘/收盘 = closed)
- 美股(ET):盘前 4:00–9:30 / 盘中 9:30–16:00 / 盘后 16:00–20:00 · zoneinfo 自动处理 EST/EDT 夏令时
- 港股(HKT):早盘 9:30–12:00 / 午休 / 午盘 13:00–16:00 · 无盘前盘后(同 A 股教学版)· 全年 UTC+8 无 DST

交易日判定:
- A股:优先用 CH market_trade_calendar(AKShare tool_trade_date_hist_sina 采集)·
  日历未就绪(冷启动 / 上游不可达)时回退到「周一至周五」(忽略节假日)
- 美股:周一至周五 减去 US_MARKET_HOLIDAYS 硬编码节假日(2026 baseline · 后续可接日历源)

时区铁律:入参 now_utc 必须 tz-aware UTC · astimezone 到市场本地时区算时段。
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.schemas.market_home import MarketKind, MarketStatusCode, MarketStatusInfo

CN_TZ = ZoneInfo("Asia/Shanghai")
US_TZ = ZoneInfo("America/New_York")
HK_TZ = ZoneInfo("Asia/Hong_Kong")  # 港股 · 全年 UTC+8 无夏令时

# A股连续竞价时段(CST)· 集合竞价并入(教学版不细分盘前)
_CN_MORNING: tuple[time, time] = (time(9, 30), time(11, 30))
_CN_AFTERNOON: tuple[time, time] = (time(13, 0), time(15, 0))

# 美股时段(ET · zoneinfo 自动 DST)· 盘前 / 常规盘 / 盘后
_US_PRE: tuple[time, time] = (time(4, 0), time(9, 30))
_US_REGULAR: tuple[time, time] = (time(9, 30), time(16, 0))
_US_POST: tuple[time, time] = (time(16, 0), time(20, 0))

# 港股时段(HKT)· 早盘 9:30–12:00 / 午休 12:00–13:00 / 午盘 13:00–16:00 · 无盘前盘后(同 A 股教学版)
_HK_MORNING: tuple[time, time] = (time(9, 30), time(12, 0))
_HK_AFTERNOON: tuple[time, time] = (time(13, 0), time(16, 0))

# 美股全天休市节假日(NYSE / Nasdaq)· 2026 baseline · 硬编码(yfinance 无干净日历 API)
# 周末已由 weekday 判定挡掉 · 这里只列工作日落上的节假日。
US_MARKET_HOLIDAYS: frozenset[date] = frozenset(
    {
        date(2026, 1, 1),    # New Year's Day
        date(2026, 1, 19),   # Martin Luther King Jr. Day
        date(2026, 2, 16),   # Washington's Birthday
        date(2026, 4, 3),    # Good Friday
        date(2026, 5, 25),   # Memorial Day
        date(2026, 6, 19),   # Juneteenth
        date(2026, 7, 3),    # Independence Day(7/4 为周六 · 周五补休)
        date(2026, 9, 7),    # Labor Day
        date(2026, 11, 26),  # Thanksgiving
        date(2026, 12, 25),  # Christmas
    },
)

# 港股全天休市节假日(SEHK)· 2026 baseline · ★ 待核港交所官方交易日历。
# 农历浮动节(清明 / 佛诞 / 端午 / 中秋翌日 / 重阳)每年日期变 → 此处先列高置信的固定节 + 农历新年 +
# 复活节;未覆盖的由「周一至周五」回退兜底(可能把某浮动节误判为交易日)。hk 无数据,仅状态机壳;
# P1-3 采集后对齐官方日历再补全。
HK_MARKET_HOLIDAYS: frozenset[date] = frozenset(
    {
        date(2026, 1, 1),    # 元旦
        date(2026, 2, 17),   # 农历年初一(★待核)
        date(2026, 2, 18),   # 年初二(★待核)
        date(2026, 2, 19),   # 年初三(★待核)
        date(2026, 4, 3),    # 耶稣受难节
        date(2026, 4, 6),    # 复活节后星期一
        date(2026, 5, 1),    # 劳动节
        date(2026, 7, 1),    # 香港特别行政区成立纪念日
        date(2026, 10, 1),   # 国庆节
        date(2026, 12, 25),  # 圣诞节
    },
)


def _in_window(t: time, window: tuple[time, time]) -> bool:
    start, end = window
    return start <= t < end


def _cn_status(
    now_utc: datetime, cn_trading_days: frozenset[date] | None,
) -> tuple[MarketStatusCode, str, bool]:
    local = now_utc.astimezone(CN_TZ)
    if not _is_cn_trading_day(local.date(), cn_trading_days):
        return "closed_holiday", "休市", False
    t = local.time()
    if _in_window(t, _CN_MORNING) or _in_window(t, _CN_AFTERNOON):
        return "open", "盘中", True
    if _CN_MORNING[1] <= t < _CN_AFTERNOON[0]:
        return "closed", "午间休市", False
    if t < _CN_MORNING[0]:
        return "closed", "待开盘", False
    return "closed", "已收盘", False


def _is_cn_trading_day(d: date, cn_trading_days: frozenset[date] | None) -> bool:
    if cn_trading_days:
        return d in cn_trading_days
    # 日历未就绪(冷启动 / 上游不可达)· 回退周一至周五(忽略节假日 · 状态机降级)
    return d.weekday() < 5  # noqa: PLR2004


def _us_status(now_utc: datetime) -> tuple[MarketStatusCode, str, bool]:
    local = now_utc.astimezone(US_TZ)
    d = local.date()
    if d.weekday() >= 5 or d in US_MARKET_HOLIDAYS:  # noqa: PLR2004
        return "closed_holiday", "休市", False
    t = local.time()
    if _in_window(t, _US_REGULAR):
        return "open", "盘中", True
    if _in_window(t, _US_PRE):
        return "pre_market", "盘前", False
    if _in_window(t, _US_POST):
        return "post_market", "盘后", False
    return "closed", "已收盘", False


def _hk_status(now_utc: datetime) -> tuple[MarketStatusCode, str, bool]:
    """港股状态(HKT)· 早盘/午休/午盘 · 无盘前盘后(同 A 股教学版)。"""
    local = now_utc.astimezone(HK_TZ)
    d = local.date()
    if d.weekday() >= 5 or d in HK_MARKET_HOLIDAYS:  # noqa: PLR2004
        return "closed_holiday", "休市", False
    t = local.time()
    if _in_window(t, _HK_MORNING) or _in_window(t, _HK_AFTERNOON):
        return "open", "盘中", True
    if _HK_MORNING[1] <= t < _HK_AFTERNOON[0]:
        return "closed", "午间休市", False
    if t < _HK_MORNING[0]:
        return "closed", "待开盘", False
    return "closed", "已收盘", False


def compute_market_status(
    market: MarketKind,
    *,
    now_utc: datetime,
    data_as_of: datetime | None = None,
    cn_trading_days: frozenset[date] | None = None,
) -> MarketStatusInfo:
    """算市场状态 · A股看 CH 交易日历(传 cn_trading_days)· 美股用硬编码节假日。"""
    if market == "cn":
        code, label, trading = _cn_status(now_utc, cn_trading_days)
    elif market == "hk":
        code, label, trading = _hk_status(now_utc)
    else:
        code, label, trading = _us_status(now_utc)
    return MarketStatusInfo(
        market=market,
        status=code,
        label=label,
        is_trading_now=trading,
        as_of=now_utc,
        data_as_of=data_as_of,
    )
