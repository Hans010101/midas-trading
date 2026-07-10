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

import io
import logging
import re
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

FED_CALENDAR_URL = "https://www.federalreserve.gov/json/calendar.json"
BEA_RELEASE_DATES_URL = "https://apps.bea.gov/API/signup/release_dates.json"
# KOSTAT(2026 改名 국가데이터처/MODS)官方年度 xlsx · 路径纯约定按年份填充(调研实测 200)
KOSTAT_XLSX_URL = "https://mods.go.kr/ansk/file/schedule_{year}.xlsx"
# 零 key 公共源 · UA 自我标识(公共数据礼仪·非绕反爬)
_UA = {"User-Agent": "MidasTerminal/1.0 (data-schedule; contact via midastrade.asia)"}
_TIMEOUT = 30.0

_ET = ZoneInfo("America/New_York")
_KST = ZoneInfo("Asia/Seoul")

# BEA release 名 → (event_type, 中文标题, importance)· ★最小集:GDP + PCE(FOMC 关注的通胀口径)
BEA_RELEASES: dict[str, tuple[str, str, int]] = {
    "Gross Domestic Product": ("us_gdp", "美国GDP", 2),
    "Personal Income and Outlays": ("us_pce", "美国PCE物价", 2),
}

# KOSTAT 年表 보도자료명(标题)含此韩文子串 → (event_type, 中文标题)· ★最小集:三大月度指标
#   소비자물가동향=CPI · 고용동향=就业 · 산업활동동향=产业活动(2026 xlsx 实测各 12 条,08:00 KST)
KOSTAT_INDICATORS: tuple[tuple[str, str, str], ...] = (
    ("소비자물가동향", "kr_cpi", "韩国CPI"),
    ("고용동향", "kr_employment", "韩国就业动向"),
    ("산업활동동향", "kr_ind_activity", "韩国产业活动"),
)


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


# ── KOSTAT(韩国国家数据处/MODS)年度 xlsx ─────────────────────────────────────
# ★实测形状(2026-07-10 亲手下载解包):单 sheet · 第 3 行表头(보도일자/보도시간/
#   보도자료명/담당과)· 数据从第 4 行 · 日期 "M.D.(요일)" · 时刻 "08:00" 或 datetime.time ·
#   三大月度指标各 12 条 08:00 KST。🔴 韩国全 importance=1 + markets=["kr"](红线不注入决策卡)。


def _parse_kostat_time(raw: Any) -> tuple[int, int]:
    """'08:00' / datetime.time → (8, 0) · 解析不了回退 (8, 0)(KOSTAT 惯例发布时刻)。"""
    if isinstance(raw, time):
        return (raw.hour, raw.minute)
    m = re.match(r"(\d{1,2}):(\d{2})", str(raw).strip())
    return (int(m.group(1)), int(m.group(2))) if m else (8, 0)


def parse_kostat_rows(rows: list[tuple[Any, ...]], year: int) -> list[dict[str, Any]]:
    """KOSTAT 年表行(보도일자, 보도시간, 보도자료명, …)→ 三大指标事件(纯函数 · 可单测)。

    只取标题含 KOSTAT_INDICATORS 韩文子串的行(别过度扩张:全表 199 条,只要 CPI/就业/
    产业活动 36 条)· 日期 "M.D.(요일)" 取 M.D + 传入 year · 韩文星期忽略(用 year+M+D)。
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if len(row) < 3 or not row[0] or not row[2]:
            continue
        date_raw, time_raw, title_raw = str(row[0]).strip(), row[1], str(row[2])
        # ★先匹配指标(表头/其他报告类型静默跳过是对的);再解析日期——这样「三大指标却
        #   日期解析失败」能留 warn(否则静默漏采:同一 xlsx 里日期格式按录入人不一致,
        #   实测有 "8.31(월)" 无尾点 / "9. 8.(화)" 带空格等 8 种变体,对抗自审实锤)。
        # ★结尾匹配(非子串):主报告标题恒为「…M월[및 연간]<指标>동향」,指标名在结尾。
        #   子串匹配会把未来年「청년층 고용동향 부가조사」等含名副报告误采(交叉审 P2);
        #   endswith 收紧 → 真 xlsx 36 条零变化,副报告排除(实测)。
        stripped_title = title_raw.rstrip()
        etype = title = None
        for needle, et, zh in KOSTAT_INDICATORS:
            if stripped_title.endswith(needle):
                etype, title = et, zh
                break
        if etype is None:
            continue
        # 容忍尾点缺失("8.31(월)")与内嵌空格("9. 8.(화)")· "1.14.(수)" 仍匹配
        dm = re.match(r"(\d{1,2})\.\s*(\d{1,2})\.?", date_raw)
        if not dm:
            logger.warning("[econ-cal] kostat 指标行日期无法解析(疑格式漂移·漏采): %r", date_raw)
            continue
        month, day = int(dm.group(1)), int(dm.group(2))
        hour, minute = _parse_kostat_time(time_raw)
        try:
            local = datetime(year, month, day, hour, minute, tzinfo=_KST)
        except ValueError:
            continue
        key = f"{etype}-{year}-{month:02d}-{day:02d}"
        if key in seen:   # 同指标同日去重(年表偶有重复行)
            continue
        seen.add(key)
        out.append({
            "event_key": key,
            "event_type": etype,
            "title": title,
            "markets": ["kr"],      # ★非四市场 → 决策卡永不注入(叠加 importance=1)
            "importance": 1,        # ★韩国恒 1(红线:绝不提 2)
            "scheduled_at": local.astimezone(UTC),
            "time_confirmed": True,
            "source": "kostat",
        })
    return out


def _extract_kostat_rows(content: bytes) -> list[tuple[Any, ...]]:
    """xlsx 字节 → 首个 sheet 全部数据行(轻量:read_only)· openpyxl 已是显式依赖。"""
    import openpyxl  # noqa: PLC0415 · 仅此路径用,惰性 import 避免拖累无关调用

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        ws = wb[wb.sheetnames[0]]
        return [tuple(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


async def fetch_kostat_events(year: int | None = None) -> list[dict[str, Any]]:
    """拉 KOSTAT schedule_{year}.xlsx → 解析三大指标。当年为主(失败抛出记 fail);
    临近年末顺带best-effort拉次年(404 正常,静默忽略)· 失效模式良性:存量 30 天仍有效。
    """
    now_kst = datetime.now(tz=_KST)
    base_year = year or now_kst.year
    events = await _fetch_kostat_year(base_year)          # 主年:失败向上抛
    if year is None and now_kst.month >= 10:              # 10 月起次年表可能已出,顺带拉
        try:
            events += await _fetch_kostat_year(base_year + 1)
        except Exception as exc:  # noqa: BLE001 · 次年 404/未发布正常,不影响主年
            logger.info("[econ-cal] kostat 次年 %d 暂不可用(正常): %s", base_year + 1, exc)
    logger.info("[econ-cal] kostat 解析 %d 条", len(events))
    return events


async def _fetch_kostat_year(year: int) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_UA) as client:
        resp = await client.get(KOSTAT_XLSX_URL.format(year=year))
        resp.raise_for_status()
    return parse_kostat_rows(_extract_kostat_rows(resp.content), year)
