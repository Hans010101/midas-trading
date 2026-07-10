"""econ_event 数据访问:幂等 upsert + 未来窗口查询 + last-run 保鲜键。

★保鲜口径(调研 §5.5 · 写死):事件 ts 在未来,绝不用 max(scheduled_at) 判 stale
(永远假新鲜)——用「采集任务 last-run 成功时间」(Redis econ:cal:last_success:{source})。
★失效模式良性:源断后存量未来日程仍有效 → 3 天~30 天 stale 只标注不丢弃;
  超 STALE_HARD_DAYS(30 天)才停止注入决策卡(events_usable=False)。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.econ_event import EconEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Redis last-run 成功键(worker 每源成功后写 ISO 时间)
LAST_SUCCESS_KEY = "econ:cal:last_success:{source}"
FRESH_SOURCES = ("fed_json", "bea_json", "rule_seed")   # 全部日更(beat 每日一轮)
STALE_SOFT_DAYS = 3     # 超 3 天没成功 → 监控标 stale(存量日程照用·仅标注)
STALE_HARD_DAYS = 30    # 超 30 天 → 存量日程不再注入决策卡(降级为不可用)


async def upsert_events(session: AsyncSession, events: list[dict[str, Any]]) -> int:
    """按 event_key 幂等 upsert(改期 = 同 key 新时刻 → UPDATE)· 返回写入条数。"""
    if not events:
        return 0
    now = datetime.now(tz=UTC)
    # ★同批同 key 去重(后者胜):同 key 两行进同一条 INSERT..ON CONFLICT 会
    #   CardinalityViolation(PG 禁止一条语句改同行两次)· 上游日历实测出过重复日期
    rows = list({e["event_key"]: {**e, "updated_at": now} for e in events}.values())
    stmt = pg_insert(EconEvent).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[EconEvent.event_key],
        set_={
            "title": stmt.excluded.title,
            "markets": stmt.excluded.markets,
            "importance": stmt.excluded.importance,
            "scheduled_at": stmt.excluded.scheduled_at,
            "time_confirmed": stmt.excluded.time_confirmed,
            "source": stmt.excluded.source,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    await session.execute(stmt)
    await session.commit()
    return len(rows)


async def select_upcoming(
    session: AsyncSession, market: str, *,
    days: int = 7, min_importance: int = 2, now: datetime | None = None, limit: int = 5,
) -> list[EconEvent]:
    """该市场未来 days 天、importance≥min 的事件(按时间升序 · 上限 limit 免噪音)。"""
    now = now or datetime.now(tz=UTC)
    stmt = (
        select(EconEvent)
        .where(
            EconEvent.scheduled_at >= now,
            EconEvent.scheduled_at < now + timedelta(days=days),
            EconEvent.importance >= min_importance,
            EconEvent.markets.contains([market]),
        )
        .order_by(EconEvent.scheduled_at.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def mark_source_success(redis: Any, source: str, now: datetime | None = None) -> None:
    now = now or datetime.now(tz=UTC)
    await redis.set(LAST_SUCCESS_KEY.format(source=source), now.isoformat())


async def read_source_freshness(redis: Any) -> dict[str, datetime | None]:
    """各源 last-run 成功时间(未跑过 = None)。"""
    out: dict[str, datetime | None] = {}
    for s in FRESH_SOURCES:
        raw = await redis.get(LAST_SUCCESS_KEY.format(source=s))
        try:
            out[s] = datetime.fromisoformat(raw) if raw else None
        except ValueError:
            out[s] = None
    return out


def events_usable(freshness: dict[str, datetime | None], now: datetime | None = None) -> bool:
    """★30 天硬阈:任一源 30 天内成功过 → 存量日程可用(良性失效);全部超 30 天/从未跑 → 降级。"""
    now = now or datetime.now(tz=UTC)
    hard = timedelta(days=STALE_HARD_DAYS)
    return any(ts is not None and now - ts < hard for ts in freshness.values())
