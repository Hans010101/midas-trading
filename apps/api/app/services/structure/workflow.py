"""结构诊断 LangGraph workflow · 结构分析助手第2刀。

照 ai/workflow.py 范式(线性节点 · 单例 compiled graph · mock 自动切换):
  Entry → IntentParse(轻量规则归一 5 类 · 零 LLM)→ Snapshot(复用第1刀)
  → Diagnose(单次 llm.ainvoke:问题 + 全因子快照一次喂 · 产结构化 JSON)
  → Validator(复用 ai/validator 祈使句改写 · 红线层)→ Exit。

🔴 红线:非价格预测(prompt 三红线见 prompts.py)· 只读 CH · 不碰决策卡/回测现有逻辑。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypedDict, cast

from langgraph.graph import END, StateGraph

from app.core.config import settings
from app.core.redis_client import get_redis
from app.schemas.structure import (
    FactorFinding,
    IntentKind,
    StructureDiagnosis,
    StructureSnapshot,
)
from app.services.ai.cache import compute_trading_day
from app.services.ai.llm import ainvoke, is_mock_mode
from app.services.ai.usage import log_usage
from app.services.ai.validator import has_imperative, rewrite_imperatives
from app.services.structure.prompts import SYSTEM_PROMPT, build_diagnose_prompt
from app.services.structure.snapshot import build_structure_snapshot, normalize_symbol

if TYPE_CHECKING:
    from clickhouse_connect.driver.asyncclient import AsyncClient

logger = logging.getLogger(__name__)

_CACHE_TTL_S = 3600  # 诊断层 TTL 1h(对齐快照层 · 意图枚举化后才可缓存)
_DIAGNOSE_MAX_TOKENS = 900  # 结论+分因子足够 · 低于 llm.py 默认 1024 硬上限


class NoFactorDataError(Exception):
    """6 个合约因子全 null(symbol 无衍生品数据)· 友好闸:不进 LLM(省成本防垃圾诊断)。

    ★ 不继承 ValueError:端点对 ValueError 走 502(LLM 解析失败),本异常走 422(用户输入面)。
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        super().__init__(f"未找到 {symbol} 的合约因子数据")


# ── 意图归一(轻量规则 + 关键词 · 零 LLM · 枚举化是诊断缓存的前提)──────────────


def parse_intent(question: str) -> IntentKind:
    """自由文本 → 5 类枚举。规则优先级:拥挤(多/空)> 杠杆 > 资金费率 > 方向词 > overall。"""
    q = question.lower()
    crowd = any(k in q for k in ("拥挤", "挤爆", "太挤", "crowd"))
    short_side = any(k in q for k in ("空头", "做空", "空单", "short"))
    long_side = any(k in q for k in ("多头", "做多", "多单", "long"))
    if crowd:
        return "short_crowding" if short_side and not long_side else "long_crowding"
    if any(k in q for k in ("杠杆", "未平仓", "持仓量", "oi", "leverage")):
        return "leverage_buildup"
    if any(k in q for k in ("资金费", "费率", "funding")):
        return "funding_extreme"
    if long_side:
        return "long_crowding"
    if short_side:
        return "short_crowding"
    return "overall"


# ── Workflow State ──────────────────────────────────────────────────────────


class DiagnoseState(TypedDict, total=False):
    # 入参
    client: Any                      # AsyncClient(CH · 只读)
    symbol: str
    question: str
    user_id: str | None              # 会员刀1 · ai_usage_log 审计归属(不参与诊断)
    # IntentParse 产出
    intent: IntentKind
    # Snapshot 产出
    snapshot: StructureSnapshot
    # Diagnose 产出(LLM 原始解析)
    conclusion: str
    factor_findings: list[FactorFinding]
    unsupported_note: str | None
    # Exit 产出
    diagnosis: StructureDiagnosis


# ── 节点实现 ────────────────────────────────────────────────────────────────


async def _node_entry(state: DiagnoseState) -> dict[str, Any]:
    logger.info(
        "[structure.workflow.entry] symbol=%s q=%r", state["symbol"], state["question"][:50],
    )
    return {}


async def _node_intent(state: DiagnoseState) -> dict[str, Any]:
    intent = parse_intent(state["question"])
    logger.info("[structure.workflow.intent] → %s", intent)
    return {"intent": intent}


async def _node_snapshot(state: DiagnoseState) -> dict[str, Any]:
    snapshot = await build_structure_snapshot(state["client"], state["symbol"])
    # 友好闸:6 个合约因子全 null(sentiment 是全局因子不计入)→ 不进 LLM 节点。
    # 场景:无效 symbol(XYZUSDT)/ 非 USDT 永续(BTCUSDC)—— 省一次 LLM 成本 + 防贫瘠垃圾诊断。
    contract_factors = (
        snapshot.account_long_short,
        snapshot.position_long_short,
        snapshot.taker_flow,
        snapshot.open_interest,
        snapshot.funding_rate,
        snapshot.basis,
    )
    if all(f is None for f in contract_factors):
        raise NoFactorDataError(state["symbol"])
    return {"snapshot": snapshot}


async def _node_diagnose(state: DiagnoseState) -> dict[str, Any]:
    """单次 LLM:问题 + 全因子快照一次喂 · JSON 输出 · 解析失败明确 raise(不缓存坏结果)。"""
    snapshot = state["snapshot"]
    prompt = build_diagnose_prompt(
        state["question"], state["intent"], snapshot.model_dump(mode="json"),
    )
    resp = await ainvoke(
        prompt,
        system=SYSTEM_PROMPT,
        response_format_json=True,
        max_tokens=_DIAGNOSE_MAX_TOKENS,
        temperature=0.2,
    )
    # 真实调用记账(mock 不记 · 同决策卡)。period 表必填,结构诊断无 K 线周期 → 记 '1d' 占位。
    if not is_mock_mode():
        await log_usage(
            market="crypto",
            symbol=state["symbol"],
            period="1d",
            model=settings.llm_model,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
            total_tokens=resp.total_tokens,
            node="structure_diagnose",
            status="success",
            user_id=state.get("user_id"),
        )

    try:
        data = json.loads(resp.content)
        conclusion = str(data["conclusion"]).strip()
        findings = [
            FactorFinding(
                factor=str(f["factor"])[:32],
                state=str(f["state"])[:40],
                detail=str(f["detail"])[:300],
                window=str(f.get("window", "latest"))[:16],
            )
            for f in data.get("factor_findings", [])
        ]
        raw_note = data.get("unsupported_note")
        note = str(raw_note)[:200] if raw_note else None
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        # 明确失败,不产兜底假诊断(避免被缓存层存 1h 的坏结果);端点转 502 让用户重试。
        msg = f"structure diagnose: LLM 输出解析失败({e});content 前 80 字={resp.content[:80]!r}"
        raise ValueError(msg) from e

    if not conclusion:
        msg = "structure diagnose: LLM 输出 conclusion 为空"
        raise ValueError(msg)
    return {"conclusion": conclusion, "factor_findings": findings, "unsupported_note": note}


async def _node_validator(state: DiagnoseState) -> dict[str, Any]:
    """祈使句 → 陈述句改写(复用 ai/validator · 0012 红线②同款)· 结论与各因子 detail 都过。"""
    conclusion = state["conclusion"]
    if has_imperative(conclusion):
        logger.warning("[structure.workflow.validator] 结论含祈使句 · 改写 · %r", conclusion[:60])
        conclusion = rewrite_imperatives(conclusion)
    findings = [
        f.model_copy(update={"detail": rewrite_imperatives(f.detail)})
        if has_imperative(f.detail)
        else f
        for f in state["factor_findings"]
    ]
    return {"conclusion": conclusion, "factor_findings": findings}


async def _node_exit(state: DiagnoseState) -> dict[str, Any]:
    diagnosis = StructureDiagnosis(
        conclusion=state["conclusion"],
        factor_findings=state["factor_findings"],
        intent=state["intent"],
        unsupported_note=state.get("unsupported_note"),
        snapshot=state["snapshot"],
    )
    return {"diagnosis": diagnosis}


# ── Workflow 构造(单例 compiled · 照 ai/workflow.py)──────────────────────────


def _build_workflow() -> Any:
    graph = StateGraph(DiagnoseState)
    graph.add_node("entry", _node_entry)
    graph.add_node("intent_parse", _node_intent)
    graph.add_node("snapshot", _node_snapshot)
    graph.add_node("diagnose", _node_diagnose)
    graph.add_node("validator", _node_validator)
    graph.add_node("exit", _node_exit)

    graph.set_entry_point("entry")
    graph.add_edge("entry", "intent_parse")
    graph.add_edge("intent_parse", "snapshot")
    graph.add_edge("snapshot", "diagnose")
    graph.add_edge("diagnose", "validator")
    graph.add_edge("validator", "exit")
    graph.add_edge("exit", END)

    return graph.compile()


_compiled = _build_workflow()


# ── 公共入口 ────────────────────────────────────────────────────────────────


async def run_structure_diagnosis(
    client: AsyncClient, symbol: str, question: str, user_id: str | None = None,
) -> StructureDiagnosis:
    """跑完整诊断 workflow(无缓存 · 缓存在 get_structure_diagnosis)。"""
    state: DiagnoseState = {
        "client": client,
        "symbol": normalize_symbol(symbol),
        "question": question,
        "user_id": user_id,
    }
    final_state = await _compiled.ainvoke(state)
    return cast("StructureDiagnosis", final_state["diagnosis"])


def _cache_key(symbol: str, intent: IntentKind) -> str:
    return f"ai:structure:diagnose:{symbol}:{intent}:{compute_trading_day('crypto')}"


async def get_structure_diagnosis(
    client: AsyncClient,
    symbol: str,
    question: str,
    *,
    user_id: str | None = None,
    on_llm_run: Callable[[], Awaitable[None]] | None = None,
) -> StructureDiagnosis:
    """缓存优先(key 含归一意图 · 同 symbol+意图+6h 桶共享)· Redis 异常降级直跑。

    ★ 取舍:同意图不同措辞共享同一份诊断(意图枚举化是缓存命中率的来源 · 任务拍板)。
    会员刀1:on_llm_run 只在缓存 miss、LLM 真跑成功后调用(额度扣减的灵魂位置 ——
    命中缓存不扣 · LLM 失败不扣);回调异常不阻塞诊断返回。
    """
    sym = normalize_symbol(symbol)
    intent = parse_intent(question)
    key = _cache_key(sym, intent)
    try:
        redis = await get_redis()
        raw = await redis.get(key)
        if raw is not None:
            return StructureDiagnosis.model_validate(json.loads(raw))
    except Exception as e:  # noqa: BLE001 — 缓存读失败不阻塞主链路
        logger.warning("[structure.diagnose.cache] get failed key=%s err=%s", key, e)

    diagnosis = await run_structure_diagnosis(client, sym, question, user_id=user_id)
    if on_llm_run is not None:
        try:
            await on_llm_run()
        except Exception as e:  # noqa: BLE001 — 扣减失败不阻塞结果(用户已拿到诊断)
            logger.warning("[structure.diagnose.quota] on_llm_run failed err=%s", e)

    try:
        redis = await get_redis()
        await redis.setex(
            key, _CACHE_TTL_S, json.dumps(diagnosis.model_dump(mode="json"), ensure_ascii=False),
        )
    except Exception as e:  # noqa: BLE001 — 缓存写失败不阻塞主链路
        logger.warning("[structure.diagnose.cache] set failed key=%s err=%s", key, e)

    return diagnosis


__all__ = [
    "NoFactorDataError",
    "get_structure_diagnosis",
    "parse_intent",
    "run_structure_diagnosis",
]
