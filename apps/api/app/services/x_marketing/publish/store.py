"""platform_dispatch 数据访问(发布层 PR-1)· 幂等 upsert / 查 / 更新结果。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from app.models.platform_dispatch import PlatformDispatch

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def get_dispatch(
    session: AsyncSession, tweet_id: int, platform: str,
) -> PlatformDispatch | None:
    """取 (tweet_id, platform) 的发布记录 · 无则 None。"""
    stmt = select(PlatformDispatch).where(
        PlatformDispatch.tweet_id == tweet_id,
        PlatformDispatch.platform == platform,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_dispatches(session: AsyncSession, tweet_id: int) -> list[PlatformDispatch]:
    """列某推文的所有平台发布记录(前端按推文展示各平台状态)。"""
    stmt = select(PlatformDispatch).where(PlatformDispatch.tweet_id == tweet_id)
    return list((await session.execute(stmt)).scalars().all())


async def list_dispatches_for_tweets(
    session: AsyncSession, tweet_ids: list[int],
) -> list[PlatformDispatch]:
    """批量列多条推文的发布记录(★一次查避 N+1 · 列表页用)· 空入参返空。"""
    if not tweet_ids:
        return []
    stmt = select(PlatformDispatch).where(PlatformDispatch.tweet_id.in_(tweet_ids))
    return list((await session.execute(stmt)).scalars().all())


async def upsert_pending(
    session: AsyncSession, *, tweet_id: int, platform: str, dispatched_by: UUID | None,
    source: str = "manual",
) -> PlatformDispatch:
    """★幂等:(tweet_id, platform) 已存在则【重置为 pending 重试】,否则新建 · 返回该行。

    端点已在调用前拦掉 status=success(不重复发);到这里只会是 新建 / 失败重试 / 重发 pending。
    ★source:manual(后台人工点 · 默认)/ auto(自动托管 · PR-2/3 传)· 重发沿用新来源。
    """
    existing = await get_dispatch(session, tweet_id, platform)
    if existing is not None:
        existing.status = "pending"
        existing.error = None
        existing.dispatched_by = dispatched_by
        existing.source = source
        await session.commit()
        await session.refresh(existing)
        return existing
    row = PlatformDispatch(
        tweet_id=tweet_id, platform=platform, dispatched_by=dispatched_by, source=source,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_dispatch_result(
    session: AsyncSession,
    dispatch_id: int,
    *,
    status: str,
    platform_post_id: str | None = None,
    url: str | None = None,
    error: str | None = None,
) -> bool:
    """发布完更新结果(success/failed + 帖子 id/url 或 error)· 行不存在返 False。"""
    row = await session.get(PlatformDispatch, dispatch_id)
    if row is None:
        return False
    row.status = status
    row.platform_post_id = platform_post_id
    row.platform_post_url = url
    row.error = error
    await session.commit()
    return True
