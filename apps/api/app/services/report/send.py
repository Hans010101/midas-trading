"""市场周报 · 发送广播(P3 第二刀)。

approved 报告 → 生成 PDF → 给订阅用户(weekly_report_enabled)发:
  ① 邮件:HTML 正文(全文)+ ★PDF 附件;
  ② TG/飞书:「📊 已发送至邮箱」轻提示(不发全文)。
→ status=sent + sent_at。

★人工触发(admin 点发布,不自动发)· ★广播失败隔离(逐人逐渠道 try/except,部分失败不整体崩)·
★只 approved 可发(非 approved 抛 ValueError → 409;不存在抛 LookupError → 404)。
🔴 报告内容已过 validate_advisory + 免责兜底(第一刀);PDF / 邮件渲染该内容 → 自带免责。

发送当前同步跑在 admin 端点(早期订阅量小 · PDF 走 to_thread 不阻塞 loop · 邮件/推送均 await I/O);
订阅量上量后可平移为 Celery 任务(逻辑已在本 service · 端点只需改成 enqueue)。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationConfig
from app.models.user import User
from app.services.notifications.dispatcher import dispatch
from app.services.notifications.events import WeeklyReportSentEvent
from app.services.report.pdf import render_report_pdf
from app.services.report.store import get_report

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportSendResult:
    """发送统计(广播结果 · 用于 admin 回显 / 日志)。"""

    report_id: int
    recipients: int
    email_sent: int
    email_failed: int
    notify_sent: int  # TG/飞书 实际投递的用户数(无绑定渠道 no-op 不计)
    notify_failed: int


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def report_email_html(title: str, content: str) -> str:
    """报告 HTML 正文(衬线 + 中国红标题)· content 换行 → <p>。"""
    paragraphs = "".join(
        f"<p style='margin:0 0 12px;line-height:1.8;color:#1a1a1a'>{_esc(line.strip())}</p>"
        for line in content.split("\n")
        if line.strip()
    )
    return (
        "<div style='font-family:\"Noto Serif SC\",serif;max-width:640px;"
        "margin:0 auto;padding:24px'>"
        f"<h1 style='color:#C8102E;font-size:22px;margin:0 0 20px'>{_esc(title)}</h1>"
        f"{paragraphs}"
        "<p style='margin-top:28px;font-size:12px;color:#999'>"
        "本邮件含 PDF 附件 · 点金 Midas 市场周报</p>"
        "</div>"
    )


async def query_subscribers(session: AsyncSession) -> list[tuple[UUID, str]]:
    """订阅市场周报(weekly_report_enabled=true)的用户 → [(user_id, email)]。

    ★只取已订阅用户(收件人筛选铁律 · 未订阅不发)。邮箱 = User.email(注册必填,恒非空)。
    """
    stmt = (
        select(User.id, User.email)
        .join(NotificationConfig, NotificationConfig.user_id == User.id)
        .where(NotificationConfig.weekly_report_enabled.is_(True))
    )
    rows = await session.execute(stmt)
    return [(cast("UUID", row[0]), cast("str", row[1])) for row in rows.all()]


async def send_report(session: AsyncSession, report_id: int) -> ReportSendResult:
    """发送一篇 approved 报告给订阅用户 → status=sent。

    ★只 approved 可发(draft/sent 抛 ValueError → 409)· 不存在抛 LookupError → 404 ·
    ★广播逐人逐渠道失败隔离(单点失败不影响其他人 / 不阻止 status=sent)。
    """
    from app.services.email import send_report_email  # 延迟 import 避免循环

    report = await get_report(session, report_id)
    if report is None:
        msg = f"报告 {report_id} 不存在"
        raise LookupError(msg)
    if report.status != "approved":
        msg = f"仅 approved 报告可发送(当前 {report.status})"
        raise ValueError(msg)

    title = report.title
    # PDF 是 CPU 同步活 → to_thread 避免阻塞事件循环
    pdf_bytes = await asyncio.to_thread(render_report_pdf, title, report.content)
    pdf_filename = f"{title}.pdf"
    html = report_email_html(title, report.content)

    subscribers = await query_subscribers(session)
    email_sent = email_failed = notify_sent = notify_failed = 0

    for user_id, email in subscribers:
        # ① 邮件:全文 + PDF 附件
        if email:
            try:
                await send_report_email(
                    to=email, subject=title, html=html,
                    pdf_bytes=pdf_bytes, pdf_filename=pdf_filename,
                )
                email_sent += 1
            except Exception as e:  # noqa: BLE001 — ★广播失败隔离:单人失败 continue
                logger.warning("[report] 邮件发送失败 user=%s · %s", user_id, e)
                email_failed += 1
        # ② TG/飞书:已发邮箱轻提示(dispatch 按用户已绑渠道投递 · 无绑定 no-op)
        try:
            result = await dispatch(
                session, user_id, WeeklyReportSentEvent(report_title=title),
            )
            if result.results:
                notify_sent += 1
        except Exception as e:  # noqa: BLE001 — ★广播失败隔离
            logger.warning("[report] 提示推送失败 user=%s · %s", user_id, e)
            notify_failed += 1

    report.status = "sent"
    report.sent_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(report)

    out = ReportSendResult(
        report_id=report_id,
        recipients=len(subscribers),
        email_sent=email_sent,
        email_failed=email_failed,
        notify_sent=notify_sent,
        notify_failed=notify_failed,
    )
    logger.info("[report] 发送完成 · %s", out)
    return out
