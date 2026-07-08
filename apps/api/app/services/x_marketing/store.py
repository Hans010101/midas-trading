"""x_tweet 数据访问(阶段4a · PR-1 · 发布层 PR-1 清理改 72h)· create / list_recent / cleanup。

★72h 临时:列表只显 72h 内;清理删 created_at 超 72h 的行 + 返 image_path 给 worker 删截图。
★发布层 PR-1:已发布(有 platform_dispatch 台账)的推文【豁免清理】—— 外部帖子永久,留它发了啥的审计。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import delete, select

from app.models.platform_dispatch import PlatformDispatch
from app.models.x_tweet import XTweet

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

RETENTION_HOURS = 72  # ★72h 临时存储窗口(发布层 PR-1 从 24h 放宽)


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
    auto_drafted: bool = False,
    gen_style: str = "default",
) -> XTweet:
    """存一条推文记录(status 默认 draft)· ★门禁不过的也存(passed=false + reason)。

    auto_drafted=True:自动托管起草(待补发素材识别 + 计入 30 日配额)· 默认 False(手动生成)。
    gen_style:内容生成风格/平台(default 币安长文 / x_short X 短推)· step1 分平台地基。
    """
    row = XTweet(
        symbol=symbol,
        bias=bias,
        tweet_text=tweet_text,
        compliance_passed=compliance_passed,
        compliance_reason=compliance_reason,
        image_path=image_path,
        generated_by=generated_by,
        auto_drafted=auto_drafted,
        gen_style=gen_style,
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


async def get_tweet(session: AsyncSession, tweet_id: int) -> XTweet | None:
    """按 id 取单条推文(后台详情)· 不存在返 None。"""
    return await session.get(XTweet, tweet_id)


async def set_image_path(
    session: AsyncSession, tweet_id: int, image_path: str,
) -> bool:
    """更新某条推文的截图路径(x-shooter 截完 · 主 worker link 回调调用)· 行不存在返 False。"""
    row = await session.get(XTweet, tweet_id)
    if row is None:
        return False
    row.image_path = image_path
    await session.commit()
    return True


async def cleanup_expired(
    session: AsyncSession, *, now: datetime | None = None,
) -> list[str]:
    """删 created_at 超 72h 的行 · 返回这些行的 image_path(非空)给调用方删截图文件。

    ★先收 image_path 再删行(删后查不到)· 返回的路径由 worker 任务 os.remove(本服务不碰文件系统)。
    ★发布层 PR-1:已发布(有 platform_dispatch 台账)的推文【豁免】—— notin_ 子查询排除,留审计。
    """
    now = now or datetime.now(tz=UTC)
    before = now - timedelta(hours=RETENTION_HOURS)
    # 有任何 dispatch 记录的 tweet_id = 已发布 → 排除出清理(台账永久,推文+截图也跟着留)
    published = select(PlatformDispatch.tweet_id).distinct().scalar_subquery()
    expired = (XTweet.created_at < before, XTweet.id.notin_(published))
    paths_stmt = select(XTweet.image_path).where(
        *expired, XTweet.image_path.isnot(None),
    )
    paths = [p for p in (await session.execute(paths_stmt)).scalars().all() if p]
    await session.execute(delete(XTweet).where(*expired))
    await session.commit()
    return paths
