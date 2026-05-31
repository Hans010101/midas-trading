"""AI 命中率只读 API pytest · GET /api/v1/analysis/ai-accuracy(0036 批次乙 C)。

端到端验证(HTTP → 路由 → service → 响应 schema):
- 200 + 响应结构(总体 + 三维分桶 + min_reliable_sample + note)。
- 无样本时 hit_rate=None(不报错)。
- since_days / llm_mode query 参数透传回显。
- ★ 只读:端点不需要鉴权 / CH / 数据源(只读 PG · client fixture 覆盖 get_db 即可)。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_analysis_memory import AIAnalysisMemory

_NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)


async def _seed(db: AsyncSession, *, market: str, was_correct: bool) -> None:
    db.add(
        AIAnalysisMemory(
            symbol="NVDA",
            market=market,
            instrument="spot",
            period="1d",
            analyzed_at=_NOW - timedelta(days=10),
            direction="bull",
            composite_score=60,
            composite_label="强多",
            composite_confidence=Decimal("0.7000"),
            price_at=Decimal("100"),
            llm_mode="mock",
            reflected_at=_NOW - timedelta(days=3),
            price_after=Decimal("110"),
            actual_return=Decimal("0.1"),
            was_correct=was_correct,
        ),
    )


@pytest.mark.asyncio
async def test_ai_accuracy_endpoint_returns_stats(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """端到端:2 对 1 错 → 总体 66.7% · 结构完整。"""
    await _seed(db_session, market="us", was_correct=True)
    await _seed(db_session, market="us", was_correct=True)
    await _seed(db_session, market="us", was_correct=False)
    await db_session.commit()

    resp = await client.get("/api/v1/analysis/ai-accuracy")
    assert resp.status_code == 200
    data = resp.json()

    assert data["overall_sample_count"] == 3
    assert data["overall_correct_count"] == 2
    assert data["overall_hit_rate"] == pytest.approx(2 / 3)
    # 三维分桶都在
    assert {b["key"] for b in data["by_market"]} == {"cn", "us", "crypto"}
    assert {b["key"] for b in data["by_direction"]} == {"bull", "bear", "flat"}
    assert len(data["by_confidence"]) == 6
    assert data["min_reliable_sample"] >= 1
    assert data["note"]
    # ★ 小样本诚实标注
    us = next(b for b in data["by_market"] if b["key"] == "us")
    assert us["reliable"] is False  # 3 条 < 阈值


@pytest.mark.asyncio
async def test_ai_accuracy_endpoint_empty(client: AsyncClient) -> None:
    """无数据 → 200 · overall_hit_rate=None(不报错 · 不返回 0%)。"""
    resp = await client.get("/api/v1/analysis/ai-accuracy")
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_sample_count"] == 0
    assert data["overall_hit_rate"] is None


@pytest.mark.asyncio
async def test_ai_accuracy_endpoint_query_params(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    """since_days / llm_mode query 参数回显。"""
    await _seed(db_session, market="us", was_correct=True)
    await db_session.commit()

    resp = await client.get(
        "/api/v1/analysis/ai-accuracy", params={"since_days": 90, "llm_mode": "mock"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["since_days"] == 90
    assert data["llm_mode_filter"] == "mock"
    assert data["overall_sample_count"] == 1


@pytest.mark.asyncio
async def test_ai_accuracy_endpoint_rejects_bad_llm_mode(client: AsyncClient) -> None:
    """非法 llm_mode → 422(schema 校验)。"""
    resp = await client.get(
        "/api/v1/analysis/ai-accuracy", params={"llm_mode": "bogus"},
    )
    assert resp.status_code == 422
