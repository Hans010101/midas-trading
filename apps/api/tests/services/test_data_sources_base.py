"""BaseDataSource._retry helper 的行为测试。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.schemas.market import Kline, Period, SymbolMeta
from app.services.data_sources.base import BaseDataSource
from app.services.data_sources.exceptions import (
    DataFormatError,
    RateLimitError,
    SymbolNotFoundError,
    UpstreamUnavailableError,
)


class _FakeSource(BaseDataSource):
    """测试用空实现,只暴露 _retry。"""

    name = "fake"
    market = "cn"

    async def fetch_kline(self, symbol: str, period: Period, *, limit: int = 500) -> list[Kline]:  # noqa: ARG002
        return []

    async def list_symbols(self) -> list[SymbolMeta]:
        return []


@pytest.fixture
def src(monkeypatch: pytest.MonkeyPatch) -> _FakeSource:
    # 把 asyncio.sleep 替换成 no-op,跑测试不真等
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    return _FakeSource()


class TestRetry:
    async def test_success_first_try(self, src: _FakeSource) -> None:
        async def _ok() -> str:
            return "ok"

        result = await src._retry(op="test", symbol="600519", coro_factory=_ok)
        assert result == "ok"

    async def test_retry_then_succeed(self, src: _FakeSource) -> None:
        calls = {"count": 0}

        async def _flaky() -> str:
            calls["count"] += 1
            if calls["count"] < 3:
                raise UpstreamUnavailableError("timeout", symbol="600519")
            return "ok"

        result = await src._retry(op="test", symbol="600519", coro_factory=_flaky)
        assert result == "ok"
        assert calls["count"] == 3

    async def test_exhaust_retries(self, src: _FakeSource) -> None:
        async def _always_fail() -> str:
            raise UpstreamUnavailableError("永久挂", symbol="600519")

        with pytest.raises(UpstreamUnavailableError, match="永久挂"):
            await src._retry(op="test", symbol="600519", coro_factory=_always_fail)

    async def test_rate_limit_is_retried(self, src: _FakeSource) -> None:
        """RateLimitError 继承 UpstreamUnavailableError,应同样被重试。"""
        calls = {"count": 0}

        async def _rate_limited() -> str:
            calls["count"] += 1
            if calls["count"] < 2:
                raise RateLimitError("429", symbol="600519")
            return "ok"

        result = await src._retry(op="test", symbol="600519", coro_factory=_rate_limited)
        assert result == "ok"
        assert calls["count"] == 2

    async def test_symbol_not_found_not_retried(self, src: _FakeSource) -> None:
        """终态错误不重试,直接上抛。"""
        calls = {"count": 0}

        async def _not_found() -> str:
            calls["count"] += 1
            raise SymbolNotFoundError("XYZ 不存在", symbol="XYZ")

        with pytest.raises(SymbolNotFoundError):
            await src._retry(op="test", symbol="XYZ", coro_factory=_not_found)
        assert calls["count"] == 1  # 只调一次

    async def test_data_format_error_not_retried(self, src: _FakeSource) -> None:
        calls = {"count": 0}

        async def _bad_format() -> str:
            calls["count"] += 1
            raise DataFormatError("字段缺失", symbol="600519")

        with pytest.raises(DataFormatError):
            await src._retry(op="test", symbol="600519", coro_factory=_bad_format)
        assert calls["count"] == 1
