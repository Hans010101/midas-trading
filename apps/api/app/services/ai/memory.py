"""AI 决策卡历史记录服务 · 端点旁路写入 · 自学习闭环地基(ADR 0036 批次乙)。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:
   - 端点旁路 best-effort · 任何异常吞掉 · 永不阻塞决策卡响应。
   - 不参与撮合 / 下单 / 余额 · 不改 analyze 主流程。
   - reflection / 命中率统计的【写入端】· 读出端(回填 + 聚合)分别在
     reflection.py / accuracy.py(批次乙 sub-unit B/C)。
═══════════════════════════════════════════════════════════════════════════

direction 五档归并 → 三档:
  - 强多 / 弱多 → bull(看涨)
  - 中性        → flat(横盘)
  - 弱空 / 强空 → bear(看跌)
便于 was_correct 判定(reflection)+ 命中率分桶聚合(accuracy)。
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_analysis_memory import AIAnalysisMemory
from app.schemas.ai_decision import DecisionCardResponse

logger = logging.getLogger(__name__)


# composite_label(强多/弱多/中性/弱空/强空)→ direction(bull/flat/bear)
_LABEL_TO_DIRECTION: Final[dict[str, str]] = {
    "强多": "bull",
    "弱多": "bull",
    "中性": "flat",
    "弱空": "bear",
    "强空": "bear",
}


def direction_from_label(label: str) -> str:
    """决策卡 composite_label 五档归并到 bull/bear/flat 三档。

    用于:
    1. memory 表 direction 列(reflection 用 direction 判 was_correct)。
    2. accuracy API 分桶聚合(强多 / 弱多 共享 bull 桶,避免样本碎片化)。

    未知 label fallback flat —— 防御未来 schema 扩展时 reflection 炸。
    """
    return _LABEL_TO_DIRECTION.get(label, "flat")


async def record_decision(
    db: AsyncSession,
    *,
    card: DecisionCardResponse,
    instrument: str,
    price_at: Decimal,
) -> None:
    """旁路写一行 AIAnalysisMemory · best-effort · 永不抛 / 永不阻塞调用方。

    调用点:GET /api/v1/analysis/decision-card cache-miss 后(workflow 跑完 + 写
    Redis 缓存后)· 用 klines[-1].close 作为 price_at。

    🔴 红线:
      - 任何异常吞掉 · 只记 warning(用户已经看到决策卡了)。
      - 失败时 rollback session · 避免污染请求生命周期内其它操作(本端点当前 GET 没其它写,
        但接口约束上仍要清理,防未来加新写入操作时连锁失败)。
      - 不影响 workflow / cache 任何分支。
    """
    try:
        row = AIAnalysisMemory(
            symbol=card.symbol,
            market=card.market,
            instrument=instrument,
            period=card.period,
            analyzed_at=card.generated_at,
            direction=direction_from_label(card.composite_label),
            composite_score=card.composite_score,
            composite_label=card.composite_label,
            # float → Decimal 走 str 转换避免 IEEE754 漂移
            composite_confidence=Decimal(str(card.composite_confidence)),
            price_at=price_at,
            llm_mode=card.llm_mode,
        )
        db.add(row)
        await db.commit()
        logger.info(
            "[ai.memory] recorded symbol=%s market=%s instrument=%s period=%s "
            "direction=%s score=%d label=%s mode=%s",
            card.symbol, card.market, instrument, card.period,
            row.direction, card.composite_score, card.composite_label, card.llm_mode,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[ai.memory] record failed symbol=%s market=%s period=%s err=%s",
            card.symbol, card.market, card.period, e,
        )
        try:
            await db.rollback()
        except Exception as roll_e:  # noqa: BLE001
            logger.warning("[ai.memory] rollback also failed err=%s", roll_e)


__all__ = ["direction_from_label", "record_decision"]
