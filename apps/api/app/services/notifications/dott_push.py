"""做T 推送真发广播(M2-5)· 体系1(全景)/ 体系2(转换)共用。

★总闸 settings.dott_push_live 默认 False = 仍影子(broadcast 返回 live=False · worker 走 logger)。
发送链路安全(即便真发也必须有):
  ① 总闸 DOTT_PUSH_LIVE=false → 不真发(刹车 · 一键回影子不用回滚代码);
  ② 收件人 = 订阅对应开关 + 已绑 TG + ★Pro(发送前 resolve_plan 再确认 · 双保险);
  ③ 失败逐人隔离(照搬周报广播 · 一人失败不影响其他);
  ④ 文案在【组装期】已过 validate_shadow_push(build_* 内置门禁;render_telegram 对 dott 事件
     原样返回 message · 不绕过);
  ⑤ 用户安静时段在 dispatch 内按 config.quiet_hours 过滤(dott 事件 quiet_exempt=False)。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.config import settings
from app.models.notification import NotificationConfig
from app.services.membership import resolve_plan
from app.services.notifications.dispatcher import dispatch
from app.services.notifications.events import (
    DottDigestEvent,
    DottTransitionEvent,
    NotificationEvent,
    NotificationKind,
)

if TYPE_CHECKING:
    from uuid import UUID

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DottBroadcastResult:
    live: bool                 # 总闸是否开(False = 影子未真发)
    subscribers: int = 0       # 订阅该体系 + 已绑 TG 的用户数
    sent: int = 0              # dispatch 成功(至少一通道发出)
    failed: int = 0            # dispatch 失败(逐人隔离 · 不抛)
    skipped_non_pro: int = 0   # ★发送前 Pro 确认拦下的(非 Pro 即便 DB flag=true 也不发)


def _dott_column(kind: NotificationKind) -> object:
    """该体系的订阅列(收件人筛选)。"""
    if kind == NotificationKind.DOTT_DIGEST:
        return NotificationConfig.dott_digest_enabled
    return NotificationConfig.dott_transition_enabled


def _make_dott_event(kind: NotificationKind, message: str) -> NotificationEvent:
    """该体系的事件(携带组装好的文案 · render_telegram 原样发)。"""
    if kind == NotificationKind.DOTT_DIGEST:
        return DottDigestEvent(message=message)
    return DottTransitionEvent(message=message)


async def query_dott_subscribers(
    session: AsyncSession, *, kind: NotificationKind,
) -> list[tuple[UUID, str]]:
    """订阅该体系(dott_*_enabled=true)且已绑 TG(tg_chat_id 非空)的用户 → [(user_id, tg_chat_id)]。

    ★收件人筛选铁律:只取订阅 + 已绑 TG 的;Pro 在发送前 broadcast_dott 里再确认(双保险)。
    """
    col = _dott_column(kind)
    stmt = select(NotificationConfig.user_id, NotificationConfig.tg_chat_id).where(
        col.is_(True),  # type: ignore[attr-defined]
        NotificationConfig.tg_chat_id.isnot(None),
    )
    rows = await session.execute(stmt)
    return [(row[0], row[1]) for row in rows.all()]


async def broadcast_dott(
    session: AsyncSession,
    messages: list[str],
    *,
    kind: NotificationKind,
    client: httpx.AsyncClient | None = None,
) -> DottBroadcastResult:
    """把 messages 真发给该体系订阅者。★总闸 DOTT_PUSH_LIVE=false → 不发(live=False · 影子不变)。

    逐订阅者:发送前 Pro 再确认(非 Pro 跳过)→ 每条 messages 走 dispatch(订阅开关 + 用户安静时段 +
    渲染发送)· 失败逐人隔离(照搬周报)。返回各计数供 worker 日志。
    """
    if not settings.dott_push_live:
        return DottBroadcastResult(live=False)  # ★总闸关 → 不真发(worker 走影子日志)

    subs = await query_dott_subscribers(session, kind=kind)
    sent = failed = skipped = 0
    for user_id, _chat in subs:
        # ★Pro 发送前再确认(双保险 · 即便 PUT gate 拦过,发送时再查;非 Pro 不发)
        if await resolve_plan(session, user_id) != "pro":
            skipped += 1
            continue
        for msg in messages:
            try:
                # dispatch 内含:_kind_enabled(订阅开关)+ 用户安静时段(quiet_exempt=False)+ 渲染发送
                event = _make_dott_event(kind, msg)
                result = await dispatch(session, user_id, event, client=client)
                if result.any_sent:
                    sent += 1
                elif result.any_error:
                    failed += 1
            except Exception as exc:  # noqa: BLE001 · 广播逐人隔离 · 单点失败不影响其他人
                logger.warning("[dott-push] 发送失败 user=%s kind=%s · %s", user_id, kind, exc)
                failed += 1
    return DottBroadcastResult(
        live=True, subscribers=len(subs), sent=sent, failed=failed, skipped_non_pro=skipped,
    )
