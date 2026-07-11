"""硬编码年度种子枯竭告警(逻辑层 · 可单测)· worker 任务是薄壳(tasks/seed_depletion.py)。

查每个种子 event_type 的 max(scheduled_at),最远日期距今 < 阈值(默认 3 月)→ TG 提醒 admin
补下一年数组。把「静默枯竭」变成「有提前量的例行维护」。

★口径澄清(关键):这里 max(scheduled_at) 是【合法且正确】用途——问「硬编码数组还剩多远
  到头」。与 ingest_monitor 新鲜度的 last-run 口径【正交并存、不冲突】:last-run 判「源还
  活着吗」(种子每日 upsert 成功=永远新鲜),本模块判「硬编码数据快用完了吗」(数据有限会
  枯竭,只 max(ts) 能捕捉)。★绝不用本模块的 max(ts) 替换/干扰 ingest_monitor 的 last-run。
★只查 source='seed'(硬编码:中国CPI/PPI/GDP + BOJ/BOK/BoE/ECB 议息)· 抓取/滚动源
  (fed_json/bea_json/kostat/jp_estat/boj_xlsx/dsbb/rule)不在范围(自动滚动·永在未来·纳入永假告警)。
🔴 纯监控:只读 max(ts) + 发 TG。不碰事件数据/种子数组/注入逻辑/importance/markets。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.econ_event import EconEvent
from app.services.notifications import telegram

logger = logging.getLogger(__name__)

SEED_ALERT_MONTHS = 3.0            # 最远日期 < 3 月 → 告警(留足人工补种子提前量)
DEBOUNCE_TTL_SEC = 7 * 24 * 3600  # 同 event_type 7 天只告一次(日频 beat 防刷屏)
_ALERT_KEY = "monitor:seed_depletion:sent:{etype}"
_MONTH_DAYS = 30.0

# event_type → (中文名, rules.py 数组名)· 告警可读用 · 未列出的 seed 也会告警(回退 etype)
SEED_INFO: dict[str, tuple[str, str]] = {
    "cn_cpi": ("中国CPI", "_CN_CPI_PPI_YYYY"),
    "cn_ppi": ("中国PPI", "_CN_CPI_PPI_YYYY"),
    "cn_gdp": ("中国季度GDP", "_CN_GDP_YYYY"),
    "boj": ("日央行BOJ议息", "_BOJ_DECISIONS_YYYY"),
    "bok": ("韩国央行BOK议息", "_BOK_DECISIONS_YYYY"),
    "gb_boe": ("英国央行BoE议息", "_BOE_DECISIONS_YYYY"),
    "ecb": ("欧央行ECB议息", "_ECB_DECISIONS"),
}


def months_left(latest: datetime, now: datetime) -> float:
    return (latest - now).days / _MONTH_DAYS


def depleting(
    seeds: list[tuple[str, datetime]], now: datetime, months: float = SEED_ALERT_MONTHS,
) -> list[dict[str, Any]]:
    """纯函数:筛出最远日期距今 < months 的种子(可单测 · 与 DB/网络无关)。"""
    out: list[dict[str, Any]] = []
    for etype, latest in seeds:
        lt = latest if latest.tzinfo is not None else latest.replace(tzinfo=UTC)
        left = months_left(lt, now)
        if left < months:
            out.append({"event_type": etype, "latest": lt, "months_left": round(left, 1)})
    return out


async def seed_max_dates(session: AsyncSession) -> list[tuple[str, datetime]]:
    """每个硬编码种子 event_type 的 max(scheduled_at)(★仅 source='seed' · 排除滚动源)。"""
    stmt = (
        select(EconEvent.event_type, func.max(EconEvent.scheduled_at))
        .where(EconEvent.source == "seed")
        .group_by(EconEvent.event_type)
    )
    rows = (await session.execute(stmt)).all()
    return [(et, mx) for et, mx in rows if mx is not None]


async def maybe_alert(item: dict[str, Any], redis: Any) -> bool:
    """快枯竭 → TG 告警 admin(按 event_type 去抖 7 天)· TG 未配置只 log 不阻塞。"""
    etype = item["event_type"]
    if not settings.tg_bot_token or not settings.admin_tg_chat_id:
        logger.warning("种子 %s 快枯竭但 admin TG 未配置(tg_bot_token/admin_tg_chat_id 空)", etype)
        return False
    got = await redis.set(_ALERT_KEY.format(etype=etype), "1", ex=DEBOUNCE_TTL_SEC, nx=True)
    if not got:
        logger.info("种子枯竭告警去抖命中(7 天内已发)· 跳过:%s", etype)
        return False
    label, array_name = SEED_INFO.get(etype, (etype, "对应 _*_DECISIONS/_CN_* 数组"))
    latest: datetime = item["latest"]
    text = (
        "⚠️ *种子枯竭告警* · 点金 Midas\n"
        f"硬编码年度种子 `{etype}`({label})最远日期 *{latest:%Y-%m-%d}*,"
        f"剩余约 *{item['months_left']} 个月*(< {SEED_ALERT_MONTHS:.0f} 月阈值)。\n"
        f"请补下一年数组到 `apps/api/app/services/econ_calendar/rules.py` 的 `{array_name}`。"
    )
    try:
        await telegram.send(settings.tg_bot_token, settings.admin_tg_chat_id, text)
        logger.warning("已发种子枯竭告警到 admin TG:%s(%s)", etype, latest.date())
        return True
    except Exception:
        logger.exception("发种子枯竭告警到 admin TG 失败:%s", etype)
        return False


async def run_check(
    session: AsyncSession, redis: Any, *,
    now: datetime | None = None, months: float = SEED_ALERT_MONTHS,
) -> dict[str, Any]:
    """编排:查种子 max(ts) → 筛快枯竭 → 逐个告警(去抖)· 返回可序列化摘要。"""
    now = now or datetime.now(tz=UTC)
    seeds = await seed_max_dates(session)
    out: list[dict[str, Any]] = []
    for item in depleting(seeds, now, months):
        alerted = await maybe_alert(item, redis)
        out.append({
            "event_type": item["event_type"],
            "latest": item["latest"].isoformat(),
            "months_left": item["months_left"],
            "alerted": alerted,
        })
    logger.info("[seed-depletion] 查 %d 种子 · 快枯竭 %d 条", len(seeds), len(out))
    return {"ok": True, "checked": len(seeds), "depleting": out}
