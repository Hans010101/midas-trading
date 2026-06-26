"""每日推文生成流程(X 营销阶段4a · PR-2)· 选币 → 生成 → 标签 → 门禁 → 存行(止于 draft)。

★组装阶段2 定稿逻辑:tweet_gen.generate_tweet_text(DeepSeek)+ append_tags + compliance.validate_tweet
→ store.create_tweet。★门禁不过的也存(compliance_passed=false + reason),后台可见但 4b 不可发。
选币复用阶段3 口径:从 boll 快照按 bias 挑(强偏空优先)。截图(image_path)留 PR-4,此处先 null。
触发:admin 端点 enqueue → worker 跑(DeepSeek 慢,异步)· 红线:仅生成入库,零 X API。
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from app.services.x_marketing.compliance import validate_tweet
from app.services.x_marketing.store import create_tweet
from app.services.x_marketing.tweet_gen import (
    TweetContext,
    append_tags,
    generate_tweet_text,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.x_tweet import XTweet

logger = logging.getLogger(__name__)

_GENERATE_TASK = "tasks.x_tweets.generate_daily"
_celery_client: Any = None


def pick_contexts(
    items: list[dict[str, Any]], *, n_short: int = 5, n_long: int = 5, n_neutral: int = 4,
) -> list[TweetContext]:
    """从 boll 快照行按 bias 挑代表性币 → TweetContext(★强偏空优先 · 复用阶段3 口径)。

    偏空 %B 低在前(最空)· 偏多 %B 高在前(最多)· 中性 %B 近 0.5 在前 · 偏空排最前。
    """
    def _of(bias: str) -> list[dict[str, Any]]:
        return [x for x in items if x.get("bias") == bias]

    shorts = sorted(_of("偏空"), key=lambda x: x.get("pct_b", 0.5))[:n_short]
    longs = sorted(_of("偏多"), key=lambda x: -x.get("pct_b", 0.5))[:n_long]
    neutral = sorted(_of("中性"), key=lambda x: abs(x.get("pct_b", 0.5) - 0.5))[:n_neutral]
    return [_to_context(x) for x in (*shorts, *longs, *neutral)]


def _to_context(row: dict[str, Any]) -> TweetContext:
    return TweetContext(
        symbol=str(row["symbol"]),
        price=float(row["close"]) if row.get("close") is not None else None,
        change_pct_24h=(
            float(row["change_pct_24h"]) if row.get("change_pct_24h") is not None else None
        ),
        bias=str(row.get("bias") or "中性"),
        state_label=str(row.get("state_label") or "—"),
        zone_label=str(row.get("zone_label") or "—"),
        pct_b=float(row["pct_b"]) if row.get("pct_b") is not None else None,
        funding_rate=(
            float(row["funding_rate"]) if row.get("funding_rate") is not None else None
        ),
    )


async def generate_and_store(
    session: AsyncSession, contexts: list[TweetContext], *, generated_by: UUID | None,
) -> list[XTweet]:
    """逐币:DeepSeek 生成 → 拼标签 → 门禁 → 存行(★门禁不过也存+reason)· 返回创建的行。

    返回行(含 id+symbol)供 worker 逐条 enqueue 截图(image_path 后续由截图回调填)。
    单币失败(LLM 异常)隔离:log + 跳过,不影响其他币(批量稳健)。
    """
    created: list[XTweet] = []
    for ctx in contexts:
        try:
            resp = await generate_tweet_text(ctx)
            tweet = append_tags(resp.content, ctx.symbol)
            result = validate_tweet(tweet)
            row = await create_tweet(
                session,
                symbol=ctx.symbol,
                bias=ctx.bias,
                tweet_text=tweet,
                compliance_passed=result.passed,
                compliance_reason=None if result.passed else " | ".join(result.reasons),
                generated_by=generated_by,
            )
            created.append(row)
        except Exception as exc:  # noqa: BLE001 · 单币失败隔离,不中断批量
            logger.warning("[x-tweets] 生成失败 symbol=%s · %s", ctx.symbol, exc)
    passed_n = sum(1 for r in created if r.compliance_passed)
    logger.info("[x-tweets] 生成入库 · 共 %d 门禁通过 %d", len(created), passed_n)
    return created


def enqueue_daily_generation(generated_by: UUID) -> None:
    """admin 触发 · enqueue worker 跑生成(★异步:DeepSeek 慢,不阻塞 HTTP)· 走 Celery broker。"""
    global _celery_client
    if _celery_client is None:
        from celery import Celery  # noqa: PLC0415

        broker = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1")
        _celery_client = Celery("midas-api", broker=broker)
    _celery_client.send_task(_GENERATE_TASK, args=[str(generated_by)])
    logger.info("[x-tweets] enqueue 生成任务 · by=%s", generated_by)
