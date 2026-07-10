"""财经日历(PR-A)· 公开只读 · 零 LLM 零解读。

🔴 红线(机器验证 test_econ_calendar_page):本路由只做「库字段直出 + 保鲜元信息」,
不 import 任何 AI/LLM 模块,不产生任何对事件的解读文案(展示模板在前端,同样纯静态)。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.schemas.crypto import EconJobStatus
from app.schemas.econ_calendar import EconCalendarResponse, EconEventOut
from app.services.econ_calendar.store import read_source_freshness, select_calendar
from app.services.ingest_monitor import build_econ_job_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/econ", tags=["econ"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get(
    "/calendar",
    response_model=EconCalendarResponse,
    summary="财经日历:今天起全部宏观事件日程(公开只读 · 纯客观事实)",
    description=(
        "P0 存量全部事件(含 importance=1 的 ECB/BOJ/社融窗口——决策卡保守不注入,"
        "日历页用户主动查展示全)。市场/重要度筛选在前端做。"
        "updated_at=采集任务 last-run 成功时间(保鲜口径,非 max(事件ts))。"
    ),
)
async def get_econ_calendar(db: DbDep) -> EconCalendarResponse:
    events = await select_calendar(db)
    now = datetime.now(tz=UTC)
    # 保鲜元信息失败隔离:redis 挂了日程照常下发,只是 updated_at=None + 保守标 stale
    sources: list[EconJobStatus] = []
    updated_at: datetime | None = None
    any_stale = True
    try:
        freshness = await read_source_freshness(await get_redis())
        sources, any_stale = build_econ_job_status(freshness, now)
        updated_at = max((ts for ts in freshness.values() if ts is not None), default=None)
    except Exception:  # noqa: BLE001 · 元信息辅助段挂了不影响日程本体
        logger.warning("[econ-calendar] 保鲜元信息读取失败(忽略·日程照常下发)")
    return EconCalendarResponse(
        events=[EconEventOut.model_validate(e) for e in events],
        sources=sources,
        updated_at=updated_at,
        any_stale=any_stale,
    )
