"""技术面 Agent · 0012 ADR § 分市场 Agent 配置 + M1 二波降级 v2。

输入:TechnicalSnapshot(K 线指标 + 缠论结构摘要)
输出:AgentScore(name='technical' · score -100..100 · rationale · key_levels)

mock 模式下 LLM 调用走 llm.ainvoke 的 mock 路径 · 接口签名不变。
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from app.schemas.ai_decision import AgentScore, TechnicalSnapshot
from app.schemas.market import Market
from app.services.ai.llm import ainvoke

logger = logging.getLogger(__name__)


# ===== System prompts 分市场 =====


_SYSTEM_BASE = (
    "你是点金 Midas 的技术面分析助手。基于给定的 K 线指标、缠论结构、最近买卖点,"
    "输出**结构化评分 JSON**:\n"
    "  - score: 整数 -100 到 +100(强空 -100 / 中性 0 / 强多 +100)\n"
    "  - confidence: 浮点 0..1 · 你对结论的信心度\n"
    "  - rationale: 中文解读 · 不超过 200 字 · "
    "**绝对不能出现「建议买入」「建议卖出」「应该买」「快入场」等祈使句** · 只做陈述描述\n"
    "  - key_levels: 数组 · 1-2 个关键价位(支撑 / 阻力)\n"
    "**必须严格返回 JSON,不能有其他文本。**"
)

_SYSTEM_CN = _SYSTEM_BASE + "\n\n市场:A 股 · 注意 T+1 制度 · 单日 ±10% 涨跌停 · 复权口径为「不复权」"
_SYSTEM_US = _SYSTEM_BASE + "\n\n市场:美股 · T+0 · 无单日涨跌停 · 复权口径为「后复权」"
_SYSTEM_CRYPTO = (
    _SYSTEM_BASE
    + "\n\n市场:加密 · 24/7 · 无涨跌停 · 关注资金费率 / 链上数据(但当前 input 暂不含,M2+ 才接)"
)


def _system_prompt(market: Market) -> str:
    return {
        "cn": _SYSTEM_CN,
        "us": _SYSTEM_US,
        "crypto": _SYSTEM_CRYPTO,
    }[market]


# ===== Prompt 构造 =====


def _format_snapshot(snapshot: TechnicalSnapshot) -> str:
    """把 TechnicalSnapshot 转成给 LLM 的紧凑文本 · 节省 token。"""
    lines = [
        f"标的最新价:{snapshot.last_close:.4f}",
        f"最近 5 日趋势:{snapshot.trend_5d}",
        "",
        "## MA 均线",
        f"  MA5={snapshot.ma[5]:.4f}  MA20={snapshot.ma[20]:.4f}  MA60={snapshot.ma[60]:.4f}",
        "## MACD(12,26,9)",
        f"  DIF={snapshot.macd['dif']:.4f}  DEA={snapshot.macd['dea']:.4f}  "
        f"MACD={snapshot.macd['macd']:.4f}",
        "## RSI",
        f"  RSI14={snapshot.rsi.get(14, 0):.2f}",
        "## 布林带(20, 2σ)",
        f"  上轨={snapshot.boll['upper']:.4f}  中轨={snapshot.boll['mid']:.4f}"
        f"  下轨={snapshot.boll['lower']:.4f}",
        "",
        "## 缠论结构摘要",
        f"  笔数量:{snapshot.chan_bi_count}",
        f"  最后一笔方向:{snapshot.chan_last_bi_direction or '无'}",
        f"  中枢数量:{snapshot.chan_zhongshu_count}",
    ]
    if snapshot.chan_recent_buy_sell_points:
        lines.append("## 最近买卖点(czsc 提取)")
        for p in snapshot.chan_recent_buy_sell_points:
            kind = p.get("kind", "?")
            price = p.get("price", 0.0)
            desc = p.get("description", "")
            lines.append(f"  {kind} @ {price:.2f} · {desc}")
    return "\n".join(lines)


# ===== Agent 调用 =====


async def analyze_technical(
    snapshot: TechnicalSnapshot, market: Market,
) -> tuple[AgentScore, int, int, int]:
    """跑技术面 Agent · 返回 (AgentScore, prompt_tokens, completion_tokens, total_tokens)。

    mock 模式时 llm.ainvoke 返回随机化假 JSON · 接口签名不变。
    解析失败时降级为中性评分 + 解释 · 永远不抛异常(0012 § 失败回退)。
    """
    system = _system_prompt(market)
    prompt = _format_snapshot(snapshot)

    resp = await ainvoke(
        prompt=prompt,
        system=system,
        response_format_json=True,
        temperature=0.3,
    )

    score, confidence, rationale, key_levels = _parse_response(resp.content)

    return (
        AgentScore(
            name="technical",
            score=score,
            confidence=confidence,
            rationale=rationale,
            key_levels=key_levels,
        ),
        resp.prompt_tokens,
        resp.completion_tokens,
        resp.total_tokens,
    )


def _parse_response(
    content: str,
) -> tuple[int, float, str, list[float]]:
    """解析 LLM JSON · 失败时降级为中性。"""
    try:
        data = json.loads(content)
        score = int(data.get("score", 0))
        score = max(-100, min(100, score))
        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        rationale = str(data.get("rationale", "(分析内容暂时不可用)"))[:400]
        raw_levels = data.get("key_levels", [])
        if isinstance(raw_levels, list):
            key_levels = [float(x) for x in raw_levels[:4]]
        else:
            key_levels = []
        return score, confidence, rationale, key_levels
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning("[ai.agent.technical] parse failed err=%s content=%s", e, content[:200])
        return 0, 0.3, "(LLM 输出解析失败,本次评分降级为中性)", []


# ===== 综合标签映射(M1 二波 Aggregator 直通,这里也用)=====


def score_to_label(score: int) -> Literal["强多", "弱多", "中性", "弱空", "强空"]:
    """评分 → 5 档标签。"""
    if score >= 60:
        return "强多"
    if score >= 20:
        return "弱多"
    if score > -20:
        return "中性"
    if score > -60:
        return "弱空"
    return "强空"


__all__ = ["analyze_technical", "score_to_label"]
