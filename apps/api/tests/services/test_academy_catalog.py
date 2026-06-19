"""训练营文章目录 catalog pytest · B 期刀1(纯逻辑 · 无 DB)。

★ 钉死总数 + 各阶分布 → 训练营加文章漏同步 catalog 时 CI 立刻红(防静默偏移)。
"""

from __future__ import annotations

from app.services.academy.catalog import (
    ACADEMY_ARTICLE_SLUGS,
    STAGE_ORDER,
    STAGE_TOTALS,
    is_valid_slug,
    stage_of,
)

# 镜像 manifest.ts ACADEMY_ARTICLES(2026-06 现状 · 加文章须同步这里)
_EXPECTED_TOTALS = {
    "basics": 11,
    "technical": 9,
    "chan": 29,
    "contract": 20,
    "strategy": 10,
    "system": 38,
}
_EXPECTED_TOTAL = 117


def test_total_article_count() -> None:
    assert len(ACADEMY_ARTICLE_SLUGS) == _EXPECTED_TOTAL


def test_stage_totals_match() -> None:
    assert STAGE_TOTALS == _EXPECTED_TOTALS
    assert sum(STAGE_TOTALS.values()) == _EXPECTED_TOTAL


def test_stage_order_covers_all_stages() -> None:
    assert set(STAGE_ORDER) == set(_EXPECTED_TOTALS)
    assert len(STAGE_ORDER) == len(_EXPECTED_TOTALS)


def test_is_valid_slug() -> None:
    assert is_valid_slug("A2") is True
    assert is_valid_slug("C1-1") is True
    assert is_valid_slug("F38") is True
    assert is_valid_slug("ZZZ99") is False
    assert is_valid_slug("") is False
    assert is_valid_slug("'; DROP TABLE academy_progress;--") is False


def test_stage_of() -> None:
    assert stage_of("A2") == "basics"
    assert stage_of("C1-1") == "chan"
    assert stage_of("C2-1") == "contract"   # ★ C2-* 归合约(非缠论)
    assert stage_of("C3-1") == "strategy"   # ★ C3-* 归策略
    assert stage_of("F1") == "system"
    assert stage_of("UNKNOWN") is None
