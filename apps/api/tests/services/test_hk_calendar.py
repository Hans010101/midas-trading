"""港股交易时段状态机单测(阶段一 P1-2)· 纯逻辑 · 不打网络。

覆盖:早盘/午盘盘中 / 午间休市 / 待开盘 / 已收盘 / 边界 / 周末 / 节假日 / market 字段。
HKT = UTC+8(全年无 DST · 同 CST 偏移)。
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.market_calendar import compute_market_status

# 2026-05-21 周四 · 港股交易日(不在 HK_MARKET_HOLIDAYS)


def _utc(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def test_hk_open_morning() -> None:
    # 10:00 HKT = 02:00 UTC · 早盘盘中
    s = compute_market_status("hk", now_utc=_utc(2026, 5, 21, 2))
    assert s.status == "open"
    assert s.is_trading_now is True
    assert s.label == "盘中"
    assert s.market == "hk"


def test_hk_lunch_break() -> None:
    # 12:30 HKT = 04:30 UTC · 午间休市(12:00–13:00)
    s = compute_market_status("hk", now_utc=_utc(2026, 5, 21, 4, 30))
    assert s.status == "closed"
    assert s.is_trading_now is False
    assert s.label == "午间休市"


def test_hk_noon_boundary_is_lunch() -> None:
    # 12:00 HKT = 04:00 UTC · 边界:早盘结束 → 午间休市
    s = compute_market_status("hk", now_utc=_utc(2026, 5, 21, 4))
    assert s.label == "午间休市"


def test_hk_afternoon_open() -> None:
    # 14:00 HKT = 06:00 UTC · 午盘盘中
    s = compute_market_status("hk", now_utc=_utc(2026, 5, 21, 6))
    assert s.status == "open"
    assert s.is_trading_now is True


def test_hk_pre_open() -> None:
    # 09:00 HKT = 01:00 UTC · 待开盘
    s = compute_market_status("hk", now_utc=_utc(2026, 5, 21, 1))
    assert s.status == "closed"
    assert s.label == "待开盘"


def test_hk_after_close() -> None:
    # 16:30 HKT = 08:30 UTC · 已收盘(16:00 收盘)
    s = compute_market_status("hk", now_utc=_utc(2026, 5, 21, 8, 30))
    assert s.status == "closed"
    assert s.label == "已收盘"


def test_hk_close_boundary() -> None:
    # 16:00 HKT = 08:00 UTC · 边界:午盘结束 → 已收盘
    s = compute_market_status("hk", now_utc=_utc(2026, 5, 21, 8))
    assert s.status == "closed"
    assert s.label == "已收盘"


def test_hk_weekend() -> None:
    # 2026-05-23 周六 10:00 HKT = 02:00 UTC · 休市
    s = compute_market_status("hk", now_utc=_utc(2026, 5, 23, 2))
    assert s.status == "closed_holiday"
    assert s.label == "休市"


def test_hk_holiday_labour_day() -> None:
    # 2026-05-01 劳动节(周五 · 工作日节假日)10:00 HKT = 02:00 UTC · 休市
    # ★ 专测节假日路径(非周末):证明 HK_MARKET_HOLIDAYS 生效
    s = compute_market_status("hk", now_utc=_utc(2026, 5, 1, 2))
    assert s.status == "closed_holiday"
    assert s.is_trading_now is False
