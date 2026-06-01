"""AI 观点 → 模拟可下单建议适配层(0036 批次甲 · 纯函数 · 不调 LLM / 不改 AI 管线)。

把 DecisionCardResponse 的【观点输出】(composite_label 五档 + 评分 + 置信)确定性翻译成
【模拟可下单建议】(direction + 仓位口径 + 依据 + 提示),给前端「一键模拟下单」用。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:仅【模拟】参考。direction 只是建议方向;真要下单仍走虚拟撮合引擎(U0 的 execute)
   + 二次确认 + VIRTUAL 徽章,绝不接真实交易、绝不新开下单出口。本文件【不下单、不碰引擎】。
═══════════════════════════════════════════════════════════════════════════

映射(拍板④/③):
- 现货 cn/us:强多/弱多 → buy;中性 → hold(观望);弱空/强空 → sell
  · 现货不裸做空 → sell 语义 = 有持仓建议平、无持仓建议观望(由下单层 + hint 表达,
    适配层用户无关、只产信号方向)。
- 加密 crypto:强多/弱多 → open_long;中性 → hold;弱空/强空 → open_short。
- 仓位:第一层固定走用户下单预设(size_note 给口径,不含数额)。
"""

from __future__ import annotations

from app.schemas.ai_decision import ActionableAdvice, DecisionCardResponse

_BULLISH = ("强多", "弱多")
_BEARISH = ("弱空", "强空")
_SIZE_NOTE = "默认下单预设仓位"
_SIZE_NOTE_HOLD = "—"


def to_actionable(card: DecisionCardResponse) -> ActionableAdvice:
    """决策卡观点 → 模拟可下单建议 · 纯函数 · 幂等。"""
    label = card.composite_label
    is_crypto = card.market == "crypto"
    conf_pct = round(card.composite_confidence * 100)
    basis = f"{label} · 评分 {card.composite_score} · 置信 {conf_pct}%"

    if label in _BULLISH:
        if is_crypto:
            return ActionableAdvice(
                direction="open_long", actionable=True, basis=basis,
                size_note=_SIZE_NOTE, hint="开多参考",
            )
        return ActionableAdvice(
            direction="buy", actionable=True, basis=basis,
            size_note=_SIZE_NOTE, hint="买入参考",
        )
    if label in _BEARISH:
        if is_crypto:
            return ActionableAdvice(
                direction="open_short", actionable=True, basis=basis,
                size_note=_SIZE_NOTE, hint="开空参考",
            )
        # 拍板④:现货不裸做空 → 有持仓建议平、无持仓建议观望
        return ActionableAdvice(
            direction="sell", actionable=True, basis=basis,
            size_note=_SIZE_NOTE,
            hint="现货:如持有该标的可考虑减/平仓;无持仓则观望",
        )
    # 中性 → 观望
    return ActionableAdvice(
        direction="hold", actionable=False, basis=basis,
        size_note=_SIZE_NOTE_HOLD, hint="信号中性 · 建议观望",
    )


def with_actionable(card: DecisionCardResponse) -> DecisionCardResponse:
    """返回带 actionable 的卡片副本(幂等 · 重算覆盖)· API 层在返回前调用。

    放在 API 层(而非 workflow):workflow / AI 分析管线一行不改;且对旧缓存卡片(无此字段)
    也能补算,鲁棒。
    """
    return card.model_copy(update={"actionable": to_actionable(card)})
