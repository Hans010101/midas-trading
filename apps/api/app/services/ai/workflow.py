"""AI 决策卡 LangGraph workflow · 0012 ADR § LangGraph workflow 设计。

M1 二波单 Agent 版(0012 § M1 二波降级 v2):6 节点:
  Entry → DataPrepare → 技术面 Agent → DecisionCard → Validator → Exit

为什么用 LangGraph 即使只有 6 个线性节点:
  - M2 加 4 Agent 并行时,只需在这里改图结构,调用方不动
  - LangGraph 自带状态合并 / 错误传播 / 断点 · 不用自己写
  - workflow 可视化(.get_graph().draw_ascii())对调试很方便

mock 边界:
  - 技术面 Agent 内部走 llm.ainvoke · ainvoke 自动判断 mock 还是真实(详见 llm.py)
  - 等产品负责人填 DEEPSEEK_API_KEY 后,workflow 代码完全不动 · 自动从 mock 切到真实
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypedDict, cast

from langgraph.graph import END, StateGraph

from app.core.config import settings
from app.schemas.ai_decision import (
    AgentScore,
    ChanBuySellPoint,
    DecisionCardResponse,
    TechnicalSnapshot,
    TradingPlan,
)
from app.schemas.market import Kline, Market, Period
from app.services.ai import indicators as ind
from app.services.ai.agents.plan_note import generate_plan_note
from app.services.ai.agents.technical import analyze_technical, score_to_label
from app.services.ai.llm import is_mock_mode
from app.services.ai.trading_plan import compute_trading_plan
from app.services.ai.usage import log_usage
from app.services.ai.validator import has_imperative, rewrite_imperatives
from app.services.analysis import chan as chan_service
from app.services.analysis.chan import ChanAnalysisResult

# 标记 TYPE_CHECKING 别名(消除 unused import 警告)
_ = TYPE_CHECKING

logger = logging.getLogger(__name__)


# ===== Workflow State =====


class DecisionState(TypedDict, total=False):
    # 入参
    symbol: str
    market: Market
    period: Period
    klines: list[Kline]
    language: str  # i18n Phase4 刀1:'zh'(默认)/'en' · 穿给 agent prompt 分发 + validator

    # DataPrepareNode 产出
    chan_result: ChanAnalysisResult
    snapshot: TechnicalSnapshot

    # 技术面 Agent 产出
    technical_score: AgentScore
    token_usage: int

    # TradingPlanNode 产出(三价位规则算 + AI plan_note)
    trading_plan: TradingPlan

    # DecisionCardNode 产出
    narrative: str

    # Validator 产出
    validated_narrative: str

    # Exit 产出
    card: DecisionCardResponse


# ===== 节点实现 =====


async def _node_entry(state: DecisionState) -> dict[str, Any]:
    """EntryNode · 入参校验 · 当前由调用方校验,这里只 log。"""
    logger.info(
        "[ai.workflow.entry] symbol=%s market=%s period=%s bars=%d",
        state["symbol"], state["market"], state["period"], len(state["klines"]),
    )
    return {}


async def _node_data_prepare(state: DecisionState) -> dict[str, Any]:
    """DataPrepareNode · 算指标快照 + 跑缠论 · 组装 TechnicalSnapshot。

    复用已有的 chan service · 不再重复算笔/分型/中枢。
    """
    klines = state["klines"]
    period = state["period"]
    symbol = state["symbol"]

    chan_result = await chan_service.analyze(klines, period, symbol)

    ma = ind.compute_ma(klines)
    macd = ind.compute_macd(klines)
    rsi = ind.compute_rsi(klines)
    boll = ind.compute_boll(klines)
    trend = ind.compute_trend_5d(klines)

    atr = ind.compute_atr(klines)
    last_zs = chan_result.zhongshus[-1] if chan_result.zhongshus else None

    last = klines[-1]
    last_bi_direction = chan_result.bis[-1].direction if chan_result.bis else None

    # 最近 3 个买卖点(给 LLM 看 · 不超过 3 个免噪音)
    recent_bsp_dicts: list[dict[str, object]] = [
        {
            "ts": p.ts.isoformat(),
            "price": p.price,
            "kind": p.kind,
            "description": p.description,
        }
        for p in chan_result.buy_sell_points[-3:]
    ]

    snapshot = TechnicalSnapshot(
        last_close=float(last.close),
        last_ts=last.ts,
        ma=ma,
        macd=macd,
        rsi=rsi,
        boll=boll,
        trend_5d=trend,
        chan_bi_count=len(chan_result.bis),
        chan_last_bi_direction=last_bi_direction,
        chan_zhongshu_count=len(chan_result.zhongshus),
        chan_recent_buy_sell_points=recent_bsp_dicts,
        atr=atr,
        zhongshu_high=last_zs.high if last_zs else None,
        zhongshu_low=last_zs.low if last_zs else None,
    )

    return {"chan_result": chan_result, "snapshot": snapshot}


async def _node_technical_agent(state: DecisionState) -> dict[str, Any]:
    """技术面 Agent · 跑 LLM(mock 或 real)· 输出 AgentScore。"""
    snapshot = state["snapshot"]
    market = state["market"]
    score, prompt_tokens, completion_tokens, total_tokens = await analyze_technical(
        snapshot, market, language=state.get("language", "zh"),
    )

    # 真实调用时记 ai_usage_log · mock 不记(避免污染统计)
    if not is_mock_mode():
        await log_usage(
            market=market,
            symbol=state["symbol"],
            period=state["period"],
            model=settings.llm_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            node="technical_agent",
            status="success",
        )

    return {"technical_score": score, "token_usage": total_tokens}


async def _node_trading_plan(state: DecisionState) -> dict[str, Any]:
    """TradingPlanNode · 规则算三价位 + AI 写 plan_note(★价位 100% 规则 · LLM 只写解释)。

    compute_trading_plan 按 score 方向纯规则算出 入场区间/止损/双目标/盈亏比;
    generate_plan_note 让 LLM 解释(mock / 失败回退价位感知模板)。中性方向三价位全 None。
    """
    snapshot = state["snapshot"]
    score = state["technical_score"].score
    plan = compute_trading_plan(
        score=score,
        last_close=snapshot.last_close,
        boll=snapshot.boll,
        atr=snapshot.atr,
        zhongshu_high=snapshot.zhongshu_high,
        zhongshu_low=snapshot.zhongshu_low,
    )
    note, note_tokens = await generate_plan_note(
        plan, state["market"], language=state.get("language", "zh"),
    )
    plan = plan.model_copy(update={"plan_note": note})
    return {
        "trading_plan": plan,
        "token_usage": state.get("token_usage", 0) + note_tokens,
    }


async def _node_decision_card(state: DecisionState) -> dict[str, Any]:
    """DecisionCardNode · 把 AgentScore 转成 narrative(决策卡叙事)。

    M1 二波简化:不再单独调一次 LLM 生成 narrative · 直接复用技术面 Agent 的 rationale。
    省一次 LLM 调用 · 省 token · 也更可控(narrative 跟评分理由一致)。

    M2 加 Aggregator 时,这个节点要重新激活(综合多 Agent 评分生成统一叙事)。
    """
    score = state["technical_score"]
    narrative = score.rationale
    return {"narrative": narrative}


async def _node_validator(state: DecisionState) -> dict[str, Any]:
    """ValidatorNode · 祈使句 → 陈述句改写 · 0012 红线 ②。"""
    narrative = state["narrative"]
    lang = state.get("language", "zh")
    if has_imperative(narrative, language=lang):
        logger.warning(
            "[ai.workflow.validator] imperative detected · rewriting · before=%r",
            narrative[:80],
        )
        narrative = rewrite_imperatives(narrative, language=lang)
    return {"validated_narrative": narrative}


async def _node_exit(state: DecisionState) -> dict[str, Any]:
    """ExitNode · 组装 DecisionCardResponse 输出。"""
    score = state["technical_score"]
    chan_result = state["chan_result"]
    narrative = state["validated_narrative"]

    chan_signals = [
        ChanBuySellPoint(
            ts=p.ts, price=p.price,
            kind=p.kind,
            description=p.description,
        )
        for p in chan_result.buy_sell_points
    ]

    card = DecisionCardResponse(
        symbol=state["symbol"],
        market=state["market"],
        period=state["period"],
        generated_at=datetime.now(UTC),
        # M1 二波 Aggregator 直通:综合 = 技术面
        composite_score=score.score,
        composite_label=score_to_label(score.score),
        composite_confidence=score.confidence,
        agent_scores=[score],
        contradiction=None,             # M1 二波永远 None
        narrative=narrative,
        chan_signals=chan_signals,
        trading_plan=state.get("trading_plan"),
        cached=False,
        token_usage=state.get("token_usage", 0),
        llm_mode="mock" if is_mock_mode() else "real",
    )

    return {"card": card}


# ===== Workflow 构造 =====


def _build_workflow() -> Any:
    """构造 LangGraph workflow · 6 节点线性。

    M2 升级时,这里改图结构(加 Aggregator + 4 Agent 并行)即可,调用方无感。
    """
    graph = StateGraph(DecisionState)
    graph.add_node("entry", _node_entry)
    graph.add_node("data_prepare", _node_data_prepare)
    graph.add_node("technical_agent", _node_technical_agent)
    graph.add_node("trading_plan", _node_trading_plan)
    graph.add_node("decision_card", _node_decision_card)
    graph.add_node("validator", _node_validator)
    graph.add_node("exit", _node_exit)

    graph.set_entry_point("entry")
    graph.add_edge("entry", "data_prepare")
    graph.add_edge("data_prepare", "technical_agent")
    graph.add_edge("technical_agent", "trading_plan")
    graph.add_edge("trading_plan", "decision_card")
    graph.add_edge("decision_card", "validator")
    graph.add_edge("validator", "exit")
    graph.add_edge("exit", END)

    return graph.compile()


# 单例 compiled graph · 避免每次请求重新编译
_compiled = _build_workflow()


# ===== 公共入口 =====


async def run_decision_workflow(
    symbol: str, market: Market, period: Period, klines: list[Kline],
    *, language: str = "zh",
) -> DecisionCardResponse:
    """跑完整 workflow · 返回 DecisionCardResponse。

    ★i18n Phase4 刀1:language 穿进 state → agent prompt 分发 + validator(默认 zh · zh 走原路径)。
    """
    state: DecisionState = {
        "symbol": symbol,
        "market": market,
        "period": period,
        "klines": klines,
        "language": language,
    }
    final_state = await _compiled.ainvoke(state)
    return cast("DecisionCardResponse", final_state["card"])


__all__ = ["run_decision_workflow"]
