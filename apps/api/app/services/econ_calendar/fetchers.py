"""P0 两个零 key 官方 JSON 源:Fed calendar.json + BEA release_dates.json(每日刷)。

★解析层纯函数(parse_*·喂 dict 可单测·不碰网络);拉取层 async httpx(照 email/oxapay 范式)。
★实测形状(2026-07-10 亲手 curl,调研 verified):
  - Fed:{"events":[2577 条],"announcement"} · ★文件带 BOM(utf-8-sig)· type=="FOMC" 135 条,
    title 有大小写/前导空格变体("FOMC Meeting"/"FOMC meeting"/" FOMC Minutes")须 normalize;
    会议条目 month="2026-12"+days="9"(两日会的【末日=决议日】,范围如 "17-18" 取末数);
    time="2:00 p.m."(★无时区标注=美东,America/New_York 换算,项目铁律 tz-aware)。
  - BEA:dict{release 名 → {"release_dates":[ISO8601 带时区]}} · 个别重复日期需去重。
🔴 红线:纯日程数据 · 零 key 零凭证 · 与交易逻辑零关联。
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

FED_CALENDAR_URL = "https://www.federalreserve.gov/json/calendar.json"
BEA_RELEASE_DATES_URL = "https://apps.bea.gov/API/signup/release_dates.json"
# 零 key 公共源 · UA 自我标识(公共数据礼仪·非绕反爬)
_UA = {"User-Agent": "MidasTerminal/1.0 (data-schedule; contact via midastrade.asia)"}
_TIMEOUT = 30.0

_ET = ZoneInfo("America/New_York")

# BEA release 名 → (event_type, 中文标题, importance)· ★最小集:GDP + PCE(FOMC 关注的通胀口径)
BEA_RELEASES: dict[str, tuple[str, str, int]] = {
    "Gross Domestic Product": ("us_gdp", "美国GDP", 2),
    "Personal Income and Outlays": ("us_pce", "美国PCE物价", 2),
}


def _parse_fed_time(raw: str) -> tuple[int, int]:
    """'2:00 p.m.' → (14, 0) · 解析不了回退 (14, 0)(FOMC 决议惯例时刻)。"""
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m", raw.strip().lower())
    if not m:
        return (14, 0)
    hour = int(m.group(1)) % 12
    if m.group(3) == "p":
        hour += 12
    return (hour, int(m.group(2) or 0))


def parse_fed_events(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Fed calendar.json → FOMC 利率决议事件列表(纯函数 · 可单测)。

    ★只取 title normalize 后 == "fomc meeting" 的条目(决议 ★3);Minutes/Press Conference/
    Speeches 不进最小集(别过度扩张)。days 可为范围("17-18")→ 取末数 = 两日会末日 = 决议日。
    """
    out: list[dict[str, Any]] = []
    for ev in data.get("events", []):
        title = str(ev.get("title", "")).strip().lower()
        if ev.get("type") != "FOMC" or title != "fomc meeting":
            continue
        month = str(ev.get("month", ""))          # "2026-12"
        days = str(ev.get("days", "")).strip()    # "9" 或 "17-18"
        last_day = days.split("-")[-1].strip()
        if not re.fullmatch(r"\d{4}-\d{2}", month) or not last_day.isdigit():
            continue
        hour, minute = _parse_fed_time(str(ev.get("time", "")))
        try:
            local = datetime(
                int(month[:4]), int(month[5:7]), int(last_day), hour, minute, tzinfo=_ET,
            )
        except ValueError:
            continue
        scheduled = local.astimezone(UTC)
        out.append({
            "event_key": f"fomc-{local:%Y-%m-%d}",
            "event_type": "fomc",
            "title": "FOMC 利率决议",
            "markets": ["us", "crypto", "hk", "cn"],
            "importance": 3,
            "scheduled_at": scheduled,
            "time_confirmed": True,
            "source": "fed_json",
        })
    return out


def parse_bea_events(data: dict[str, Any]) -> list[dict[str, Any]]:
    """BEA release_dates.json → GDP/PCE 事件列表(纯函数 · ISO 带时区 · 去重)。"""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for release_name, (etype, title, importance) in BEA_RELEASES.items():
        entry = data.get(release_name) or {}
        for iso in entry.get("release_dates", []):
            try:
                dt = datetime.fromisoformat(str(iso))
            except ValueError:
                continue
            if dt.tzinfo is None:  # 铁律:绝不留 naive
                dt = dt.replace(tzinfo=UTC)
            key = f"{etype}-{dt.astimezone(UTC):%Y-%m-%d}"
            if key in seen:  # ★个别重复日期(实测)去重
                continue
            seen.add(key)
            out.append({
                "event_key": key,
                "event_type": etype,
                "title": title,
                "markets": ["us", "crypto"] if etype == "us_pce" else ["us"],
                "importance": importance,
                "scheduled_at": dt.astimezone(UTC),
                "time_confirmed": True,
                "source": "bea_json",
            })
    return out


async def fetch_fed_events() -> list[dict[str, Any]]:
    """拉 Fed calendar.json(★BOM → utf-8-sig)→ 解析 FOMC。失败抛给调用方记 fail。"""
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_UA) as client:
        resp = await client.get(FED_CALENDAR_URL)
        resp.raise_for_status()
        import json  # noqa: PLC0415 · 手动 utf-8-sig 解码(resp.json() 会被 BOM 噎住)

        data = json.loads(resp.content.decode("utf-8-sig"))
    events = parse_fed_events(data)
    logger.info("[econ-cal] fed_json 解析 FOMC 决议 %d 条", len(events))
    return events


async def fetch_bea_events() -> list[dict[str, Any]]:
    """拉 BEA release_dates.json → 解析 GDP/PCE。失败抛给调用方记 fail。"""
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_UA) as client:
        resp = await client.get(BEA_RELEASE_DATES_URL)
        resp.raise_for_status()
        import json  # noqa: PLC0415

        data = json.loads(resp.content.decode("utf-8-sig"))
    events = parse_bea_events(data)
    logger.info("[econ-cal] bea_json 解析 %d 条", len(events))
    return events
