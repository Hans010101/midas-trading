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
from app.services.ai.language_lock import LANGUAGE_LOCK_RETRY_PREFIX, contains_cjk
from app.services.ai.llm import ainvoke
from app.services.ai.prompts_en import TECHNICAL_SYSTEM_EN

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
    # 🔴 事件日程层 P0 红线(锁死):事件只是波动风险背景,绝不是方向依据
    "若输入含「重大事件」段:只能将其作为事件前后波动可能放大的风险背景提示,"
    "**绝不能据此给出任何方向判断或操作暗示**(不因事件临近而看多或看空)。\n"
    "**必须严格返回 JSON,不能有其他文本。**"
)

_SYSTEM_CN = _SYSTEM_BASE + (
    "\n\n市场:A 股 · 注意 T+1 制度 · 单日 ±10% 涨跌停 · 复权口径为「不复权」"
)
_SYSTEM_US = _SYSTEM_BASE + "\n\n市场:美股 · T+0 · 无单日涨跌停 · 复权口径为「后复权」"
_SYSTEM_CRYPTO = (
    _SYSTEM_BASE
    + "\n\n市场:加密 · 24/7 · 无涨跌停 · 关注资金费率 / 链上数据(但当前 input 暂不含,M2+ 才接)"
)
_SYSTEM_HK = (
    _SYSTEM_BASE
    + "\n\n市场:港股 · T+0 · 无涨跌停 · 复权「前复权」qfq · 按手 board lot 交易"
)


def _system_prompt(market: Market, language: str = "zh") -> str:
    # ★i18n Phase4:language 分发 · zh 走现有中文常量【一字不动】;en 走 prompts_en(新增常量)。
    #   默认 zh → 命中的永远是逐字节相同的中文常量(zh 零变化红线)。
    if language == "en":
        return TECHNICAL_SYSTEM_EN[market]
    return {
        "cn": _SYSTEM_CN,
        "us": _SYSTEM_US,
        "crypto": _SYSTEM_CRYPTO,
        "hk": _SYSTEM_HK,
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
        (
            f"  DIF={snapshot.macd['dif']:.4f}  DEA={snapshot.macd['dea']:.4f}  "
            f"MACD={snapshot.macd['macd']:.4f}"
        ),
        "## RSI",
        f"  RSI14={snapshot.rsi.get(14, 0):.2f}",
        "## 布林带(20, 2σ)",
        (
            f"  上轨={snapshot.boll['upper']:.4f}  中轨={snapshot.boll['mid']:.4f}"
            f"  下轨={snapshot.boll['lower']:.4f}"
        ),
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
    # 事件日程层 P0:预格式化事件段(自带「仅风险背景·绝不给方向」红线尾句)· 空串零变化
    if snapshot.econ_events_context:
        lines.append(snapshot.econ_events_context)
    return "\n".join(lines)


def _format_snapshot_en(snapshot: TechnicalSnapshot) -> str:
    """英文标签版 snapshot(i18n Phase4 刀2)· 数字与 zh 版一字不差,只英文化标签。

    ★为什么单独一版:zh _format_snapshot 全中文标签,喂给英文 system prompt = 串台诱因。
    英文标签的输入 + 英文 system = 全英文管道,降低 DeepSeek 回中文的概率(语言锁第一层的配套)。
    """
    lines = [
        f"Last price: {snapshot.last_close:.4f}",
        f"5-day trend: {snapshot.trend_5d}",
        "",
        "## MA",
        f"  MA5={snapshot.ma[5]:.4f}  MA20={snapshot.ma[20]:.4f}  MA60={snapshot.ma[60]:.4f}",
        "## MACD(12,26,9)",
        (
            f"  DIF={snapshot.macd['dif']:.4f}  DEA={snapshot.macd['dea']:.4f}  "
            f"MACD={snapshot.macd['macd']:.4f}"
        ),
        "## RSI",
        f"  RSI14={snapshot.rsi.get(14, 0):.2f}",
        "## Bollinger Bands (20, 2σ)",
        (
            f"  upper={snapshot.boll['upper']:.4f}  mid={snapshot.boll['mid']:.4f}"
            f"  lower={snapshot.boll['lower']:.4f}"
        ),
        "",
        "## Chan Theory structure",
        f"  Stroke count: {snapshot.chan_bi_count}",
        f"  Last stroke direction: {snapshot.chan_last_bi_direction or 'none'}",
        f"  Central Hub count: {snapshot.chan_zhongshu_count}",
    ]
    if snapshot.chan_recent_buy_sell_points:
        lines.append("## Recent buy/sell points (czsc)")
        for p in snapshot.chan_recent_buy_sell_points:
            kind = p.get("kind", "?")
            price = p.get("price", 0.0)
            desc = p.get("description", "")
            lines.append(f"  {kind} @ {price:.2f} · {desc}")
    # Econ calendar P0: pre-formatted events section (carries its own risk-only red-line tail)
    if snapshot.econ_events_context:
        lines.append(snapshot.econ_events_context)
    return "\n".join(lines)


# ===== Agent 调用 =====


async def analyze_technical(
    snapshot: TechnicalSnapshot, market: Market, *, language: str = "zh",
) -> tuple[AgentScore, int, int, int]:
    """跑技术面 Agent · 返回 (AgentScore, prompt_tokens, completion_tokens, total_tokens)。

    mock 模式时 llm.ainvoke 返回随机化假 JSON · 接口签名不变。
    解析失败时降级为中性评分 + 解释 · 永远不抛异常(0012 § 失败回退)。

    ★i18n Phase4:language 默认 zh(走现有中文 prompt·逐字节不变)· en 走英文 prompt + 语言锁双层。
    """
    system = _system_prompt(market, language)
    prompt = _format_snapshot_en(snapshot) if language == "en" else _format_snapshot(snapshot)

    resp = await ainvoke(
        prompt=prompt,
        system=system,
        response_format_json=True,
        temperature=0.3,
    )

    score, confidence, rationale, key_levels = _parse_response(resp.content)
    prompt_tokens, completion_tokens, total_tokens = (
        resp.prompt_tokens, resp.completion_tokens, resp.total_tokens,
    )

    # ★语言锁第二层(仅 en · zh 不进此分支 = 零变化):CJK 检出 → 重试一次 → 仍中文则降级英文兜底。
    if language == "en" and contains_cjk(rationale):
        logger.warning("[ai.agent.technical] en 输出含中文(串台)· 加强语言锁重试一次")
        resp2 = await ainvoke(
            prompt=LANGUAGE_LOCK_RETRY_PREFIX + prompt,
            system=system,
            response_format_json=True,
            temperature=0.3,
        )
        s2, c2, r2, k2 = _parse_response(resp2.content)
        prompt_tokens += resp2.prompt_tokens
        completion_tokens += resp2.completion_tokens
        total_tokens += resp2.total_tokens
        if contains_cjk(r2):
            # 重试仍串台 → 降级:数值(评分/价位)语言中立保留,自由文本换英文兜底(标记)。
            logger.warning("[ai.agent.technical] en 重试仍含中文 · 降级英文兜底 rationale")
            score, confidence, key_levels = s2, c2, k2
            rationale = _en_degrade_rationale(s2)
        else:
            score, confidence, rationale, key_levels = s2, c2, r2, k2

    return (
        AgentScore(
            name="technical",
            score=score,
            confidence=confidence,
            rationale=rationale,
            key_levels=key_levels,
        ),
        prompt_tokens,
        completion_tokens,
        total_tokens,
    )


def _score_to_label_en(score: int) -> str:
    """评分 → 5 档英文标签(仅用于串台降级兜底 rationale · 不改卡片 composite_label)。"""
    if score >= 60:
        return "Strong-Long"
    if score >= 20:
        return "Mild-Long"
    if score > -20:
        return "Neutral"
    if score > -60:
        return "Mild-Short"
    return "Strong-Short"


def _en_degrade_rationale(score: int) -> str:
    """串台降级时的安全英文 rationale(数值仍有效 · 免责由 workflow validator 兜底追加)。"""
    return (
        f"Composite technical read: {_score_to_label_en(score)}. Derived from MA / MACD / RSI / "
        "Bollinger Bands and Chan Theory structure signals."
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
        key_levels = [float(x) for x in raw_levels[:4]] if isinstance(raw_levels, list) else []
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
