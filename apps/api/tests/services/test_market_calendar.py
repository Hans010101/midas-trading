"""交易时段 / 市场状态状态机单测(0023 阶段③ · 3.1)。

纯逻辑 · 不打网络 · 覆盖:
- A股:盘中 / 午间休市 / 待开盘 / 已收盘 / 交易日历命中 vs 回退 vs 休市
- 美股:盘前 / 盘中 / 盘后 / 已收盘 / 周末 / 节假日
- 美股 DST:同一 UTC 时刻在 EST(冬) vs EDT(夏)下解析到不同时段(zoneinfo 自动)
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.services.market_calendar import compute_market_status

# A股某交易日(2026-05-21 周四)· CST = UTC+8
_CN_DAY = frozenset({date(2026, 5, 21)})


def _utc(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


# ── A股 ──────────────────────────────────────────────────────────────────────


def test_cn_open_morning() -> None:
    # 10:00 CST = 02:00 UTC · 盘中
    s = compute_market_status("cn", now_utc=_utc(2026, 5, 21, 2), cn_trading_days=_CN_DAY)
    assert s.status == "open"
    assert s.is_trading_now is True
    assert s.label == "盘中"


def test_cn_lunch_break() -> None:
    # 12:00 CST = 04:00 UTC · 午间休市
    s = compute_market_status("cn", now_utc=_utc(2026, 5, 21, 4), cn_trading_days=_CN_DAY)
    assert s.status == "closed"
    assert s.is_trading_now is False
    assert s.label == "午间休市"


def test_cn_afternoon_open() -> None:
    # 14:00 CST = 06:00 UTC · 盘中
    s = compute_market_status("cn", now_utc=_utc(2026, 5, 21, 6), cn_trading_days=_CN_DAY)
    assert s.status == "open"


def test_cn_pre_open() -> None:
    # 09:00 CST = 01:00 UTC · 待开盘
    s = compute_market_status("cn", now_utc=_utc(2026, 5, 21, 1), cn_trading_days=_CN_DAY)
    assert s.status == "closed"
    assert s.label == "待开盘"


def test_cn_after_close() -> None:
    # 15:30 CST = 07:30 UTC · 已收盘
    s = compute_market_status("cn", now_utc=_utc(2026, 5, 21, 7, 30), cn_trading_days=_CN_DAY)
    assert s.status == "closed"
    assert s.label == "已收盘"


def test_cn_holiday_when_date_not_in_calendar() -> None:
    # 交易日历存在但当天不在 → 休市(节假日)
    s = compute_market_status(
        "cn", now_utc=_utc(2026, 5, 21, 2), cn_trading_days=frozenset({date(2026, 5, 20)}),
    )
    assert s.status == "closed_holiday"
    assert s.label == "休市"


def test_cn_calendar_fallback_weekday_trades() -> None:
    # 日历未就绪(None)· 周四盘中时间 → 回退周一至周五 → 盘中
    s = compute_market_status("cn", now_utc=_utc(2026, 5, 21, 2), cn_trading_days=None)
    assert s.status == "open"


def test_cn_calendar_fallback_weekend_closed() -> None:
    # 日历未就绪 · 周六(2026-05-23)→ 回退判定休市
    s = compute_market_status("cn", now_utc=_utc(2026, 5, 23, 2), cn_trading_days=None)
    assert s.status == "closed_holiday"


# ── 美股 ──────────────────────────────────────────────────────────────────────


def test_us_regular_open() -> None:
    # 2026-05-21 周四 10:00 EDT(UTC-4)= 14:00 UTC · 盘中
    s = compute_market_status("us", now_utc=_utc(2026, 5, 21, 14))
    assert s.status == "open"
    assert s.is_trading_now is True


def test_us_pre_market() -> None:
    # 05:00 EDT = 09:00 UTC · 盘前
    s = compute_market_status("us", now_utc=_utc(2026, 5, 21, 9))
    assert s.status == "pre_market"
    assert s.label == "盘前"


def test_us_post_market() -> None:
    # 17:00 EDT = 21:00 UTC · 盘后
    s = compute_market_status("us", now_utc=_utc(2026, 5, 21, 21))
    assert s.status == "post_market"
    assert s.label == "盘后"


def test_us_closed_overnight() -> None:
    # 02:00 EDT = 06:00 UTC · 已收盘(盘前前)
    s = compute_market_status("us", now_utc=_utc(2026, 5, 21, 6))
    assert s.status == "closed"
    assert s.label == "已收盘"


def test_us_weekend_closed() -> None:
    # 2026-05-23 周六 → 休市
    s = compute_market_status("us", now_utc=_utc(2026, 5, 23, 14))
    assert s.status == "closed_holiday"


def test_us_holiday_closed() -> None:
    # 2026-05-25 Memorial Day(周一)10:00 EDT = 14:00 UTC → 休市
    s = compute_market_status("us", now_utc=_utc(2026, 5, 25, 14))
    assert s.status == "closed_holiday"


def test_us_dst_same_utc_different_session() -> None:
    """同一 UTC 14:00 · 冬(EST UTC-5)= 09:00 盘前 · 夏(EDT UTC-4)= 10:00 盘中。

    证明 zoneinfo 自动处理 DST · 状态机不写死 UTC 偏移。
    """
    winter = compute_market_status("us", now_utc=_utc(2026, 1, 15, 14))  # 周四 · EST
    summer = compute_market_status("us", now_utc=_utc(2026, 7, 16, 14))  # 周四 · EDT
    assert winter.status == "pre_market"  # 09:00 EST < 09:30 开盘
    assert summer.status == "open"        # 10:00 EDT 盘中
