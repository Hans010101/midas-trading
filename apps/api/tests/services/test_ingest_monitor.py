"""采集新鲜度监控单测(刀D)· 纯函数 · 不需要 CH。

重点钉死两个特例阈值防误报回归:funding 8h 结算栅格(非 15min 任务频率)、
kline 日线脉搏 48h(缺今日 bar 超 1 天)。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.ingest_monitor import (
    CRYPTO_SOURCES,
    EQUITY_SOURCES,
    build_ingest_status,
    is_stale,
)

NOW = datetime(2026, 6, 11, 15, 0, tzinfo=UTC)


def test_is_stale_basic() -> None:
    assert is_stale(NOW - timedelta(seconds=100), 180, NOW) is False  # 新鲜
    assert is_stale(NOW - timedelta(seconds=181), 180, NOW) is True  # 过期
    assert is_stale(NOW - timedelta(seconds=180), 180, NOW) is False  # 恰好等于阈值 → 不算
    assert is_stale(None, 180, NOW) is True  # 从未采 = stale


def test_is_stale_naive_ts_treated_as_utc() -> None:
    naive = (NOW - timedelta(hours=2)).replace(tzinfo=None)
    assert is_stale(naive, 3600, NOW) is True


def _threshold(source: str) -> int:
    return next(s.expected_max_age_seconds for s in CRYPTO_SOURCES if s.source == source)


def test_funding_8h_grid_no_false_alarm() -> None:
    """★ 特例:funding 任务 15min 跑但数据 8h 结算栅格 → age 6h 绝不能误报。"""
    assert _threshold("funding_rate") == 86400  # 8h 栅格 ×3 = 24h(非 15min×3)
    six_hours_old = NOW - timedelta(hours=6)
    assert is_stale(six_hours_old, _threshold("funding_rate"), NOW) is False
    assert is_stale(NOW - timedelta(hours=25), _threshold("funding_rate"), NOW) is True


def test_kline_daily_pulse_no_false_alarm() -> None:
    """★ 特例:日线 bar ts=当日 00:00 · 正常 age 峰值 ~24h → 48h 内绝不能误报。"""
    assert _threshold("kline_btc_perp_1d") == 172800  # 48h =「超过 1 天没今日 bar」
    # 午夜前夕:今日 bar age ≈ 23h59m → 新鲜
    assert is_stale(NOW - timedelta(hours=23, minutes=59), 172800, NOW) is False
    # 缺今日 bar 但有昨日(age ~39h)→ 仍在缓冲内不报
    assert is_stale(NOW - timedelta(hours=39), 172800, NOW) is False
    # 连昨日 bar 都缺(age 49h)→ 红(11 天事故在此一眼暴露)
    assert is_stale(NOW - timedelta(hours=49), 172800, NOW) is True


def test_regular_thresholds() -> None:
    assert _threshold("premium_index") == 180  # 1min ×3
    assert _threshold("ticker_24h") == 1800  # 10min ×3
    assert _threshold("open_interest") == 900  # 5min ×3
    assert _threshold("long_short") == 2700  # 15min ×3
    assert _threshold("market_overview") == 5400  # 30min ×3


def test_build_ingest_status_shapes_and_any_stale() -> None:
    """组装:加密判 stale + 股票裸报 + any_stale 聚合。"""
    latest_map: dict[str, datetime | None] = {
        s.source: NOW - timedelta(seconds=10) for s in CRYPTO_SOURCES
    }
    latest_map["premium_index"] = NOW - timedelta(hours=1)  # 唯一过期源
    latest_map.update({s.source: NOW - timedelta(days=2) for s in EQUITY_SOURCES})

    crypto_items, equity_items, any_stale = build_ingest_status(latest_map, NOW)

    assert any_stale is True
    by_src = {i.source: i for i in crypto_items}
    assert by_src["premium_index"].stale is True
    assert by_src["ticker_24h"].stale is False
    assert len(equity_items) == len(EQUITY_SOURCES)
    # 股票项无 stale 字段(裸报)· 周末滞后 2 天不触发任何告警
    assert not hasattr(equity_items[0], "stale")


def test_build_ingest_status_never_ingested() -> None:
    """从未采(表空 → None)→ stale=true · age=None。"""
    crypto_items, _, any_stale = build_ingest_status({}, NOW)
    assert any_stale is True
    assert all(i.stale for i in crypto_items)
    assert all(i.age_seconds is None for i in crypto_items)
