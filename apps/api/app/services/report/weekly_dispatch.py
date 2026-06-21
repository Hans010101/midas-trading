"""周报投递服务 · 上传成品 → 提取 → 定时/补传发送(内容侧最终方案)。

★不调 LLM(不生成内容):读运营上传的 md 提取 → 填定稿邮件模板 → PDF(OSS)作附件 → 发订阅用户。
复用第三刀的 query_subscribers / send_report_email / dispatch / object_store(OSS 上传下载)。

★补救窗口 should_auto_send_on_upload:周日 21:00~周一 09:00(CST)上传本周 → 立即发;窗口外只入库。
★幂等:发送前再查 status,已 sent 跳过。一周一条(year+week 唯一)。
"""

from __future__ import annotations

import logging
import uuid as uuid_lib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.weekly_dispatch import WeeklyDispatch
from app.services.notifications.dispatcher import dispatch
from app.services.notifications.events import (
    WeeklyReportSentEvent,
    WeeklyReportSkippedEvent,
)
from app.services.report.object_store import download_object, upload_material
from app.services.report.send import query_subscribers
from app.services.report.weekly_email import build_subject, render_email_html
from app.services.report.weekly_md import (
    WeeklyExtract,
    extract_to_json,
    parse_weekly_md,
)

logger = logging.getLogger(__name__)

# 退订 v1:指向账户通知设置页(登录后关「订阅市场周报」开关)· 一键 token 退订留后续
UNSUBSCRIBE_URL = "https://midastrade.asia/account/alerts"


@dataclass(frozen=True)
class WeeklySendResult:
    dispatch_id: int
    year: int
    week: int
    recipients: int
    email_sent: int
    email_failed: int
    notify_sent: int
    notify_failed: int
    skipped: bool = False  # 幂等跳过(已 sent)


def iso_year_week(d: datetime) -> tuple[int, int]:
    """某时刻的 ISO (year, week)· 周日属当周。"""
    iso = d.isocalendar()
    return iso[0], iso[1]


async def _get_by_year_week(
    session: AsyncSession, year: int, week: int,
) -> WeeklyDispatch | None:
    rows = await session.execute(
        select(WeeklyDispatch).where(
            WeeklyDispatch.year == year, WeeklyDispatch.week == week,
        ),
    )
    return rows.scalar_one_or_none()


async def create_or_update_dispatch(
    session: AsyncSession,
    *,
    pdf_data: bytes,
    pdf_filename: str,
    md_text: str,
    uploaded_by: UUID | None,
) -> tuple[WeeklyDispatch, WeeklyExtract]:
    """解析 md → PDF 存 OSS → upsert(year+week 唯一)· frontmatter 非法 parse 抛 WeeklyMdError。"""
    extract = parse_weekly_md(md_text)
    year = extract.period_start.isocalendar()[0]  # ISO 年(跨年安全)· week 取 frontmatter
    week = extract.week

    uid = uuid_lib.uuid4().hex
    # ★weekly-dispatch/ 前缀避开 report-materials/ 7天 lifecycle(周报留存可回溯)
    oss_key = f"weekly-dispatch/{year}-W{week:02d}/{uid}.pdf"
    await upload_material(oss_key, pdf_data)

    extracted_json = extract_to_json(extract)
    existing = await _get_by_year_week(session, year, week)
    if existing is not None:
        existing.period_start = extract.period_start
        existing.period_end = extract.period_end
        existing.title = extract.title
        existing.pdf_oss_key = oss_key
        existing.pdf_filename = pdf_filename
        existing.md_text = md_text
        existing.extracted = extracted_json
        existing.status = "uploaded"  # 重新上传 → 回到待发(允许补传修正)
        existing.sent_at = None
        existing.uploaded_by = uploaded_by
        existing.uploaded_at = datetime.now(tz=UTC)
        rec = existing
    else:
        rec = WeeklyDispatch(
            year=year,
            week=week,
            period_start=extract.period_start,
            period_end=extract.period_end,
            title=extract.title,
            pdf_oss_key=oss_key,
            pdf_filename=pdf_filename,
            md_text=md_text,
            extracted=extracted_json,
            status="uploaded",
            uploaded_by=uploaded_by,
        )
        session.add(rec)
    await session.commit()
    await session.refresh(rec)
    return rec, extract


async def list_dispatches(session: AsyncSession, *, limit: int = 50) -> list[WeeklyDispatch]:
    rows = await session.execute(
        select(WeeklyDispatch).order_by(WeeklyDispatch.year.desc(), WeeklyDispatch.week.desc())
        .limit(limit),
    )
    return list(rows.scalars().all())


async def get_dispatch(session: AsyncSession, dispatch_id: int) -> WeeklyDispatch | None:
    return await session.get(WeeklyDispatch, dispatch_id)


async def schedule_dispatch(
    session: AsyncSession, dispatch_id: int,
) -> WeeklyDispatch | None:
    """「计划发送」· uploaded/scheduled → scheduled(★纯标记 · 不发送 · 不看时间 · 等周日21:00)。

    不存在 → None(端点 404);已 sent → ValueError(端点 409,已发不能再计划)。
    """
    rec = await session.get(WeeklyDispatch, dispatch_id)
    if rec is None:
        return None
    if rec.status == "sent":
        msg = "已发送的周报不能再计划"
        raise ValueError(msg)
    rec.status = "scheduled"  # uploaded / scheduled(幂等)→ scheduled
    await session.commit()
    await session.refresh(rec)
    return rec


async def cancel_schedule(
    session: AsyncSession, dispatch_id: int,
) -> WeeklyDispatch | None:
    """「取消计划」· scheduled → uploaded(撤回改稿)· 非 scheduled → ValueError(409)。"""
    rec = await session.get(WeeklyDispatch, dispatch_id)
    if rec is None:
        return None
    if rec.status != "scheduled":
        msg = f"仅「已计划」可取消(当前 {rec.status})"
        raise ValueError(msg)
    rec.status = "uploaded"
    await session.commit()
    await session.refresh(rec)
    return rec


async def dispatch_and_send(
    session: AsyncSession, *, year: int, week: int,
) -> WeeklySendResult:
    """发送某周周报给订阅用户 → status=sent。★幂等(已 sent 跳过)· 广播逐人失败隔离。

    不存在该周记录 → LookupError(端点 404 / beat 跳过另走 notify_skip)。
    """
    from app.services.email import send_report_email  # 延迟 import 避免循环

    rec = await _get_by_year_week(session, year, week)
    if rec is None:
        msg = f"{year}-W{week} 无上传记录"
        raise LookupError(msg)
    if rec.status == "sent":
        return WeeklySendResult(
            dispatch_id=rec.id, year=year, week=week, recipients=0,
            email_sent=0, email_failed=0, notify_sent=0, notify_failed=0, skipped=True,
        )

    extracted: dict[str, Any] = rec.extracted
    subject = build_subject(extracted)
    html = render_email_html(extracted, unsubscribe_url=UNSUBSCRIBE_URL)
    pdf_bytes = await download_object(rec.pdf_oss_key)

    subscribers = await query_subscribers(session)
    email_sent = email_failed = notify_sent = notify_failed = 0
    for user_id, email in subscribers:
        if email:
            try:
                await send_report_email(
                    to=email, subject=subject, html=html,
                    pdf_bytes=pdf_bytes, pdf_filename=rec.pdf_filename,
                )
                email_sent += 1
            except Exception as e:  # noqa: BLE001 · 广播失败逐人隔离
                logger.warning("[weekly] 邮件发送失败 user=%s · %s", user_id, e)
                email_failed += 1
        try:
            result = await dispatch(
                session, user_id, WeeklyReportSentEvent(report_title=rec.title),
            )
            if result.results:
                notify_sent += 1
        except Exception as e:  # noqa: BLE001 · 广播失败逐人隔离
            logger.warning("[weekly] 提示推送失败 user=%s · %s", user_id, e)
            notify_failed += 1

    rec.status = "sent"
    rec.sent_at = datetime.now(tz=UTC)
    await session.commit()

    out = WeeklySendResult(
        dispatch_id=rec.id, year=year, week=week, recipients=len(subscribers),
        email_sent=email_sent, email_failed=email_failed,
        notify_sent=notify_sent, notify_failed=notify_failed,
    )
    logger.info("[weekly] 周报发送完成 · %s", out)
    return out


async def run_scheduled_dispatch(
    session: AsyncSession, *, now: datetime,
) -> dict[str, Any]:
    """周日 21:00 定时:本周有 uploaded → 发送;已 sent → 跳过(幂等);无 → notify_skip 提醒 admin。

    返回动作摘要(供日志/测试)。now 用 CST(cn_now)· 周日属当 ISO 周。
    """
    year, week = iso_year_week(now)
    rec = await _get_by_year_week(session, year, week)
    # ★只发【已点计划发送】的(status=scheduled)· 无计划 → 安静跳过(运营自行用立即发送补救,不发提醒)
    if rec is None or rec.status not in {"scheduled", "sent"}:
        return {"action": "no_scheduled", "year": year, "week": week}
    if rec.status == "sent":
        return {"action": "already_sent", "year": year, "week": week}  # 幂等
    result = await dispatch_and_send(session, year=year, week=week)
    return {
        "action": "sent",
        "year": year,
        "week": week,
        "recipients": result.recipients,
        "email_sent": result.email_sent,
    }


async def notify_skip(session: AsyncSession, *, year: int, week: int) -> int:
    """本周未上传 → 提醒 admin(其绑定的 TG/飞书)· 返回触达 admin 数。★失败不抛(提醒非关键)。

    ★保留代码但 run_scheduled_dispatch 不再调用(运营要安静:没有 scheduled 就不发,也不提醒)·
    未来要恢复提醒时一行接回即可。
    """
    admins = (
        await session.execute(select(User.id).where(User.role == "admin"))
    ).scalars().all()
    notified = 0
    for admin_id in admins:
        try:
            result = await dispatch(
                session, admin_id, WeeklyReportSkippedEvent(year=year, week=week),
            )
            if result.results:
                notified += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("[weekly] 跳过提醒失败 admin=%s · %s", admin_id, e)
    logger.warning(
        "[weekly] 本周(%d-W%d)周报未上传,跳过 21:00 定时发送 · 已提醒 %d 个 admin",
        year, week, notified,
    )
    return notified
