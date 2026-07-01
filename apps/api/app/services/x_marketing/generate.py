"""每日推文生成流程(X 营销阶段4a · PR-2)· 选币 → 生成 → 标签 → 门禁 → 存行(止于 draft)。

★组装阶段2 定稿逻辑:tweet_gen.generate_tweet_text(DeepSeek)+ append_tags + compliance.validate_tweet
→ store.create_tweet。★门禁不过的也存(compliance_passed=false + reason),后台可见但 4b 不可发。
选币复用阶段3 口径:从 boll 快照按 bias 挑(强偏空优先)。截图(image_path)留 PR-4,此处先 null。
触发:admin 端点 enqueue → worker 跑(DeepSeek 慢,异步)· 红线:仅生成入库,零 X API。
"""

from __future__ import annotations

import logging
import os
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.services.clickhouse_crypto import (
    select_futures_metrics_batch,
    select_long_short,
    select_open_interest,
)
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
    from app.services.clickhouse_client import ClickHouseClient

logger = logging.getLogger(__name__)

_GENERATE_TASK = "tasks.x_tweets.generate_daily"
_celery_client: Any = None


def pick_auto_contexts(
    items: list[dict[str, Any]], *, limit: int = 2,
) -> list[TweetContext]:
    """自动托管选币(★口径 b · Hans 定):transition=true 池 → |change_pct_24h| 降序 → 取 limit。

    和 TG 推送近似同源(都偏向极端转换币)· 6h 去重在调用方(run_auto_draft)做 · 复用 _to_context。
    """
    trans = [x for x in items if x.get("transition")]
    trans.sort(key=lambda x: abs(x.get("change_pct_24h") or 0.0), reverse=True)
    return [_to_context(x) for x in trans[:limit]]


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


async def fetch_extra_metrics(
    ch: ClickHouseClient, contexts: list[TweetContext],
) -> list[TweetContext]:
    """★刀2(路线①)· 对【已选中的少量币】查 ClickHouse 富化 5 扩字段 → 返回富化后的 contexts。

    ★做T零碰(只读 CH · 不动 boll_scan/boll:snapshot)· ★优雅降级(任一字段查不到=None=不喂·不报错)。
    只对已选中的币(手动 ≤14 / 自动 ≤2)查,不全量 · 富化:OI 绝对值 / OI 24h 变化% /
    全市场多空比 / 15m 涨跌% / 15m 量比。
    """
    if not contexts:
        return contexts
    symbols = [c.symbol for c in contexts]
    batch: dict[str, dict[str, float]] = {}
    try:
        batch = await select_futures_metrics_batch(ch._client, symbols=symbols)  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001 · OI 变化批量失败 → 降级不喂
        logger.warning("[x-tweets] OI 变化批量查失败 · 降级: %s", exc)

    out: list[TweetContext] = []
    for ctx in contexts:
        extra: dict[str, float] = {}
        if ( oi_chg := (batch.get(ctx.symbol) or {}).get("oi_change_pct_24h") ) is not None:
            extra["oi_change_pct_24h"] = oi_chg
        try:
            oi_rows = await select_open_interest(ch._client, ctx.symbol, limit=1)  # noqa: SLF001
            if oi_rows:
                extra["oi_usd"] = oi_rows[-1].oi_usd
        except Exception as exc:  # noqa: BLE001
            logger.debug("[x-tweets] OI 查失败 %s: %s", ctx.symbol, exc)
        try:
            ls_rows = await select_long_short(ch._client, ctx.symbol, limit=1)  # noqa: SLF001
            if ls_rows and ls_rows[-1].global_account_ratio > 0:
                extra["long_short_ratio"] = ls_rows[-1].global_account_ratio
        except Exception as exc:  # noqa: BLE001
            logger.debug("[x-tweets] 多空比查失败 %s: %s", ctx.symbol, exc)
        try:
            kl = await ch.select_kline(
                symbol=ctx.symbol, market="crypto", period="15m", limit=21, instrument="perp",
            )
            if len(kl) >= 2 and kl[-2].close > 0:  # noqa: PLR2004
                extra["change_pct_15m"] = (kl[-1].close - kl[-2].close) / kl[-2].close * 100
            if len(kl) >= 6:  # noqa: PLR2004 · 至少几根才有均量意义
                prior = kl[-21:-1]
                avg_vol = sum(k.volume for k in prior) / len(prior)
                if avg_vol > 0:
                    extra["volume_ratio"] = kl[-1].volume / avg_vol
        except Exception as exc:  # noqa: BLE001
            logger.debug("[x-tweets] 15m kline 查失败 %s: %s", ctx.symbol, exc)
        out.append(replace(ctx, **extra) if extra else ctx)  # type: ignore[arg-type]
    return out


async def generate_and_store(
    session: AsyncSession, contexts: list[TweetContext], *, generated_by: UUID | None,
    auto_drafted: bool = False, ch: ClickHouseClient | None = None,
) -> list[XTweet]:
    """逐币:DeepSeek 生成 → 拼标签 → 门禁 → 存行(★门禁不过也存+reason)· 返回创建的行。

    返回行(含 id+symbol)供 worker 逐条 enqueue 截图(image_path 后续由截图回调填)。
    单币失败(LLM 异常)隔离:log + 跳过,不影响其他币(批量稳健)。
    auto_drafted=True:自动托管起草(待补发素材 + 计入 30 日配额)· 默认 False(手动)。
    ★ch 给定(刀2):先富化 5 扩字段(做T零碰·失败整体降级到基础字段);None=不富化(向后兼容)。
    """
    if ch is not None:
        try:
            contexts = await fetch_extra_metrics(ch, contexts)
        except Exception as exc:  # noqa: BLE001 · 富化整体失败 → 用基础字段(绝不阻塞生成)
            logger.warning("[x-tweets] 扩数据富化失败 · 用基础字段: %s", exc)
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
                auto_drafted=auto_drafted,
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
