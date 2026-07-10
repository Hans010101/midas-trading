"""纯规则生成器 + 年度策展种子(零网络 · 全部纯函数 · 本地可测)。

规则(调研实测验证):
- LPR:每月 20 日 9:15 CST 公布,周末顺延到下周一(调研实测 2026-06-20 周六→6-22 周一)。
  ★P0 只做周末顺延;2026 下半年 20 日均不落法定假期(逐月核过),节假日表 P1 接。
- 中国制造业 PMI:每月最后一个日历日 9:30 CST(统计局年表规则 · 周末照发 · 春节月顺延;
  2026 H2 无春节干扰,规则=年表)。
- 社融/M2:官方零日程(实测)→「每月 9-15 日窗口」占位,锚 9 日 09:00 CST,time_confirmed=False。
- 美国非农:★BLS 官方 2026 年表在全部合法通道被 Akamai 挡(bls.gov 403 实测多次)——
  绝不编造官方日期 → P0 用「每月第一个周五 8:30 ET」惯例占位,time_confirmed=False,
  标题注明以官方为准;P1 按调研双保险(VPS UA 拉 bls.ics / Hans 提供年表)替换为确认日期。
  美国 CPI/PPI 无稳定惯例规则 → P0 缺席,P1 同渠道补。

年度种子(一年一策·官方公布后人工策展·来源注明):
- 统计局 2026 年表(stats.gov.cn/sj/fbrc/bnxxfb/ · 2026-07-10 策展):CPI/PPI 精确到日 9:30、
  季度 GDP 发布会 10:00。官方注明「发布日期为初步计划,届时可能有所调整」。
- ECB 2026H2+2027 议息决议日(ecb.europa.eu 官方日历 · 提前约 2.5 年 · 决议 14:15 CET/CEST,
  用 Europe/Berlin 换算自动处理夏令时)。
- BOJ 2026 全年 8 次 MPM(boj.or.jp 官方 · 决议=会议末日 · 无固定钟点 → 锚 12:00 JST,
  time_confirmed=False)。
- BOK 2026 全年 8 次 MPB 议息(bok.or.kr 官方年表 · 前一年 10 月末公布 · 决议声明
  10:30:00 KST 极严格,韩英双站 RSS 20+ 次实证)· 韩国全部事件 importance=1(★保守:
  不注入决策卡 · 见 docs/research/kr-econ-calendar-sources.md)。

🔴 红线:纯日程 · 标题白名单零方向词(test_econ_redline 机器钉死)· 零交易逻辑。
🔴 韩国红线(写死):importance 恒 1 + markets=["kr"](非 cn/us/crypto/hk)→ 双重
   保证决策卡永不注入韩国;绝不因「想让韩国在★2+下显示」提到 2(会穿透注入,red-line)。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

_CST = ZoneInfo("Asia/Shanghai")
_ET = ZoneInfo("America/New_York")
_CET = ZoneInfo("Europe/Berlin")   # ECB 决议 14:15 当地(自动处理 CET/CEST)
_JST = ZoneInfo("Asia/Tokyo")
_KST = ZoneInfo("Asia/Seoul")

# 韩国事件专用市场标签:非 Midas 四市场(cn/us/crypto/hk)→ select_upcoming 永不命中,
# 叠加 importance=1 双重焊死「决策卡不注入韩国」(test_econ_redline 机器钉死)。
KR_MARKETS = ["kr"]

# 规则生成的前瞻月数(日程提前数月已知 · 6 个月够决策卡 7 天窗滚动使用)
RULE_HORIZON_MONTHS = 6


def _month_iter(start: date, months: int) -> list[tuple[int, int]]:
    """从 start 所在月起,连续 months 个 (year, month)。"""
    out = []
    y, m = start.year, start.month
    for _ in range(months):
        out.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _last_day_of_month(year: int, month: int) -> int:
    nxt = date(year, month, 28) + timedelta(days=4)
    return (nxt.replace(day=1) - timedelta(days=1)).day


def gen_lpr_events(now: datetime) -> list[dict[str, Any]]:
    """LPR:每月 20 日 9:15 CST · 周末顺延下周一(纯规则 · 无限远可推)。"""
    out = []
    for y, m in _month_iter(now.astimezone(_CST).date(), RULE_HORIZON_MONTHS):
        d = date(y, m, 20)
        while d.weekday() >= 5:  # 周六=5/周日=6 → 顺延
            d += timedelta(days=1)
        local = datetime(d.year, d.month, d.day, 9, 15, tzinfo=_CST)
        out.append({
            "event_key": f"lpr-{y}-{m:02d}",
            "event_type": "lpr",
            "title": "LPR 贷款市场报价利率",
            "markets": ["cn", "hk"],
            "importance": 2,
            "scheduled_at": local.astimezone(UTC),
            "time_confirmed": True,
            "source": "rule",
        })
    return out


def gen_cn_pmi_events(now: datetime) -> list[dict[str, Any]]:
    """中国制造业 PMI:每月最后一个日历日 9:30 CST(周末照发 · 2026H2 无春节干扰)。"""
    out = []
    for y, m in _month_iter(now.astimezone(_CST).date(), RULE_HORIZON_MONTHS):
        d = _last_day_of_month(y, m)
        local = datetime(y, m, d, 9, 30, tzinfo=_CST)
        out.append({
            "event_key": f"cn_pmi-{y}-{m:02d}",
            "event_type": "cn_pmi",
            "title": "中国制造业PMI",
            "markets": ["cn", "hk"],
            "importance": 2,
            "scheduled_at": local.astimezone(UTC),
            "time_confirmed": True,
            "source": "rule",
        })
    return out


def gen_cn_credit_window_events(now: datetime) -> list[dict[str, Any]]:
    """社融/M2:官方无预告 → 每月 9-15 日窗口占位(锚 9 日 09:00 CST · 待定)。"""
    out = []
    for y, m in _month_iter(now.astimezone(_CST).date(), RULE_HORIZON_MONTHS):
        local = datetime(y, m, 9, 9, 0, tzinfo=_CST)
        out.append({
            "event_key": f"cn_credit-{y}-{m:02d}",
            "event_type": "cn_credit",
            "title": "中国社融/M2(每月9-15日窗口·具体日待定)",
            "markets": ["cn"],
            "importance": 1,
            "scheduled_at": local.astimezone(UTC),
            "time_confirmed": False,
            "source": "rule",
        })
    return out


def gen_nfp_placeholder_events(now: datetime) -> list[dict[str, Any]]:
    """美国非农:惯例「每月第一个周五 8:30 ET」占位(★官方年表 P1 替换 · 以官方为准)。"""
    out = []
    for y, m in _month_iter(now.astimezone(_ET).date(), RULE_HORIZON_MONTHS):
        d = date(y, m, 1)
        while d.weekday() != 4:  # 周五
            d += timedelta(days=1)
        local = datetime(d.year, d.month, d.day, 8, 30, tzinfo=_ET)
        out.append({
            "event_key": f"nfp-{y}-{m:02d}",
            "event_type": "nfp",
            "title": "美国非农就业报告(惯例日·以官方为准)",
            "markets": ["us", "crypto"],
            "importance": 3,
            "scheduled_at": local.astimezone(UTC),
            "time_confirmed": False,
            "source": "rule",
        })
    return out


# ── 年度策展种子(官方公布 → 人工策展 · 来源与策展日期见模块头)──────────────────

# 统计局 2026:CPI/PPI 同日 9:30(官方年表 · 初步计划可能调整)
_CN_CPI_PPI_2026: tuple[tuple[int, int, int], ...] = (
    (2026, 1, 9), (2026, 2, 11), (2026, 3, 9), (2026, 4, 10), (2026, 5, 11),
    (2026, 6, 10), (2026, 7, 9), (2026, 8, 9), (2026, 9, 9), (2026, 10, 14),
    (2026, 11, 9), (2026, 12, 9),
)
# 统计局 2026:季度 GDP · 国民经济运行情况发布会 10:00
_CN_GDP_2026: tuple[tuple[int, int, int], ...] = (
    (2026, 1, 19), (2026, 4, 16), (2026, 7, 15), (2026, 10, 19),
)
# ECB 货币政策决议日(14:15 Europe/Berlin·夏令时自动)· 2026H2(1-6 月已过不录)+ 2027 全年
_ECB_DECISIONS: tuple[tuple[int, int, int], ...] = (
    (2026, 7, 23), (2026, 9, 10), (2026, 10, 29), (2026, 12, 17),
    (2027, 2, 4), (2027, 3, 18), (2027, 4, 29), (2027, 6, 10),
    (2027, 7, 22), (2027, 9, 9), (2027, 10, 28), (2027, 12, 16),
)
# BOJ 2026 全年 8 次 MPM 决议日(=会议末日 · 无固定钟点 → 12:00 JST 占位)
_BOJ_DECISIONS_2026: tuple[tuple[int, int, int], ...] = (
    (2026, 1, 23), (2026, 3, 19), (2026, 4, 28), (2026, 6, 16),
    (2026, 7, 31), (2026, 9, 18), (2026, 10, 30), (2026, 12, 18),
)
# BOK 2026 全年 8 次 MPB 议息决议日(bok.or.kr 官方年表 · 决议声明 10:30:00 KST 极严格)
_BOK_DECISIONS_2026: tuple[tuple[int, int, int], ...] = (
    (2026, 1, 15), (2026, 2, 26), (2026, 4, 10), (2026, 5, 28),
    (2026, 7, 16), (2026, 8, 27), (2026, 10, 22), (2026, 11, 26),
)


def gen_seed_events() -> list[dict[str, Any]]:
    """全部年度种子 → 事件列表(纯函数 · 与 now 无关 · upsert 幂等靠 event_key)。"""
    out: list[dict[str, Any]] = []
    for y, m, d in _CN_CPI_PPI_2026:
        local = datetime(y, m, d, 9, 30, tzinfo=_CST)
        for etype, title in (("cn_cpi", "中国CPI"), ("cn_ppi", "中国PPI")):
            out.append({
                "event_key": f"{etype}-{y}-{m:02d}-{d:02d}",
                "event_type": etype,
                "title": title,
                "markets": ["cn", "hk"],
                "importance": 2,
                "scheduled_at": local.astimezone(UTC),
                "time_confirmed": True,
                "source": "seed",
            })
    for y, m, d in _CN_GDP_2026:
        local = datetime(y, m, d, 10, 0, tzinfo=_CST)
        out.append({
            "event_key": f"cn_gdp-{y}-{m:02d}-{d:02d}",
            "event_type": "cn_gdp",
            "title": "中国季度GDP·国民经济运行发布会",
            "markets": ["cn", "hk"],
            "importance": 3,
            "scheduled_at": local.astimezone(UTC),
            "time_confirmed": True,
            "source": "seed",
        })
    for y, m, d in _ECB_DECISIONS:
        local = datetime(y, m, d, 14, 15, tzinfo=_CET)
        out.append({
            "event_key": f"ecb-{y}-{m:02d}-{d:02d}",
            "event_type": "ecb",
            "title": "欧央行ECB利率决议",
            "markets": ["us"],
            "importance": 1,
            "scheduled_at": local.astimezone(UTC),
            "time_confirmed": True,
            "source": "seed",
        })
    for y, m, d in _BOJ_DECISIONS_2026:
        local = datetime(y, m, d, 12, 0, tzinfo=_JST)
        out.append({
            "event_key": f"boj-{y}-{m:02d}-{d:02d}",
            "event_type": "boj",
            "title": "日央行BOJ利率决议",
            "markets": ["us", "crypto"],
            "importance": 1,
            "scheduled_at": local.astimezone(UTC),
            "time_confirmed": False,  # 决议无固定钟点(会议末日中午前后)
            "source": "seed",
        })
    for y, m, d in _BOK_DECISIONS_2026:
        local = datetime(y, m, d, 10, 30, tzinfo=_KST)
        out.append({
            "event_key": f"bok-{y}-{m:02d}-{d:02d}",
            "event_type": "bok",
            "title": "韩国央行BOK利率决议",
            "markets": KR_MARKETS,             # ★["kr"] · 非四市场 → 决策卡永不注入
            "importance": 1,                   # ★恒 1(红线:绝不提 2)
            "scheduled_at": local.astimezone(UTC),
            "time_confirmed": True,            # 决议声明 10:30:00 KST 极严格(RSS 实证)
            "source": "seed",
        })
    return out


def gen_rule_and_seed_events(now: datetime) -> list[dict[str, Any]]:
    """规则 + 种子全量(worker 每日调 · upsert 幂等)。"""
    return [
        *gen_lpr_events(now),
        *gen_cn_pmi_events(now),
        *gen_cn_credit_window_events(now),
        *gen_nfp_placeholder_events(now),
        *gen_seed_events(),
    ]
