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
from app.services.ai.llm import ainvoke, is_mock_mode
from app.services.ai.trading_plan import template_note

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


async def generate_plan_note(
    plan: TradingPlan, market: Market, *, language: str = "zh",
) -> tuple[str, int]:
    """生成 plan_note(解释文字)· 返回 (note, total_tokens)。

    mock 模式直接走规则模板(确定性 · 不烧 token);真实模式调 LLM,失败回退模板。

    ★i18n Phase4 刀1:language 默认 zh(走现有 PLAN_NOTE_SYSTEM 中文·逐字节不变)· en 常量刀2 接。
    """
    _ = market  # 当前解释不分市场;保留入参以便后续按市场定制语气
    _ = language  # 刀1 占位:保留入参供刀2 选 zh/en plan_note prompt 常量
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
