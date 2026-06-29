"""智能交易复盘生成(智能交易第二期 PR-8)· 读交易数据 → DeepSeek 复盘 → 存库 → 发送。

🔴旁观分析师:只读【已平 intelligent 仓】数据生成分析报告 · 绝不碰交易执行/下单决策 · 引擎零碰。
复用:review.build_review_data(PR-7 结构化数据)+ ai.llm.ainvoke(DeepSeek)+ email/telegram(发送)。
日报/周报/月报按 period 取不同窗口 · 周/月报对比上期同周期(发现趋势)· 存 1 月供月报读周报。
发送对象 = admin(产品负责人 · 内部策略诊断工具)· 日报邮件+TG · 周/月报邮件。
★AI 输出红线:复盘正文末尾强制免责"仅供参考,不构成投资建议"(email + TG 双通道)。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.models.intelligent_review import IntelligentReview
from app.models.notification import NotificationConfig
from app.models.user import User
from app.services.ai.llm import ainvoke
from app.services.email import send_email
from app.services.notifications import telegram
from app.services.virtual_trading.intelligent.review import (
    build_review_data,
    fetch_review_trades,
    period_start,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PERIOD_LABEL = {"day": "日报", "week": "周报", "month": "月报"}
REVIEW_RETENTION_DAYS = 30  # ★复盘历史存 1 月(让月报读周报 + 上期对比 · Hans 定)
# 🔴AI 输出免责红线:用"仅供参考/不构成投资建议",★不含"虚拟"二字(CLAUDE.md 锁死红线)
_DISCLAIMER = "⚠ 本复盘仅供参考,不构成投资建议。"
_TG_MAX = 4000  # Telegram sendMessage 限 4096 字符 · 留余量

# ★复盘 Prompt(★Hans 设计 · 严格按此实现 · 不改成套话 · {{REVIEW_DATA}} 处插结构化数据)─────
_REVIEW_PROMPT = """你是一位专业的量化交易策略复盘分析师。你的任务是\
分析一套"多指标共振"自动交易策略的虚拟交易数据,\
找出策略表现背后的具体原因,给出可执行的改进建议。

【重要原则】
1. 你是分析师不是交易员——复盘诊断·不预测未来不给交易指令
2. ★必须基于提供的具体数据说话·引用具体数字·严禁空洞套话
3. ★严禁说"表现良好""注意风险""继续保持"这类放之四海皆准的废话
4. 发现具体规律(如"做空胜率明显低于做多")·给具体可执行建议(如"考虑提高做空开仓阈值")
5. ★如果数据量少不足以下结论·如实说明·不要硬凑分析

【策略机制】
- 6指标打分共振:布林(权重2.0)+MACD(1.5)+MA(1.5)+RSI(1.0)+KDJ(1.0)+perp极端(1.0)·满分8.0
- 加权得分>+阈值开多·<−阈值开空(当前阈值±3.0)
- 止损:开仓价∓2×ATR / 止盈:开仓价±4×ATR(理论盈亏比2:1)
- 平仓三出口:ATR止损 / 2:1止盈 / 信号反转(得分跌破0)
- 每单固定保证金·5倍杠杆

【你要分析的数据】
{{REVIEW_DATA}}

【按5维度分析·每维度必须引用具体数字】

1.【整体表现诊断】
- 盈亏比和胜率说明什么?
- ★理论盈亏比2:1·实际盈亏比多少?差距说明什么?
- 实际远低于2:1则分析原因(止盈很少触及?信号反转平太早?)

2.【做多vs做空对比】
- 哪个方向更准?胜率/盈亏比差多少?
- ★某方向明显差是重要发现(该方向规则可能有问题)

3.【平仓原因分析】
- 三种平仓占比说明什么?
- ★信号反转平占比高(>50%)说明什么?(开仓信号不稳?共振后很快反转?)
- ★止盈占比低说明什么?(止盈设太远?趋势跟踪在震荡市失效?)

4.【共振信号质量】★诊断核心
- by_indicator:哪些指标参与的单胜率高/低?哪些在拖后腿?
- by_score_band:强共振vs中共振哪个表现好?
- ★中共振(刚过阈值)表现差→阈值可能太松
- ★某指标参与单胜率特别低→该指标权重可能要调

5.【可执行改进建议】
- 基于上面发现·给具体可执行调整建议
- ★必须具体:不是"优化策略"·而是"考虑把阈值从3.0提到4.0·因为中共振单胜率仅X%"
- ★针对当前可调参数(阈值/权重/ATR倍数)给建议

【输出】结构化报告·5维度清晰分段·每结论引用具体数字·数据少如实说不硬凑
(周报/月报额外:对比本期vs上期·发现趋势)"""

# system:呼应原则 · 强化旁观分析师红线(🔴不碰交易执行)
_REVIEW_SYSTEM = (
    "你是量化交易策略复盘分析师,只做复盘诊断,不预测未来、不给交易指令、不参与下单决策。"
    "必须基于提供的具体数据分析,引用具体数字,严禁空洞套话。"
)


def build_review_prompt(
    review_data: dict[str, Any], period: str, prev_content: str | None = None,
) -> str:
    """组装复盘 Prompt(★Hans 原文 + 插结构化数据 + 周/月报追加上期对比)· 纯函数 · 可测。"""
    data_json = json.dumps(review_data, ensure_ascii=False, indent=2)
    prompt = _REVIEW_PROMPT.replace("{{REVIEW_DATA}}", data_json)
    label = PERIOD_LABEL.get(period, "复盘")
    if period in ("week", "month") and prev_content:
        prompt += (
            f"\n\n【上期{label}复盘报告(★对比本期 vs 上期 · 发现趋势)】\n{prev_content[:3000]}"
        )
    return prompt


def is_last_day_of_month(now: datetime) -> bool:
    """是否当月最后一天(纯函数 · 月报 beat 用 · 自动处理 28/29/30/31)。"""
    return (now + timedelta(days=1)).month != now.month


async def _prev_review(
    session: AsyncSession, period: str, before: Any,
) -> IntelligentReview | None:
    """读上一期同 period 复盘(对比趋势)· period_start < before · 取最近一条。"""
    row = await session.scalar(
        select(IntelligentReview)
        .where(
            IntelligentReview.period == period,
            IntelligentReview.period_start < before,
        )
        .order_by(IntelligentReview.period_start.desc())
        .limit(1),
    )
    return row  # noqa: RET504 · 赋值供 mypy 推断类型(inline return 会 Returning Any)


async def generate_review(
    session: AsyncSession, period: str, now: datetime,
) -> IntelligentReview:
    """fetch → build_review_data → 读上期 → DeepSeek → 存表(★幂等 upsert)→ 返回记录。

    🔴只读交易数据 · 不碰执行。无 DEEPSEEK_API_KEY → ainvoke 自动 mock(is_mock=True)。
    """
    if period not in PERIOD_LABEL:
        period = "day"
    trades = await fetch_review_trades(session, period, now)
    review_data = build_review_data(trades, period)
    start = period_start(period, now).date()
    prev = await _prev_review(session, period, start) if period in ("week", "month") else None
    prompt = build_review_prompt(review_data, period, prev.content if prev else None)

    resp = await ainvoke(
        prompt=prompt, system=_REVIEW_SYSTEM, temperature=0.4, max_tokens=2048,
    )

    # ★幂等 upsert(period + period_start 唯一 → 同周期重跑覆盖)
    stmt = (
        pg_insert(IntelligentReview)
        .values(
            period=period, period_start=start, trade_count=len(trades),
            content=resp.content, review_data=review_data,
            is_mock=resp.is_mock, total_tokens=resp.total_tokens,
        )
        .on_conflict_do_update(
            index_elements=["period", "period_start"],
            set_={
                "content": resp.content, "review_data": review_data,
                "trade_count": len(trades), "is_mock": resp.is_mock,
                "total_tokens": resp.total_tokens,
            },
        )
        .returning(IntelligentReview)
    )
    row = await session.scalar(stmt)
    await session.commit()
    if row is None:  # 理论不达(returning 必返)· 类型兜底
        msg = "intelligent_review upsert 未返回记录"
        raise RuntimeError(msg)
    logger.info(
        "[intelligent-review] 生成 %s · %s · 单数=%d · mock=%s · tokens=%d",
        period, start, len(trades), resp.is_mock, resp.total_tokens,
    )
    return row


async def _admin_recipients(session: AsyncSession) -> tuple[list[str], list[str]]:
    """查 admin 的 email + 已绑 TG chat_id(复盘 = 产品负责人内部诊断工具)。"""
    rows = await session.execute(
        select(User.email, NotificationConfig.tg_chat_id)
        .outerjoin(NotificationConfig, NotificationConfig.user_id == User.id)
        .where(User.role == "admin"),
    )
    emails: list[str] = []
    chat_ids: list[str] = []
    for email, chat_id in rows.all():
        if email:
            emails.append(email)
        if chat_id:
            chat_ids.append(chat_id)
    return emails, chat_ids


def _render_email_html(review: IntelligentReview, period: str) -> str:
    """复盘邮件 HTML(中国红标题 + 正文 pre-wrap + 🔴免责)· 纯函数。"""
    label = PERIOD_LABEL.get(period, "复盘")
    body = review.content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        '<div style="font-family:-apple-system,sans-serif;max-width:680px;margin:0 auto;'
        'color:#1a1a1a;line-height:1.7">'
        f'<h2 style="color:#C8102E;border-bottom:2px solid #B8860B;padding-bottom:8px">'
        f"智能交易策略复盘 · {label}</h2>"
        f'<p style="color:#666;font-size:13px">周期起点 {review.period_start} · '
        f"本期 {review.trade_count} 笔已平仓</p>"
        f'<pre style="white-space:pre-wrap;font-family:inherit;font-size:14px;'
        f'background:#FCFCF9;padding:16px;border-radius:8px">{body}</pre>'
        f'<p style="color:#999;font-size:12px;margin-top:24px;'
        f'border-top:1px solid #eee;padding-top:12px">{_DISCLAIMER}</p>'
        "</div>"
    )


async def dispatch_review(
    session: AsyncSession, period: str, now: datetime, *, channels: set[str],
) -> dict[str, Any]:
    """生成 + 发送复盘 · channels={'email','tg'} · 失败逐通道隔离 · 🔴正文带免责。"""
    review = await generate_review(session, period, now)
    emails, chat_ids = await _admin_recipients(session)
    label = PERIOD_LABEL.get(period, "复盘")
    sent = {"email": 0, "tg": 0}

    if "email" in channels and emails:
        subject = f"【点金 Midas】智能交易策略复盘 · {label} · {review.period_start}"
        html = _render_email_html(review, period)
        for email in emails:
            try:
                await send_email(to=email, subject=subject, html=html)
                sent["email"] += 1
            except Exception:  # noqa: BLE001 · 逐人隔离
                logger.warning("[intelligent-review] 邮件发送失败 to=%s", email)

    if "tg" in channels and chat_ids and settings.tg_bot_token:
        # 🔴TG 正文带免责 · 超长截断(复盘多在限内)
        text = f"📊 *智能交易策略复盘 · {label}* · {review.period_start}\n\n{review.content}"
        text = f"{text[:_TG_MAX]}\n\n{_DISCLAIMER}"
        for chat_id in chat_ids:
            try:
                await telegram.send(settings.tg_bot_token, chat_id, text)
                sent["tg"] += 1
            except telegram.TelegramApiError:
                logger.warning("[intelligent-review] TG 发送失败 chat=%s", chat_id)

    logger.info(
        "[intelligent-review] 发送 %s · 邮件 %d · TG %d · mock=%s",
        period, sent["email"], sent["tg"], review.is_mock,
    )
    return {
        "period": period, "trade_count": review.trade_count,
        "sent": sent, "is_mock": review.is_mock,
    }


async def cleanup_old_reviews(session: AsyncSession, now: datetime) -> int:
    """删 created_at < now − 30 天的复盘(★存 1 月)· 返回删除行数。"""
    cutoff = now - timedelta(days=REVIEW_RETENTION_DAYS)
    result = await session.execute(
        delete(IntelligentReview).where(IntelligentReview.created_at < cutoff),
    )
    await session.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]  # CursorResult.rowcount
