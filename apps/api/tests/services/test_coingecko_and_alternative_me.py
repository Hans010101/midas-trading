"""CoinGecko + alternative.me 两个 source 的单元测试。

全部 httpx.MockTransport · 不打外网。M2-A 范围覆盖核心解析 + 错误映射。
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.data_sources.alternative_me_source import AlternativeMeSource
from app.services.data_sources.coingecko_source import CoinGeckoSource
from app.services.data_sources.exceptions import (
    DataFormatError,
    RateLimitError,
    UpstreamUnavailableError,
)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())


def _gecko(handler: Any) -> CoinGeckoSource:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return CoinGeckoSource(client=client)


def _altme(handler: Any) -> AlternativeMeSource:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return AlternativeMeSource(client=client)


# ============================================================================
# CoinGecko
# ============================================================================


@pytest.mark.asyncio
async def test_coingecko_global_parses_nested_structure() -> None:
    """`/global` 返 {data: {...}} 结构 · 解析 BTC dominance 和 total market cap。"""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": {
                "total_market_cap": {"usd": 2500000000000.0, "btc": 41000000.0},
                "total_volume": {"usd": 80000000000.0},
                "market_cap_percentage": {"btc": 52.5, "eth": 17.2},
            },
        })

    src = _gecko(handler)
    try:
        ov = await src.fetch_global_overview()
        assert ov.total_market_cap_usd == 2_500_000_000_000.0
        assert ov.btc_dominance == 52.5
        assert ov.eth_dominance == 17.2
        # FGI / derivatives 字段先留 0(由其他 adapter 合并)
        assert ov.fear_greed_value == 0
        assert ov.derivatives_oi_usd == 0
    finally:
        await src.close()


@pytest.mark.asyncio
async def test_coingecko_429_maps_to_rate_limit() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    src = _gecko(handler)
    try:
        with pytest.raises(RateLimitError):
            await src.fetch_global_overview()
    finally:
        await src.close()


@pytest.mark.asyncio
async def test_coingecko_malformed_response_raises_format_error() -> None:
    """data 字段缺 market_cap_percentage 时 · 应抛 DataFormatError。"""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"total_market_cap": {"usd": 1}}})

    src = _gecko(handler)
    try:
        with pytest.raises(DataFormatError):
            await src.fetch_global_overview()
    finally:
        await src.close()


# ============================================================================
# alternative.me Fear & Greed
# ============================================================================


@pytest.mark.asyncio
async def test_altme_fgi_parses_and_sorts_ascending() -> None:
    """alternative.me 返 newest first · adapter 应返 ASC 升序。"""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": [
                {"value": "70", "value_classification": "Greed", "timestamp": "1716316800"},
                {"value": "65", "value_classification": "Greed", "timestamp": "1716230400"},
                {"value": "55", "value_classification": "Neutral", "timestamp": "1716144000"},
            ],
        })

    src = _altme(handler)
    try:
        series = await src.fetch_fear_greed(limit=3)
        assert len(series) == 3
        # 应该是 ASC(最早在前)
        assert series[0].value == 55
        assert series[1].value == 65
        assert series[2].value == 70
        assert series[0].ts < series[1].ts < series[2].ts
    finally:
        await src.close()


@pytest.mark.asyncio
async def test_altme_handles_malformed_entries_gracefully() -> None:
    """单行解析失败 · skip · 不抛 · 继续返其余有效数据。"""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": [
                {"value": "70", "value_classification": "Greed", "timestamp": "1716316800"},
                {"value": "BAD"},   # 缺 timestamp + value 非数字 · skip
                {"value": "55", "value_classification": "Neutral", "timestamp": "1716144000"},
            ],
        })

    src = _altme(handler)
    try:
        series = await src.fetch_fear_greed(limit=3)
        assert len(series) == 2   # 中间的坏行被 skip
    finally:
        await src.close()


@pytest.mark.asyncio
async def test_altme_500_raises_upstream_unavailable() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="busy")

    src = _altme(handler)
    try:
        with pytest.raises(UpstreamUnavailableError):
            await src.fetch_fear_greed(limit=5)
    finally:
        await src.close()
