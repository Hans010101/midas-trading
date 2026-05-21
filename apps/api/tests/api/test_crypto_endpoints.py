"""`/api/v1/crypto/*` 路由层测试(M2-A 骨架 · M2-B 联调时补全)。

M2-A 范围:确认路由注册成功 · 响应 schema 大致符合契约。
M2-B 实装:补完整端到端测试(用 conftest 注入 mock ClickHouseClient)。

当前测试都标 @pytest.mark.skip · 因为 ClickHouseClient fixture 需要 M2-B
完善(目前 conftest 没注入 mock CH 数据)。
"""

from __future__ import annotations

import pytest


# ============================================================================
# overview
# ============================================================================


@pytest.mark.skip(reason="M2-A 骨架 · 需要 conftest 注入 mock ClickHouse 数据 · M2-B 补")
@pytest.mark.asyncio
async def test_get_overview_returns_stub_when_no_data() -> None:
    """没数据时应返 stub MarketOverview · 不该 500。"""
    pass


@pytest.mark.skip(reason="M2-A 骨架 · 需要 mock CH 数据 · M2-B 补")
@pytest.mark.asyncio
async def test_get_overview_returns_top_gainers_when_data_present() -> None:
    """有数据时应返 top 5 gainers / losers / volume。"""
    pass


# ============================================================================
# tickers/24h
# ============================================================================


@pytest.mark.skip(reason="M2-A 骨架 · M2-B 补")
@pytest.mark.asyncio
async def test_tickers_24h_default_sort_change_pct_desc() -> None:
    """默认 sort_by=change_pct_24h · order=desc · 第一个应该是涨幅最高的。"""
    pass


@pytest.mark.skip(reason="M2-A 骨架 · M2-B 补")
@pytest.mark.asyncio
async def test_tickers_24h_top_n_caps_at_100() -> None:
    """top 参数应 Pydantic 校验 le=100 · 超过返 422。"""
    pass


# ============================================================================
# futures endpoints
# ============================================================================


@pytest.mark.skip(reason="M2-A 骨架 · M2-B 补")
@pytest.mark.asyncio
async def test_funding_rate_returns_asc_sorted() -> None:
    """funding rate 端点返 ASC 升序(继承 0010 教训)。"""
    pass


@pytest.mark.skip(reason="M2-A 骨架 · M2-B 补")
@pytest.mark.asyncio
async def test_long_short_ratio_returns_three_metric_sets() -> None:
    """单个 LongShortRatio 应包含 top_account / top_position / taker 三套指标。"""
    pass


@pytest.mark.skip(reason="M2-A 骨架 · futures/info 需要 M2-B 回源 · 现在是 stub")
@pytest.mark.asyncio
async def test_futures_info_returns_404_when_no_data() -> None:
    """没 funding / OI 数据时 · futures/info 返 404。"""
    pass


# ============================================================================
# fear-greed
# ============================================================================


@pytest.mark.skip(reason="M2-A 骨架 · M2-B 补")
@pytest.mark.asyncio
async def test_fear_greed_returns_daily_dedup() -> None:
    """同一天多条 FGI · argMax(ts) 去重 · 一天一行。"""
    pass


# ============================================================================
# 红线 · 路由层不应有任何 POST/PUT/DELETE 端点
# ============================================================================


def test_crypto_router_has_no_write_endpoints() -> None:
    """加密 router 全部 GET · 任何 trade / write 动作都不应在此 router。

    红线:本测试是「合规守门」· 防 M2-B/C 误加端点。
    """
    from app.api.v1.crypto import router

    for route in router.routes:
        methods = getattr(route, "methods", set())
        # 排除 HEAD/OPTIONS(FastAPI 自动注册)
        non_safe = methods - {"GET", "HEAD", "OPTIONS"}
        assert not non_safe, (
            f"路由 {route.path} 包含非 GET 方法 {non_safe} · "
            "Crypto API 应只读 · 交易动作走 /api/v1/virtual"
        )
