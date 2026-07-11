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


def test_bok_seed_kst_and_importance():
    """BOK 8 期议息:10:30:00 KST 极严格(7/16=01:30 UTC)· importance=1 · markets=["kr"]。"""
    by_key = {e["event_key"]: e for e in gen_seed_events()}
    bok = [e for e in by_key.values() if e["event_type"] == "bok"]
    assert len(bok) == 8
    jul = by_key["bok-2026-07-16"]
    assert jul["scheduled_at"] == datetime(2026, 7, 16, 1, 30, tzinfo=UTC)  # 10:30 KST=01:30 UTC
    assert jul["time_confirmed"] is True
    assert all(e["importance"] == 1 and e["markets"] == ["kr"] for e in bok)


def test_rule_and_seed_all_keys_unique_and_tz_aware():
    all_events = gen_rule_and_seed_events(_NOW)
    keys = [e["event_key"] for e in all_events]
    assert len(keys) == len(set(keys))
    assert all(e["scheduled_at"].tzinfo is not None for e in all_events)  # 铁律 tz-aware


def test_parse_kostat_rows_three_indicators():
    """KOSTAT 年表:只取 CPI/就业/产业活动三大指标 · "M.D.(요일)" 日期 · 08:00 KST · 去重。"""
    from app.services.econ_calendar.fetchers import parse_kostat_rows

    rows = [
        ("보도일자", "보도시간", "보도자료명", "담당과"),        # 表头行 → 跳过
        ("8.4.(화)", "08:00", "2026년 7월 소비자물가동향", "물가동향과"),
        ("8.4.(화)", "08:00", "2026년 7월 소비자물가동향", "물가동향과"),  # 重复 → 去重
        ("8.12.(수)", "08:00", "2026년 7월 고용동향", "고용통계과"),
        ("8.31.(월)", "08:00", "2026년 7월 산업활동동향", "산업동향과"),
        ("8.20.(목)", "12:00", "2026년 2/4분기 가축동향조사 결과", "농어업동향과"),  # 非三大指标 → 排除
        ("8.25.(화)", "12:00", "2026년 2분기 청년층 고용동향 부가조사", "고용통계과"),  # 含子串副报告→排除
    ]
    events = parse_kostat_rows(rows, 2026)
    by_key = {e["event_key"]: e for e in events}
    assert sorted(by_key) == [
        "kr_cpi-2026-08-04", "kr_employment-2026-08-12", "kr_ind_activity-2026-08-31",
    ]
    cpi = by_key["kr_cpi-2026-08-04"]
    assert cpi["title"] == "韩国CPI"
    assert cpi["scheduled_at"] == datetime(2026, 8, 3, 23, 0, tzinfo=UTC)  # 08:00 KST=前日23:00 UTC
    assert cpi["importance"] == 1
    assert cpi["markets"] == ["kr"]
    assert cpi["source"] == "kostat"
    assert cpi["time_confirmed"] is True


def test_parse_kostat_date_format_variants():
    """日期格式容错(对抗自审实锤:同一 xlsx 录入不一致)——尾点缺失/内嵌空格都要解析出。"""
    from app.services.econ_calendar.fetchers import parse_kostat_rows

    rows = [
        ("8.31.(월)", "08:00", "2026년 7월 산업활동동향", "산업동향과"),   # 标准
        ("8.31(월)", "08:00", "2026년 7월 소비자물가동향", "물가동향과"),  # 无尾点
        ("9. 8.(화)", "08:00", "2026년 8월 고용동향", "고용통계과"),       # 内嵌空格
    ]
    by_key = {e["event_key"]: e for e in parse_kostat_rows(rows, 2026)}
    assert set(by_key) == {
        "kr_ind_activity-2026-08-31", "kr_cpi-2026-08-31", "kr_employment-2026-09-08",
    }


# ── 日本 統計局 e-Stat XML(★UTF-16)+ BOJ xlsx(实测形状 · 2026-07-11 亲手下载解包)──


def _jp_cpi_xml(os_name: str = "消費者物価指数", class1: str = "全国",
                class2: str = "2026年7月分") -> bytes:
    """最小 e-Stat XML fixture · ★UTF-16 编码(同真源)· 一条 08:30 全国月度发布。"""
    xml = (
        '<?xml version="1.0" encoding="UTF-16" ?>'
        f'<e-stat><os_code name="{os_name}"><class_1 name="{class1}">'
        f'<class_2 name="{class2}"><class_3 name=""><class_4 name=""><class_5 name="">'
        "<release_year>2026</release_year><release_month>8</release_month>"
        "<release_day>21</release_day><release_hour>8</release_hour>"
        "<release_minute>30</release_minute>"
        "</class_5></class_4></class_3></class_2></class_1></os_code></e-stat>"
    )
    return xml.encode("utf-16")


def test_parse_estat_cpi_utf16_and_keep():
    """★UTF-16 解码 + 全国月度 keep + JST→UTF 换算 + 红线(imp=1/markets=jp)。"""
    from app.services.econ_calendar.fetchers import _cpi_keep, parse_estat_xml

    evs = parse_estat_xml(_jp_cpi_xml(), os_name="消費者物価指数",
                          event_type="jp_cpi", title="日本CPI", keep=_cpi_keep)
    assert len(evs) == 1
    e = evs[0]
    assert e["event_key"] == "jp_cpi-2026-08-21"
    assert e["title"] == "日本CPI"
    assert e["markets"] == ["jp"]
    assert e["importance"] == 1
    # 08:30 JST = 前日 23:30 UTC
    assert e["scheduled_at"] == datetime(2026, 8, 20, 23, 30, tzinfo=UTC)


def test_parse_estat_excludes_tokyo_and_wrong_oscode():
    """keep 排除東京都区部速報;os_code 名不符(路径漂移/换文件)→ 返回 [](不误采)。"""
    from app.services.econ_calendar.fetchers import _cpi_keep, parse_estat_xml

    # 東京都区部 → _cpi_keep(class1!="全国") 排除
    tokyo = _jp_cpi_xml(class1="東京都区部（中旬速報値）")
    assert parse_estat_xml(tokyo, os_name="消費者物価指数", event_type="jp_cpi",
                           title="日本CPI", keep=_cpi_keep) == []
    # os_code 名不符 → 空(防换文件静默误采)
    assert parse_estat_xml(_jp_cpi_xml(), os_name="錯誤統計", event_type="jp_cpi",
                           title="日本CPI", keep=_cpi_keep) == []


def test_parse_estat_unemp_basic_only():
    """失業率 keep 只取基本集計(排除詳細集計 14:00 · 非市场事件)。"""
    from app.services.econ_calendar.fetchers import _unemp_keep

    assert _unemp_keep("2026年7月分", "基本集計（2026年7月分）") is True
    assert _unemp_keep("2026年7月分", "詳細集計（2026年4～6月期平均）") is False


def test_parse_boj_tankan_pairs_time_and_date():
    """BOJ 短観:时刻行(08:50)+ 日期行(原生 datetime)同名配对 · 同日去重 · 红线。"""
    from app.services.econ_calendar.fetchers import parse_boj_rows

    rows = [
        ("８．短観", "短観（全国企業短期経済観測調査）／概要及び要旨", "", "08:50:00", "(9月調査)"),
        ("８．短観", "短観（全国企業短期経済観測調査）／概要及び要旨", "", "(四半期)",
         datetime(2026, 10, 1)),  # noqa: DTZ001 · openpyxl naive(同真源)
        ("８．短観", "短観（全国企業短期経済観測調査）／調査全容", "", "08:50:00", "(9月調査)"),
        ("８．短観", "短観（全国企業短期経済観測調査）／調査全容", "", "(四半期)",
         datetime(2026, 10, 2)),  # noqa: DTZ001 · 調査全容不含「概要」→ 不采
    ]
    evs = parse_boj_rows(rows)
    assert [e["event_key"] for e in evs] == ["jp_tankan-2026-10-01"]  # 只采概要 · 全容排除
    e = evs[0]
    assert e["markets"] == ["jp"]
    assert e["importance"] == 1
    assert e["scheduled_at"] == datetime(2026, 10, 1, 8, 50, tzinfo=UTC) - timedelta(hours=9)


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
    # fixture expire_on_commit=False + Core upsert 不刷新 identity map → 显式过期才读到新值
    # (生产无此路径:worker 写 / API 读跨进程)
    db_session.expire_all()
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


@pytest.mark.asyncio
async def test_select_calendar_full_range(db_session) -> None:  # noqa: ANN001
    """日历页查询:今天(CST 零点)起全量,含 importance=1 与今天已过时刻;昨天不列;升序。"""
    from app.services.econ_calendar.store import select_calendar, upsert_events

    now = _NOW  # 2026-07-10 12:00 UTC = 20:00 CST
    rows = [
        {"event_key": "boj-2026-07-31", "event_type": "boj", "title": "日央行BOJ利率决议",
         "markets": ["us", "crypto"], "importance": 1,  # ★1 也要出现在日历页
         "scheduled_at": now + timedelta(days=21), "time_confirmed": False, "source": "seed"},
        {"event_key": "cn_cpi-2026-07-10", "event_type": "cn_cpi", "title": "中国CPI",
         "markets": ["cn", "hk"], "importance": 2,
         # 今天 09:30 CST(已过)→ 仍列(「今天」分组完整性)
         "scheduled_at": now - timedelta(hours=10, minutes=30),
         "time_confirmed": True, "source": "seed"},
        {"event_key": "lpr-2026-06", "event_type": "lpr", "title": "LPR 贷款市场报价利率",
         "markets": ["cn", "hk"], "importance": 2,
         "scheduled_at": now - timedelta(days=18), "time_confirmed": True, "source": "rule"},
        {"event_key": "fomc-2026-07-29", "event_type": "fomc", "title": "FOMC 利率决议",
         "markets": ["us", "crypto", "hk", "cn"], "importance": 3,
         "scheduled_at": now + timedelta(days=19), "time_confirmed": True, "source": "fed_json"},
    ]
    await upsert_events(db_session, rows)
    db_session.expire_all()
    got = await select_calendar(db_session, now=now)
    keys = [e.event_key for e in got]
    assert keys == ["cn_cpi-2026-07-10", "fomc-2026-07-29", "boj-2026-07-31"]  # 升序·无昨天
    assert "lpr-2026-06" not in keys                     # 18 天前 → 不列
    assert any(e.importance == 1 for e in got)           # ★1 展示全(与决策卡口径不同)
