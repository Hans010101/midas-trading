"""KLINE-001 K线图 PNG 端点测试 · GET /api/v1/chart/kline.png。

fake CH(不连真库)· 数据不足 → 404(调用方回退链接)· 充足 → 200 image/png(真跑渲染器出 PNG)。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.api.deps import get_clickhouse
from app.main import app
from app.schemas.market import Kline

_BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _klines(n: int) -> list[Kline]:
    out: list[Kline] = []
    price = 100.0
    for i in range(n):
        drift = 0.02 if i % 3 == 0 else (-0.015 if i % 3 == 1 else 0.005)
        close = max(1.0, price * (1 + drift))
        out.append(Kline(ts=_BASE + timedelta(days=i), open=round(price, 4),
                         high=round(max(price, close) * 1.008, 4),
                         low=round(min(price, close) * 0.992, 4),
                         close=round(close, 4), volume=1000.0 + i))
        price = close
    return out


class _FakeCH:
    def __init__(self, klines: list[Kline]) -> None:
        self._klines = klines

    async def select_kline(self, **_kwargs: Any) -> list[Kline]:  # noqa: ANN401
        return self._klines


def _override(klines: list[Kline]) -> None:
    app.dependency_overrides[get_clickhouse] = lambda: _FakeCH(klines)


@pytest.fixture(autouse=True)
def _clear() -> Any:  # noqa: ANN401
    yield
    app.dependency_overrides.pop(get_clickhouse, None)


@pytest.mark.asyncio
async def test_chart_insufficient_data_404(client: AsyncClient) -> None:
    """K线 < 30 根 → 404(bot 据此回退网页链接)。"""
    _override(_klines(10))
    r = await client.get("/api/v1/chart/kline.png?market=cn&symbol=600519&name=贵州茅台")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_chart_sufficient_returns_png(client: AsyncClient) -> None:
    """K线充足 → 200 + image/png(真跑渲染器出 PNG)。"""
    _override(_klines(120))
    r = await client.get("/api/v1/chart/kline.png?market=cn&symbol=600519&name=贵州茅台")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
