"""x_tweet 数据访问(阶段4a · PR-1)· create / list_recent(24h)/ cleanup_expired(删行+返图路径)。

★24h 临时:列表只显 24h 内;清理删 created_at 超 24h 的行,并把这些行的 image_path 返回给
worker 任务去删截图文件(本服务只管 DB,文件删除在有卷访问的 worker 侧 · 见 tasks/x_tweets.py)。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import delete, select

from app.models.x_tweet import XTweet

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

RETENTION_HOURS = 24  # ★24h 临时存储窗口


async def create_tweet(
    session: AsyncSession,
    *,
    symbol: str,
    bias: str,
    tweet_text: str,
    compliance_passed: bool,
    compliance_reason: str | None = None,
    image_path: str | None = None,
    generated_by: UUID | None = None,
) -> XTweet:
    """存一条推文记录(status 默认 draft)· ★门禁不过的也存(passed=false + reason)。"""
    row = XTweet(
        symbol=symbol,
        bias=bias,
        tweet_text=tweet_text,
        compliance_passed=compliance_passed,
        compliance_reason=compliance_reason,
        image_path=image_path,
        generated_by=generated_by,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_recent(
    session: AsyncSession, *, now: datetime | None = None,
) -> list[XTweet]:
    """列最近 24h 的推文(created_at desc)· 后台面板只显 24h 内。"""
    now = now or datetime.now(tz=UTC)
    since = now - timedelta(hours=RETENTION_HOURS)
    stmt = (
        select(XTweet)
        .where(XTweet.created_at >= since)
        .order_by(XTweet.created_at.desc())
    )
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def cleanup_expired(
    session: AsyncSession, *, now: datetime | None = None,
) -> list[str]:
    """删 created_at 超 24h 的行 · 返回这些行的 image_path(非空)给调用方删截图文件。

    ★先收 image_path 再删行(删后查不到)· 返回的路径由 worker 任务 os.remove(本服务不碰文件系统)。
    """
    now = now or datetime.now(tz=UTC)
    before = now - timedelta(hours=RETENTION_HOURS)
    paths_stmt = select(XTweet.image_path).where(
        XTweet.created_at < before, XTweet.image_path.isnot(None),
    )
    paths = [p for p in (await session.execute(paths_stmt)).scalars().all() if p]
    await session.execute(delete(XTweet).where(XTweet.created_at < before))
    await session.commit()
    return paths
