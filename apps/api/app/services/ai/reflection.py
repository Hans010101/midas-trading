"""AI 决策卡 Reflection 回填 · 自学习闭环核心价值(ADR 0036 批次乙 sub-unit B)。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:
   ★★ 只读已采 CH 历史价(ch.select_first_kline_at_or_after)· 绝不打实时上游 ——
      这是 B 步的头号红线。reflection 读的是 incremental 采集任务早已落库的历史 K 线,
      不触发任何上游拉取 / 不写 CH。
   - 不碰下单 / 交易 / 撮合(同 A · 纯验证)。
   - 不改 AI 分析主流程(独立守护任务 · 不动 analyze / workflow / agents)。
═══════════════════════════════════════════════════════════════════════════

做什么:
  对 N 天前的 AI 历史判断(ai_analysis_memory · reflected_at IS NULL),
  用事后真实价格回填验证——当时看多 / 看空 / 中性,事后实际涨跌如何 →
  标记 was_correct + actual_return。已验证的记录(reflected_at NOT NULL)不再处理。

判定口径(judge_correct):
  - bull(看多)→ 实际涨(actual_return > 0)= 对
  - bear(看空)→ 实际跌(actual_return < 0)= 对
  - flat(中性)→ |actual_return| < 1%(FLAT_THRESHOLD)= 对(横盘命中)

回填窗口 horizon 可配置 · 先固定 7 天。cutoff = now - horizon 与
horizon_ts = analyzed_at + horizon 用同一 horizon,保证「够资格的记录其 horizon
时刻必然已过」(analyzed_at <= now - horizon ⟺ analyzed_at + horizon <= now)。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_analysis_memory import AIAnalysisMemory

if TYPE_CHECKING:
    # 仅类型标注 · 运行时按 duck-typing(只需 select_first_kline_at_or_after) ·
    # 让 worker / 测试不必构造真实 ClickHouseClient 即可注入。
    from app.services.clickhouse_client import ClickHouseClient

logger = logging.getLogger(__name__)

# 回填窗口:AI 判断后 N 天用实测价验证(可配置 · 先固定 7d)
DEFAULT_HORIZON = timedelta(days=7)
# 中性(flat)判定阈值:|实际涨跌| < 1% 视为「横盘命中」
FLAT_THRESHOLD = Decimal("0.01")
# 单轮最多回填多少条(防一次扫太多 · 剩余下轮继续)
DEFAULT_BATCH_LIMIT = 500


@dataclass(frozen=True)
class ReflectionStats:
    """单轮 reflection 统计 · 给 worker 日志 / 测试断言。"""

    scanned: int      # 本轮扫到的待回填记录数
    reflected: int    # 成功回填(找到 horizon 后 K 线 + 算出 return / was_correct)
    skipped: int      # 跳过(CH 暂无 horizon 后 K 线 / 脏数据)· reflected_at 仍 NULL · 下轮重试
    errored: int      # 单条异常(吞掉 · 不影响其它)· reflected_at 仍 NULL · 下轮重试


def judge_correct(direction: str, actual_return: Decimal) -> bool:
    """方向判定口径(自学习闭环核心):

    - bull(看多)→ 实际涨(return > 0)= 对
    - bear(看空)→ 实际跌(return < 0)= 对
    - flat(中性)→ |return| < FLAT_THRESHOLD(1%)= 对
    - 其它(理论不会有 · 防御)→ False
    """
    if direction == "bull":
        return actual_return > 0
    if direction == "bear":
        return actual_return < 0
    if direction == "flat":
        return abs(actual_return) < FLAT_THRESHOLD
    return False


async def reflect_pending(
    db: AsyncSession,
    ch: ClickHouseClient,
    *,
    now: datetime,
    horizon: timedelta = DEFAULT_HORIZON,
    batch_limit: int = DEFAULT_BATCH_LIMIT,
) -> ReflectionStats:
    """对 reflected_at IS NULL 且 analyzed_at <= now - horizon 的记录回填验证。

    ★ 只读 CH 已采历史价(select_first_kline_at_or_after)· 绝不打实时上游。

    幂等:reflected_at 标记后不再处理 · 重跑安全(beat 重触发 / 手动重试不会重复回填)。
    单条失败吞掉(reflected_at 不变 → 下轮重试)· 不让一条脏数据拖垮整轮。
    """
    cutoff = now - horizon
    # 走部分索引 ix_ai_memory_pending_reflection(WHERE reflected_at IS NULL)
    rows = (
        await db.scalars(
            select(AIAnalysisMemory)
            .where(
                AIAnalysisMemory.reflected_at.is_(None),
                AIAnalysisMemory.analyzed_at <= cutoff,
            )
            .order_by(AIAnalysisMemory.analyzed_at)
            .limit(batch_limit),
        )
    ).all()

    reflected = skipped = errored = 0
    for row in rows:
        try:
            horizon_ts = row.analyzed_at + horizon
            kline = await ch.select_first_kline_at_or_after(
                symbol=row.symbol,
                market=row.market,  # type: ignore[arg-type]
                period=row.period,  # type: ignore[arg-type]
                at_or_after=horizon_ts,
                instrument=row.instrument,
            )
            if kline is None:
                # CH 还没采到 horizon 后的 K 线(标的不在采集池 / 数据延迟)→
                # 跳过 · reflected_at 仍 NULL · 下轮重试
                skipped += 1
                continue
            if row.price_at <= 0:
                # 防御除零(price_at 是 close 价 · 理论 > 0)· 脏数据不静默标记成已验证
                logger.warning(
                    "[ai.reflection] price_at<=0 id=%s symbol=%s · 跳过验证",
                    row.id, row.symbol,
                )
                skipped += 1
                continue

            price_after = Decimal(str(kline.close))
            actual_return = (price_after - row.price_at) / row.price_at
            row.price_after = price_after
            row.actual_return = actual_return
            row.was_correct = judge_correct(row.direction, actual_return)
            row.reflected_at = now
            reflected += 1
        except Exception as e:  # noqa: BLE001
            # 单条异常吞掉(瞬时 CH 抖动等)· reflected_at 不变 → 下轮重试 · 不拖垮整轮
            logger.warning(
                "[ai.reflection] reflect failed id=%s symbol=%s err=%s",
                row.id, row.symbol, e,
            )
            errored += 1

    if reflected:
        await db.commit()

    logger.info(
        "[ai.reflection] scanned=%d reflected=%d skipped=%d errored=%d horizon=%dd",
        len(rows), reflected, skipped, errored, horizon.days,
    )
    return ReflectionStats(
        scanned=len(rows), reflected=reflected, skipped=skipped, errored=errored,
    )


__all__ = [
    "DEFAULT_HORIZON",
    "FLAT_THRESHOLD",
    "ReflectionStats",
    "judge_correct",
    "reflect_pending",
]
