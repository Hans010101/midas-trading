"""市场周报 · 生成逻辑(P1)。

管道:聚合四市场现成快照数据 → ★占位 prompt 调 ainvoke(mock-aware)→ 强制免责
(validate_advisory + 兜底)→ 存 market_report(status=draft)。

★★ 占位 prompt(WEEKLY_REPORT_SYSTEM):本刀只验证生成→复核管道,内容是占位的。
   真正的专业报告 prompt（分市场结构 / 趋势研判口径 / 风格）待【内容设计立项】单独替换。

🔴 红线:报告属 AI/策略输出 → 免责语「仅供参考,不构成投资建议」强制必带(ADR 0012)。
   validate_advisory 清营销违规 + _ensure_disclaimer 兜底保证免责串存在(双保险)。

资源:被 worker 任务(tasks/report.py)与 admin 手动触发端点共用,各自传入 session + ch。
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_report import MarketReport
from app.services.ai.llm import ainvoke, is_mock_mode
from app.services.ai.validator import validate_advisory
from app.services.clickhouse_client import ClickHouseClient
from app.services.clickhouse_market_home import select_latest_indices
from app.services.clickhouse_overview import select_latest_overview
from app.services.market_home_config import (
    CN_INDEX_CODES,
    HK_INDEX_CODES,
    US_INDEX_ORDER,
)
from app.services.report.materials import build_materials_text

logger = logging.getLogger(__name__)

DISCLAIMER = "仅供参考,不构成投资建议。"

# ════════════════════════════════════════════════════════════════════════════
# ★★ 占位 prompt —— 待【内容设计立项】替换成专业报告 prompt（分市场 / 趋势口径 / 风格）。
#    本刀仅用最简提示验证「定时生成 → 存草稿 → admin 复核」管道。★勿当成最终报告设计。
# ════════════════════════════════════════════════════════════════════════════
WEEKLY_REPORT_SYSTEM = (
    "你是市场动态分析助手。根据提供的四市场(加密 / 美股 / A股 / 港股)行情数据,"
    "用中文写一段简明、客观的市场动态概述(约 200-400 字),陈述事实与趋势,不做买卖指令。"
    "结尾必须包含一句:仅供参考,不构成投资建议。"
)


def _fmt_quotes(quotes: object, *, limit: int = 6) -> str:
    """把指数 / 概览 quote 列表压成「名称 涨跌幅」一行 · 防御访问字段(缺则略过)。"""
    if not isinstance(quotes, list) or not quotes:
        return "(暂无数据)"
    parts: list[str] = []
    for q in quotes[:limit]:
        name = getattr(q, "name", None) or getattr(q, "symbol", "")
        pct = getattr(q, "change_pct", None)
        if not name:
            continue
        parts.append(f"{name} {pct:+.2f}%" if isinstance(pct, (int, float)) else str(name))
    return " · ".join(parts) if parts else "(暂无数据)"


async def aggregate_market_snapshot(ch: ClickHouseClient) -> str:
    """聚合四市场现成快照 → 喂给 prompt 的文本摘要。

    ★每段独立 try/except(空 CH / 上游缺数据不崩管道,退化为「暂无数据」)·
    ★本刀只取指数 + 全球概览(现成稳查询);全量四市场细化数据待内容立项充实。
    """
    raw = ch._client  # noqa: SLF001 · 复用 API 侧同款(select_* 收 raw AsyncClient)
    lines: list[str] = []

    async def _indices(market: str, order: tuple[str, ...], label: str) -> None:
        try:
            items = await select_latest_indices(raw, market=market, order=order)  # type: ignore[arg-type]
            lines.append(f"【{label}指数】{_fmt_quotes(items)}")
        except Exception:  # noqa: BLE001
            logger.warning("[report] 聚合 %s 指数失败(退化暂无数据)", label)
            lines.append(f"【{label}指数】(暂无数据)")

    await _indices("cn", CN_INDEX_CODES, "A股")
    await _indices("us", US_INDEX_ORDER, "美股")
    await _indices("hk", HK_INDEX_CODES, "港股")
    try:
        overview = await select_latest_overview(raw)
        lines.append(f"【全球概览(含加密/商品/外汇)】{_fmt_quotes(overview, limit=10)}")
    except Exception:  # noqa: BLE001
        logger.warning("[report] 聚合全球概览失败(退化暂无数据)")
        lines.append("【全球概览】(暂无数据)")

    return "\n".join(lines)


def _ensure_disclaimer(text: str) -> str:
    """★免责红线兜底:先 validate_advisory 清营销违规,再保证免责串存在(LLM 漏写也补上)。"""
    cleaned = validate_advisory(text).strip()
    if "不构成投资建议" not in cleaned:
        cleaned = f"{cleaned}\n\n{DISCLAIMER}"
    return cleaned


def current_report_period(now: datetime | None = None) -> tuple[date, date]:
    """本期周报周期(period_start, period_end)= 自然周回看 7 天 · 上传素材与生成共用同口径。"""
    now = now or datetime.now(tz=UTC)
    period_end = now.date()
    return period_end - timedelta(days=6), period_end


async def generate_weekly_report_draft(
    session: AsyncSession,
    ch: ClickHouseClient,
    *,
    now: datetime | None = None,
    materials_text: str | None = None,
) -> MarketReport:
    """生成一篇市场周报草稿(status=draft)并落库 · 返回新建行。

    mock 模式(无 DEEPSEEK_API_KEY)走 ainvoke 的 mock 路径,不烧钱、管道照通。
    ★素材注入:materials_text 缺省时拉本期素材(截断 + 预算守卫);无素材优雅降级(只用平台数据)。
    """
    now = now or datetime.now(tz=UTC)
    period_start, period_end = current_report_period(now)

    data_text = await aggregate_market_snapshot(ch)
    if materials_text is None:
        materials_text = await build_materials_text(session, period_start=period_start, now=now)

    materials_block = (
        f"参考素材(运营搜集 · 优先据此并结合行情数据):\n{materials_text}\n\n"
        if materials_text.strip()
        else ""
    )
    user_prompt = (
        f"报告周期:{period_start.isoformat()} ~ {period_end.isoformat()}\n\n"
        f"四市场行情数据:\n{data_text}\n\n"
        f"{materials_block}"
        "请基于以上数据写一段市场动态概述。"
    )

    resp = await ainvoke(user_prompt, system=WEEKLY_REPORT_SYSTEM, max_tokens=800, temperature=0.4)
    content = _ensure_disclaimer(resp.content)

    title = f"市场周报 · {period_start.isoformat()} ~ {period_end.isoformat()}"
    report = MarketReport(
        title=title,
        content=content,
        status="draft",
        period_start=period_start,
        period_end=period_end,
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    logger.info(
        "[report] 生成周报草稿 id=%s mock=%s 周期=%s~%s",
        report.id, is_mock_mode(), period_start, period_end,
    )
    return report
