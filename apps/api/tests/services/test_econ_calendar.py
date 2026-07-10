"""事件日程层 P0:规则生成器 / 源解析器(fixture 纯函数)/ 存储 upsert / job 新鲜度。

规则与解析全纯函数(无网络无 DB · 本地秒跑);store 两测需 PG(CI 跑)。
红线专项见 test_econ_redline.py。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.econ_calendar.fetchers import parse_bea_events, parse_fed_events
from app.services.econ_calendar.rules import (
    gen_cn_credit_window_events,
    gen_cn_pmi_events,
    gen_lpr_events,
    gen_nfp_placeholder_events,
    gen_rule_and_seed_events,
    gen_seed_events,
)
from app.services.econ_calendar.store import events_usable
from app.services.ingest_monitor import build_econ_job_status

_CST = ZoneInfo("Asia/Shanghai")
_NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


# ── 规则生成器 ──────────────────────────────────────────────────────────


def test_lpr_weekend_defer():
    """LPR 每月 20 日 9:15 CST · 周末顺延下周一(2026-09-20 周日→9-21 · 12-20 周日→12-21)。"""
    events = {e["event_key"]: e for e in gen_lpr_events(_NOW)}
    sep = events["lpr-2026-09"]["scheduled_at"].astimezone(_CST)
    assert (sep.month, sep.day, sep.hour, sep.minute) == (9, 21, 9, 15)  # 周日顺延
    dec = events["lpr-2026-12"]["scheduled_at"].astimezone(_CST)
    assert (dec.month, dec.day) == (12, 21)  # 周日顺延
    jul = events["lpr-2026-07"]["scheduled_at"].astimezone(_CST)
    assert (jul.month, jul.day) == (7, 20)  # 周一不顺延


def test_cn_pmi_last_calendar_day():
    """PMI 每月最后一个日历日 9:30 CST(周末照发)。"""
    events = {e["event_key"]: e for e in gen_cn_pmi_events(_NOW)}
    sep = events["cn_pmi-2026-09"]["scheduled_at"].astimezone(_CST)
    assert (sep.month, sep.day, sep.hour, sep.minute) == (9, 30, 9, 30)
    nov = events["cn_pmi-2026-11"]["scheduled_at"].astimezone(_CST)
    assert (nov.month, nov.day) == (11, 30)


def test_credit_window_and_nfp_are_unconfirmed_placeholders():
    """社融窗口 + 非农惯例占位:time_confirmed=False(展示层标待定/以官方为准)。"""
    credit = gen_cn_credit_window_events(_NOW)
    assert all(e["time_confirmed"] is False for e in credit)
    assert all("窗口" in e["title"] for e in credit)
    nfp = {e["event_key"]: e for e in gen_nfp_placeholder_events(_NOW)}
    assert all(e["time_confirmed"] is False for e in nfp.values())
    assert all("以官方为准" in e["title"] for e in nfp.values())
    # 2026-08 第一个周五 = 8/7 · 8:30 ET
    aug = nfp["nfp-2026-08"]["scheduled_at"].astimezone(ZoneInfo("America/New_York"))
    assert (aug.month, aug.day, aug.hour, aug.minute) == (8, 7, 8, 30)


def test_seed_events_tz_and_keys():
    """种子:统计局 CST / ECB 夏令时(7/23 14:15 CEST=12:15 UTC)/ BOJ 待定钟点 · key 全局唯一。"""
    seeds = gen_seed_events()
    by_key = {e["event_key"]: e for e in seeds}
    assert len(by_key) == len(seeds)  # key 唯一
    gdp = by_key["cn_gdp-2026-07-15"]["scheduled_at"].astimezone(_CST)
    assert (gdp.month, gdp.day, gdp.hour, gdp.minute) == (7, 15, 10, 0)
    ecb = by_key["ecb-2026-07-23"]["scheduled_at"].astimezone(UTC)
    assert (ecb.hour, ecb.minute) == (12, 15)  # 14:15 CEST(夏令时)= 12:15 UTC
    assert by_key["boj-2026-07-31"]["time_confirmed"] is False


def test_rule_and_seed_all_keys_unique_and_tz_aware():
    all_events = gen_rule_and_seed_events(_NOW)
    keys = [e["event_key"] for e in all_events]
    assert len(keys) == len(set(keys))
    assert all(e["scheduled_at"].tzinfo is not None for e in all_events)  # 铁律 tz-aware


# ── 源解析器(实测形状 fixture · 2026-07-10 亲手 curl)───────────────────────


def test_parse_fed_events_variants_and_range():
    """Fed:title 大小写/前导空格变体 · days 范围取末日=决议日 · ET→UTC · 只取 Meeting。"""
    data = {"events": [
        {"title": "FOMC Meeting", "type": "FOMC", "month": "2026-12", "days": "9",
         "time": "2:00 p.m."},
        {"title": "FOMC meeting", "type": "FOMC", "month": "2026-09", "days": "15-16",
         "time": "2:00 p.m."},                                     # 小写变体 + 范围
        {"title": " FOMC Minutes", "type": "FOMC", "month": "2026-11", "days": "18",
         "time": "2:00 p.m."},                                     # Minutes 不进最小集
        {"title": "Speech - Governor X", "type": "Speeches", "month": "2026-10",
         "days": "1", "time": "7:00 p.m."},                        # 非 FOMC type 过滤
    ]}
    events = parse_fed_events(data)
    keys = {e["event_key"] for e in events}
    assert keys == {"fomc-2026-12-09", "fomc-2026-09-16"}          # 范围取末日 16
    dec = next(e for e in events if e["event_key"] == "fomc-2026-12-09")
    assert dec["scheduled_at"] == datetime(2026, 12, 9, 19, 0, tzinfo=UTC)  # 14:00 EST=19:00 UTC
    assert dec["importance"] == 3
    assert set(dec["markets"]) == {"us", "crypto", "hk", "cn"}


def test_parse_bea_events_dedup_and_tz():
    """BEA:ISO 带时区照抄 · 重复日期去重 · 只取注册的 release(GDP/PCE)。"""
    data = {
        "Gross Domestic Product": {"release_dates": [
            "2026-07-30T12:30:00+00:00", "2026-07-30T12:30:00+00:00",  # 重复 → 去重
        ]},
        "Personal Income and Outlays": {"release_dates": ["2026-08-28T12:30:00+00:00"]},
        "Travel and Tourism Satellite Account": {"release_dates": ["2026-09-01T12:30:00+00:00"]},
    }
    events = parse_bea_events(data)
    keys = sorted(e["event_key"] for e in events)
    assert keys == ["us_gdp-2026-07-30", "us_pce-2026-08-28"]      # 去重 + 未注册 release 不进
    pce = next(e for e in events if e["event_type"] == "us_pce")
    assert pce["scheduled_at"].tzinfo is not None
    assert "crypto" in pce["markets"]                               # PCE=通胀口径 · crypto 关注


# ── 存储(DB · CI 跑)────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_idempotent_and_reschedule(db_session) -> None:  # noqa: ANN001
    """同 key 重复 upsert 不增行;改期(同 key 新时刻)= UPDATE(调研:日程会因停摆等改期)。"""
    from app.services.econ_calendar.store import select_upcoming, upsert_events

    now = _NOW
    ev = {
        "event_key": "fomc-2026-07-29", "event_type": "fomc", "title": "FOMC 利率决议",
        "markets": ["us", "crypto"], "importance": 3,
        "scheduled_at": now + timedelta(days=3), "time_confirmed": True, "source": "fed_json",
    }
    assert await upsert_events(db_session, [ev]) == 1
    assert await upsert_events(db_session, [ev]) == 1              # 幂等不炸
    got = await select_upcoming(db_session, "crypto", days=7, now=now)
    assert [e.event_key for e in got] == ["fomc-2026-07-29"]
    # 改期 +1 天 → 同 key UPDATE
    ev2 = {**ev, "scheduled_at": now + timedelta(days=4)}
    await upsert_events(db_session, [ev2])
    got2 = await select_upcoming(db_session, "crypto", days=7, now=now)
    assert len(got2) == 1
    assert got2[0].scheduled_at == now + timedelta(days=4)


@pytest.mark.asyncio
async def test_select_upcoming_filters(db_session) -> None:  # noqa: ANN001
    """窗口(7天)/ 市场(JSONB 包含)/ 重要度(≥2)三过滤 + 时间升序 + limit。"""
    from app.services.econ_calendar.store import select_upcoming, upsert_events

    now = _NOW
    rows = [
        {"event_key": "cn_gdp-2026-07-15", "event_type": "cn_gdp", "title": "中国季度GDP发布会",
         "markets": ["cn", "hk"], "importance": 3,
         "scheduled_at": now + timedelta(days=4), "time_confirmed": True, "source": "seed"},
        {"event_key": "cn_credit-2026-08", "event_type": "cn_credit", "title": "社融窗口",
         "markets": ["cn"], "importance": 1,                        # 重要度 1 → 滤掉
         "scheduled_at": now + timedelta(days=5), "time_confirmed": False, "source": "rule"},
        {"event_key": "fomc-2026-07-29", "event_type": "fomc", "title": "FOMC 利率决议",
         "markets": ["us", "crypto"], "importance": 3,              # 市场不含 cn → 滤掉
         "scheduled_at": now + timedelta(days=2), "time_confirmed": True, "source": "fed_json"},
        {"event_key": "cn_cpi-2026-08-09", "event_type": "cn_cpi", "title": "中国CPI",
         "markets": ["cn", "hk"], "importance": 2,                  # 30 天后 → 窗口外
         "scheduled_at": now + timedelta(days=30), "time_confirmed": True, "source": "seed"},
    ]
    await upsert_events(db_session, rows)
    got = await select_upcoming(db_session, "cn", days=7, min_importance=2, now=now)
    assert [e.event_key for e in got] == ["cn_gdp-2026-07-15"]


# ── 保鲜(★job last-run 口径 · 绝非 max(事件ts))────────────────────────────


def test_events_usable_30d_hard_threshold():
    """30 天硬阈:任一源 30 天内成功 → 可用(良性失效);全部超期/从未跑 → 降级。"""
    now = _NOW
    assert events_usable({"fed_json": now - timedelta(days=2), "bea_json": None,
                          "rule_seed": None}, now) is True
    assert events_usable({"fed_json": now - timedelta(days=31),
                          "bea_json": now - timedelta(days=40), "rule_seed": None}, now) is False
    assert events_usable({"fed_json": None, "bea_json": None, "rule_seed": None}, now) is False


def test_build_econ_job_status_stale_3d():
    """job 新鲜度:>3 天没成功 → stale(存量日程仍有效仅标注)· 从未跑 → stale。"""
    now = _NOW
    items, any_stale = build_econ_job_status({
        "fed_json": now - timedelta(hours=20),
        "bea_json": now - timedelta(days=4),
        "rule_seed": None,
    }, now)
    by = {i.source: i for i in items}
    assert by["fed_json"].stale is False
    assert by["bea_json"].stale is True
    assert by["rule_seed"].stale is True
    assert by["rule_seed"].last_success is None
    assert any_stale is True
