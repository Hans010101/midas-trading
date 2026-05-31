"""AI 历史命中率计算 · 自学习闭环呈现层后端(ADR 0036 批次乙 sub-unit C)。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:
   - 纯只读 PG · 基于 reflection 已验证记录(ai_analysis_memory.was_correct IS NOT NULL)。
   - 不碰下单 / 交易 / 撮合 · 不改 analyze 主流程 · 不打实时上游。
   - ★ 样本诚实标注:每桶给 sample_count + reliable(< MIN_RELIABLE_SAMPLE 标 False),
     hit_rate 在样本为 0 时为 None(不写 0.0 避免误导)。
═══════════════════════════════════════════════════════════════════════════

分桶维度(各自独立聚合 · 借鉴 QuantDinger calibration,但不接其实盘部分):
- 市场:cn / us / crypto(固定列出 · 即便样本 0 也返回,前端结构稳定)
- 方向:bull / bear / flat(reflection 已归并的三档)
- 置信度:<50 / 50-60 / 60-70 / 70-80 / 80-90 / 90-100(composite_confidence ×100)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.ai_analysis_memory import AIAnalysisMemory
from app.schemas.ai_accuracy import AccuracyBucket, AiAccuracyResponse

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ★ 样本可靠阈值:样本数 < 该值的桶命中率仅供参考(统计上小样本不可靠)
MIN_RELIABLE_SAMPLE = 20

# 固定列出的桶维度(即便样本 0 也返回 · 前端结构稳定)
_MARKET_KEYS: tuple[tuple[str, str], ...] = (
    ("cn", "A股"),
    ("us", "美股"),
    ("crypto", "加密"),
)
_DIRECTION_KEYS: tuple[tuple[str, str], ...] = (
    ("bull", "看多"),
    ("bear", "看空"),
    ("flat", "中性"),
)
# 置信度桶:(key, label, 下界含, 上界不含)· composite_confidence ∈ [0,1]
# 最后一桶上界设 1.01 以含 1.0。<50 兜底低置信度(诚实覆盖,不只 50-100)。
_CONFIDENCE_BUCKETS: tuple[tuple[str, str, float, float], ...] = (
    ("<50", "<50%", 0.0, 0.5),
    ("50-60", "50-60%", 0.5, 0.6),
    ("60-70", "60-70%", 0.6, 0.7),
    ("70-80", "70-80%", 0.7, 0.8),
    ("80-90", "80-90%", 0.8, 0.9),
    ("90-100", "90-100%", 0.9, 1.01),
)


def _confidence_key(confidence: float) -> str:
    """把置信度(0..1)映射到桶 key。"""
    for key, _label, lo, hi in _CONFIDENCE_BUCKETS:
        if lo <= confidence < hi:
            return key
    # 理论不可达(confidence ∈ [0,1] 必落某桶)· 防御越界
    return "90-100" if confidence >= 1.0 else "<50"


def _make_bucket(key: str, label: str, correct: int, total: int) -> AccuracyBucket:
    """组装单桶 · hit_rate 在样本 0 时为 None(★不写 0.0 避免误导)。"""
    return AccuracyBucket(
        key=key,
        label=label,
        hit_rate=(correct / total if total > 0 else None),
        sample_count=total,
        correct_count=correct,
        reliable=total >= MIN_RELIABLE_SAMPLE,
    )


def _bucketize(
    counts: dict[str, list[int]],
    ordered_keys: tuple[tuple[str, str], ...],
) -> list[AccuracyBucket]:
    """按固定顺序 keys 输出桶 · counts[key] = [correct, total]。"""
    return [
        _make_bucket(key, label, *counts.get(key, [0, 0]))
        for key, label in ordered_keys
    ]


async def compute_accuracy(
    db: AsyncSession,
    *,
    since: datetime | None = None,
    since_days: int | None = None,
    llm_mode: str | None = None,
) -> AiAccuracyResponse:
    """计算 AI 历史命中率(总体 + 市场 / 方向 / 置信度三维分桶)。

    ★ 只读 PG · 仅统计 reflection 已验证记录(was_correct IS NOT NULL)。

    参数:
      since      - 只统计 analyzed_at >= since 的记录(None = 全部历史)。
      since_days - 仅用于响应回显(端点把天数转成 since 传入)。
      llm_mode   - 'mock' / 'real' 过滤(None = 全部)· 未来切真实模型后前端可只看 real。
    """
    # 只 select 4 个轻量列(不拉全行)· 已验证 = was_correct IS NOT NULL
    stmt = select(
        AIAnalysisMemory.market,
        AIAnalysisMemory.direction,
        AIAnalysisMemory.composite_confidence,
        AIAnalysisMemory.was_correct,
    ).where(AIAnalysisMemory.was_correct.is_not(None))
    if since is not None:
        stmt = stmt.where(AIAnalysisMemory.analyzed_at >= since)
    if llm_mode is not None:
        stmt = stmt.where(AIAnalysisMemory.llm_mode == llm_mode)

    rows = (await db.execute(stmt)).all()

    # [correct, total] 累加器
    overall_correct = 0
    overall_total = 0
    by_market: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_direction: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    by_confidence: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    for market, direction, confidence, was_correct in rows:
        hit = 1 if was_correct else 0
        overall_total += 1
        overall_correct += hit

        by_market[market][1] += 1
        by_market[market][0] += hit

        by_direction[direction][1] += 1
        by_direction[direction][0] += hit

        conf_key = _confidence_key(float(confidence))
        by_confidence[conf_key][1] += 1
        by_confidence[conf_key][0] += hit

    note = (
        "命中率基于 reflection 事后实测涨跌验证(看多→涨 / 看空→跌 / 中性→±1% 内为命中)。"
        f"样本数 < {MIN_RELIABLE_SAMPLE} 的桶(reliable=false)统计意义有限,仅供参考。"
    )

    response = AiAccuracyResponse(
        generated_at=datetime.now(UTC),
        overall_hit_rate=(
            overall_correct / overall_total if overall_total > 0 else None
        ),
        overall_sample_count=overall_total,
        overall_correct_count=overall_correct,
        by_market=_bucketize(by_market, _MARKET_KEYS),
        by_direction=_bucketize(by_direction, _DIRECTION_KEYS),
        by_confidence=[
            _make_bucket(key, label, *by_confidence.get(key, [0, 0]))
            for key, label, _lo, _hi in _CONFIDENCE_BUCKETS
        ],
        min_reliable_sample=MIN_RELIABLE_SAMPLE,
        llm_mode_filter=llm_mode,
        since_days=since_days,
        note=note,
    )
    logger.info(
        "[ai.accuracy] overall sample=%d correct=%d since_days=%s llm_mode=%s",
        overall_total, overall_correct, since_days, llm_mode,
    )
    return response


__all__ = ["MIN_RELIABLE_SAMPLE", "compute_accuracy"]
