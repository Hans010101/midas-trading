"""X 营销自动托管 · 自动发布编排(自动托管 PR-3)。

draft_scan 起草门禁通过的推文后,按 2-4min 间隔排发布任务;每个任务到点跑 run_auto_publish:
★发布前【再次】过守卫(countdown 这 2-4min 内开关/熔断/时段可能已变 · 紧急熔断的兜底)→
upsert_pending(source=auto)→ run_publish(复用发布层:撮合+台账+rate_limit+门禁双保险)→
成功:mark_published(6h去重)+ incr_daily(日计数)+ reset_fail · 失败:record_fail,连续 3 次 → 开熔断。

★退避(护栏⑤):连续失败 FAIL_THRESHOLD 次自动开熔断 + TG 通知 Hans(best-effort)· 停所有自动发。
★红线:只发分析推文 binance_square,零碰交易引擎(虚拟交易绝不真实下单)· 门禁不过 run_publish 内再拦。
"""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.services.x_marketing.publish import auto_guard
from app.services.x_marketing.publish.dispatch import run_publish
from app.services.x_marketing.publish.store import upsert_pending

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_PLATFORM = "binance_square"  # 自动托管只发币安广场(唯一有官方发帖 API 的平台)
_DELAY_MIN_S = 60   # 单条自动发布随机延迟下限 1min(频率调整 · Hans 定)
_DELAY_MAX_S = 420  # 上限 7min


def publish_delay_seconds() -> int:
    """单条自动发布的随机延迟(★1-7min · 每次随机 · 抹除「每小时固定分钟发」的机器指纹)。

    ★不是配速/最小间隔(Hans 否决):做T 信号要及时,不憋信号;延迟只为打散发布时刻、更像真人。
    """
    return random.randint(_DELAY_MIN_S, _DELAY_MAX_S)  # noqa: S311 · 非密码学用途(打散时刻)


async def run_auto_publish(
    session: AsyncSession, redis: Any, *, tweet_id: int, symbol: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """到点发布单条 · ★发布前再过守卫 → 发 → 记账(成功去重/计数 · 失败退避熔断)。

    返回 {"status": success/failed/skip, "reason"/"circuit_opened"...}。circuit_opened=True
    时由 worker 发 TG 通知 Hans(本函数不发 TG,保持可测)。
    """
    # ★发布前再过守卫(countdown 期间紧急熔断/关开关的兜底 · 即使 revoke 漏了也在此 skip)
    if not await auto_guard.is_enabled(redis):
        return {"status": "skip", "reason": "disabled"}
    if await auto_guard.is_circuit_open(redis):
        return {"status": "skip", "reason": "circuit_open"}
    if not auto_guard.is_in_publish_window(now):
        return {"status": "skip", "reason": "out_of_window"}
    if await auto_guard.daily_remaining(redis, now) <= 0:
        return {"status": "skip", "reason": "daily_cap"}
    if await auto_guard.is_recently_published(redis, symbol):
        return {"status": "skip", "reason": "duplicate"}  # 6h 内已发(并发/重排兜底)

    # 发布(复用发布层 · source=auto 审计 · run_publish 内含门禁双保险 + rate_limit)
    dispatch = await upsert_pending(
        session, tweet_id=tweet_id, platform=_PLATFORM, dispatched_by=None, source="auto",
    )
    result = await run_publish(session, redis, dispatch.id)

    if result.get("status") == "success":
        await auto_guard.mark_published(redis, symbol)  # ★6h 去重(发成功才标)
        await auto_guard.reset_fail(redis)              # 成功 → 清连续失败
        # ★日计数 +1 由 run_publish 在成功且 tweet.auto_drafted 时记(单点 · 自动发+人工补发共用配额)
        logger.info("[x-auto] ✓ 自动发布成功 tweet=%s symbol=%s", tweet_id, symbol)
        return {"status": "success", "url": result.get("url")}

    # 失败 → 退避:连续失败计数,达阈值开熔断(护栏⑤)
    fail_count = await auto_guard.record_fail(redis)
    circuit_opened = False
    if fail_count >= auto_guard.FAIL_THRESHOLD:
        await auto_guard.open_circuit(redis)
        circuit_opened = True
        logger.warning(
            "[x-auto] ★连续失败 %d 次 → 自动开熔断(停所有自动发)· tweet=%s",
            fail_count, tweet_id,
        )
    else:
        logger.warning("[x-auto] 自动发布失败 %d/%d · tweet=%s", fail_count,
                       auto_guard.FAIL_THRESHOLD, tweet_id)
    return {
        "status": "failed", "reason": result.get("error") or result.get("reason"),
        "fail_count": fail_count, "circuit_opened": circuit_opened,
    }


async def notify_circuit_open(fail_count: int) -> None:
    """★熔断时 TG 通知 Hans(best-effort · 永不 raise · 未配 admin_tg_chat_id 则仅日志)。"""
    token = settings.tg_bot_token
    chat = settings.admin_tg_chat_id
    if not token or not chat:
        logger.warning("[x-auto] 熔断已开但未配 ADMIN_TG_CHAT_ID,跳过 TG 通知(仅日志)")
        return
    try:
        from app.services.notifications import telegram  # noqa: PLC0415

        await telegram.send(
            token, chat,
            f"⚠️ 点金 X 营销自动托管【已熔断】\n连续发布失败 {fail_count} 次,已自动停止自动发布。\n"
            f"请检查币安广场 API / 网络后,在后台重新开启开关(开启即清熔断)。",
            parse_mode="",
        )
        logger.info("[x-auto] 熔断 TG 通知已发给 Hans")
    except Exception:  # noqa: BLE001
        logger.exception("[x-auto] 熔断 TG 通知失败(不影响熔断生效)")
