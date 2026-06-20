"""市场周报 · admin 复核 CRUD(P2)。

纯 PG 读写:列表(按 status 筛 + 分页)/ 取单 / 编辑 title·content / 批准(draft→approved)。
★发送(approved→sent)是第二刀,本刀不做。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_report import MarketReport

VALID_STATUSES = ("draft", "approved", "sent")


async def list_reports(
    session: AsyncSession,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[MarketReport], int]:
    """报告列表(按 status 可选筛 · created_at 倒序 · 分页)+ 总数。"""
    base = select(MarketReport)
    count_q = select(func.count()).select_from(MarketReport)
    if status is not None:
        base = base.where(MarketReport.status == status)
        count_q = count_q.where(MarketReport.status == status)
    base = base.order_by(MarketReport.created_at.desc()).limit(limit).offset(offset)

    rows = list((await session.scalars(base)).all())
    total = (await session.scalar(count_q)) or 0
    return rows, total


async def get_report(session: AsyncSession, report_id: int) -> MarketReport | None:
    return await session.get(MarketReport, report_id)


async def update_report(
    session: AsyncSession,
    report_id: int,
    *,
    title: str | None = None,
    content: str | None = None,
) -> MarketReport | None:
    """编辑报告(title / content)· 已发送(sent)不可改 · 返回 None 表示不存在,
    抛 ValueError 表示状态不允许编辑(端点转 409)。"""
    report = await session.get(MarketReport, report_id)
    if report is None:
        return None
    if report.status == "sent":
        raise ValueError("已发送的报告不可编辑")
    if title is not None:
        report.title = title
    if content is not None:
        report.content = content
    await session.commit()
    await session.refresh(report)
    return report


async def approve_report(
    session: AsyncSession,
    report_id: int,
    *,
    admin_id: UUID,
) -> MarketReport | None:
    """批准报告(draft → approved · 记 approved_at/approved_by)。

    返回 None=不存在;抛 ValueError=状态非 draft(端点转 409)。幂等保护:非 draft 拒绝。
    """
    report = await session.get(MarketReport, report_id)
    if report is None:
        return None
    if report.status != "draft":
        raise ValueError(f"仅 draft 可批准 · 当前 {report.status}")
    report.status = "approved"
    report.approved_at = datetime.now(tz=UTC)
    report.approved_by = admin_id
    await session.commit()
    await session.refresh(report)
    return report
