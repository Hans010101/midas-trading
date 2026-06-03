"""GET /api/v1/cn/search 端点守护测试(空 q / 空白 / 限量校验 / happy-path 接线)。

★ 不连真 CH:override get_clickhouse 为 fake(返回预置行)· 校验端点参数校验 + strip 守护 + 序列化。
   搜索匹配行为(命中代码/中文名/大小写/降序/限量)在 tests/services/test_cn_search.py 用真 CH 覆盖。
★ 红线:只读端点 · 无写动作。
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app.api.deps import get_clickhouse
from app.main import app


class _FakeRawClient:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    async def query(self, sql: str, parameters: dict[str, Any] | None = None) -> Any:  # noqa: ANN401, ARG002
        class _Result:
            result_rows: list[tuple[Any, ...]]

        r = _Result()
        r.result_rows = self._rows
        return r


class _FakeCh:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._client = _FakeRawClient(rows)


def _override(rows: list[tuple[Any, ...]]) -> None:
    app.dependency_overrides[get_clickhouse] = lambda: _FakeCh(rows)


@pytest.fixture(autouse=True)
def _clear_ch_override():  # noqa: ANN202
    yield
    app.dependency_overrides.pop(get_clickhouse, None)


_ROW = ("600519", "贵州茅台", 1700.0, 1.5, 25.0, 9.0e9, 1.0e6)


@pytest.mark.asyncio
async def test_search_empty_q_returns_422(client: AsyncClient) -> None:
    """空 q(?q=)→ 422(min_length=1)。"""
    _override([])
    r = await client.get("/api/v1/cn/search?q=")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_search_missing_q_returns_422(client: AsyncClient) -> None:
    """缺 q → 422(必填)。"""
    _override([])
    r = await client.get("/api/v1/cn/search")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_search_whitespace_q_returns_empty(client: AsyncClient) -> None:
    """全空白 q → 200 + 空列表(strip 守护 · 不退化成「匹配全部」)。"""
    _override([_ROW])  # 即便 fake 有行,空白守护也应直接返 [] 不查
    r = await client.get("/api/v1/cn/search?q=%20%20")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_search_happy_path_serializes_cnspotrow(client: AsyncClient) -> None:
    """正常命中 → 200 + CnSpotRow 序列化(带价/涨跌)。"""
    _override([_ROW])
    r = await client.get("/api/v1/cn/search?q=600519")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["symbol"] == "600519"
    assert body[0]["name"] == "贵州茅台"
    assert body[0]["last_price"] == 1700.0
    assert body[0]["change_pct"] == 1.5


@pytest.mark.asyncio
async def test_search_limit_over_cap_returns_422(client: AsyncClient) -> None:
    """limit 超上限(le=50)→ 422。"""
    _override([])
    r = await client.get("/api/v1/cn/search?q=test&limit=999")
    assert r.status_code == 422
