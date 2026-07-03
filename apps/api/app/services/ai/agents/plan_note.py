"""交易计划解释 Agent · 把【规则算出的三价位】喂给 LLM,生成一段"为什么这么定"的解释。

★ 红线(prompt 是红线模块 · 改动须走机器证明 test_prompt_invariants):
  - LLM 只写【解释文字】· 绝不生成/改动价位数字(数字由 trading_plan.compute_trading_plan 规则算)。
  - 禁祈使句(与技术面 Agent 一致 · 过 ValidatorNode 二次兜底)。
  - 不出现真实交易 / 下单指令措辞 · 仅陈述测算逻辑。
  - 不注入资金费率 / 链上数据(crypto 这些 M2+ 才接 · 与 _SYSTEM_CRYPTO 声明一致)。
mock 模式 / 解析失败 → 回退 trading_plan.template_note(价位感知的规则模板 · 确定性可测)。
"""

from __future__ import annotations

import logging

from app.schemas.ai_decision import TradingPlan
from app.schemas.market import Market
from app.services.ai.language_lock import LANGUAGE_LOCK_RETRY_PREFIX, contains_cjk
from app.services.ai.llm import ainvoke, is_mock_mode
from app.services.ai.prompts_en import PLAN_NOTE_SYSTEM_EN
from app.services.ai.trading_plan import template_note, template_note_en
from app.services.ai.validator import (
    ADVISORY_DISCLAIMER_EN,
    ensure_advisory_disclaimer_en,
    rewrite_imperatives,
    scrub_marketing,
)

# 对齐 TradingPlan.plan_note 的 max_length=400 —— 免责兜底追加后仍必须 ≤ 此值,
# 否则端点 response_model=DecisionCardResponse 再校验时 string_too_long → HTTP 500。
_EN_NOTE_MAX = 400

logger = logging.getLogger(__name__)


PLAN_NOTE_SYSTEM = (
    "你是点金 Midas 的交易计划解读助手。下面给你的【入场区间 / 止损失效价 / 双目标 / 盈亏比】"
    "都是系统用规则(布林轨 / ATR / 缠论中枢位)算好的,你的任务【只是用中文解释这套计划的逻辑】:"
    "为什么在这个区间进场、为什么这个价位算失效、目标依据是什么。\n"
    "硬约束:\n"
    "  - **绝对不能修改或新增任何价格数字**,只复述给定价位。\n"
    "  - **绝对不能出现「建议买入」「建议卖出」「应该买」「快入场」「立刻下单」等祈使句**,"
    "只做陈述。\n"
    "  - 不构成投资指令,只描述这套规则测算的逻辑;不要提及资金费率 / 链上数据。\n"
    "  - 不超过 120 字,一段话,中文。"
)

_SIDE_LABEL = {"long": "做多(顺势回撤进场)", "short": "做空(反弹进场)", "neutral": "中性"}


def _format_plan_prompt(plan: TradingPlan) -> str:
    side = _SIDE_LABEL[plan.direction]
    return (
        f"方向:{side}\n"
        f"入场区间:{plan.entry_low} – {plan.entry_high}\n"
        f"止损失效价:{plan.stop}\n"
        f"目标1 / 目标2:{plan.target1} / {plan.target2}\n"
        f"盈亏比:约 {plan.risk_reward}\n"
        "请用一段话解释这套计划的逻辑(为什么这样定入场/止损/目标)。"
    )


_SIDE_LABEL_EN = {
    "long": "long (trend-following pullback entry)",
    "short": "short (bounce entry)",
    "neutral": "neutral",
}


def _format_plan_prompt_en(plan: TradingPlan) -> str:
    """英文 user prompt(i18n Phase4 刀2)· 全英文输入配英文 system,降串台。"""
    side = _SIDE_LABEL_EN[plan.direction]
    return (
        f"Direction: {side}\n"
        f"Entry zone: {plan.entry_low} – {plan.entry_high}\n"
        f"Stop (invalidation): {plan.stop}\n"
        f"Target 1 / Target 2: {plan.target1} / {plan.target2}\n"
        f"Risk-reward: about {plan.risk_reward}\n"
        "Explain the logic of this plan in one paragraph (why this entry / stop / targets)."
    )


def _finalize_note_en(text: str) -> str:
    """en 红线对等兜底:祈使改写 + 营销 scrub + 英文免责固定串(缺则追加)· 且保证 ≤400 字。

    ★与技术卡的 workflow validator 节点同源(i18n-4 语言感知 validator)· 保证英文 plan_note
      同样【分析非建议 + 带免责】,与中文同等强度(Hans 红线)。
    ★长度兜底(修串台/长文本 500 崩):免责追加后若超 TradingPlan.plan_note 上限(400),
      给免责【留位】截 body 再兜底 —— 保证 ≤400 且【不截掉免责】,否则端点 response_model 会 500。
    """
    text = rewrite_imperatives(text, language="en")
    text = scrub_marketing(text, language="en")
    out = ensure_advisory_disclaimer_en(text)
    if len(out) <= _EN_NOTE_MAX:
        return out
    budget = _EN_NOTE_MAX - len(ADVISORY_DISCLAIMER_EN) - 1  # 400 - 74 - 1(分隔空格)= 325
    return ensure_advisory_disclaimer_en(text[:budget].rstrip())


async def _generate_plan_note_en(plan: TradingPlan) -> tuple[str, int]:
    """英文 plan_note · 语言锁双层(prompt 内 LANGUAGE LOCK + 这里的 CJK 重试/降级)+ en 红线兜底。"""
    if plan.direction == "neutral" or plan.entry_low is None:
        return _finalize_note_en(template_note_en(plan)), 0
    if is_mock_mode():
        return _finalize_note_en(template_note_en(plan)), 0
    try:
        resp = await ainvoke(
            prompt=_format_plan_prompt_en(plan),
            system=PLAN_NOTE_SYSTEM_EN,
            response_format_json=False,
            temperature=0.4,
            max_tokens=256,
        )
        note = resp.content.strip()
        total = resp.total_tokens
        if not note or contains_cjk(note):
            # 空 / 串台 → 加强语言锁重试一次
            logger.warning("[ai.plan_note] en 输出空或含中文(串台)· 重试一次")
            resp2 = await ainvoke(
                prompt=LANGUAGE_LOCK_RETRY_PREFIX + _format_plan_prompt_en(plan),
                system=PLAN_NOTE_SYSTEM_EN,
                response_format_json=False,
                temperature=0.4,
                max_tokens=256,
            )
            note2 = resp2.content.strip()
            total += resp2.total_tokens
            if note2 and not contains_cjk(note2):
                return _finalize_note_en(note2), total   # _finalize_note_en 保证 ≤400
            # 重试仍不合格 → 降级英文模板(绝不把中文漏给英文用户)
            logger.warning("[ai.plan_note] en 重试仍不合格 · 降级英文模板")
            return _finalize_note_en(template_note_en(plan)), total
        return _finalize_note_en(note), total
    except Exception:  # noqa: BLE001 — 解释失败不阻断决策卡,回退英文模板
        logger.warning("[ai.plan_note] en LLM 生成失败 · 回退英文模板", exc_info=True)
        return _finalize_note_en(template_note_en(plan)), 0


async def generate_plan_note(
    plan: TradingPlan, market: Market, *, language: str = "zh",
) -> tuple[str, int]:
    """生成 plan_note(解释文字)· 返回 (note, total_tokens)。

    mock 模式直接走规则模板(确定性 · 不烧 token);真实模式调 LLM,失败回退模板。

    ★i18n Phase4:language 默认 zh(走现有 PLAN_NOTE_SYSTEM 中文·逐字节不变)· en 走英文分支
      (英文 prompt + 语言锁双层 + en validator + 免责兜底)。
    """
    _ = market  # 当前解释不分市场;保留入参以便后续按市场定制语气
    if language == "en":
        return await _generate_plan_note_en(plan)
    # ===== zh 路径(逐字节不变)=====
    if plan.direction == "neutral" or plan.entry_low is None:
        return template_note(plan), 0
    if is_mock_mode():
        return template_note(plan), 0
    try:
        resp = await ainvoke(
            prompt=_format_plan_prompt(plan),
            system=PLAN_NOTE_SYSTEM,
            response_format_json=False,
            temperature=0.4,
            max_tokens=256,
        )
        note = resp.content.strip()
        if not note:
            return template_note(plan), resp.total_tokens
        return note[:400], resp.total_tokens
    except Exception:  # noqa: BLE001 — 解释失败不阻断决策卡,回退模板
        logger.warning("[ai.plan_note] LLM 生成失败 · 回退模板", exc_info=True)
        return template_note(plan), 0


__all__ = ["PLAN_NOTE_SYSTEM", "generate_plan_note"]
