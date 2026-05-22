"""alternative.me Fear & Greed Index 数据源(0017 ADR · M2-A)。

只用 `/fng/` 一个 endpoint · 完全免费 · 无 key · 无限流。

返回结构:
{
  "name": "Fear and Greed Index",
  "data": [
    {"value": "70", "value_classification": "Greed", "timestamp": "1716230400"},
    ...
  ]
}

注意 timestamp 是 string,需要 int(...)。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.schemas.crypto import FearGreedPoint
from app.services.data_sources.base import BaseDataSource
from app.services.data_sources.exceptions import (
    DataFormatError,
    UpstreamUnavailableError,
)

logger = logging.getLogger(__name__)


class AlternativeMeSource(BaseDataSource):
    """alternative.me Fear & Greed Index adapter。"""

    name = "alternative-me"
    market = "crypto"

    def __init__(
        self,
        *,
        base_url: str = "https://api.alternative.me",
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_fear_greed(self, *, limit: int = 30) -> list[FearGreedPoint]:
        """最近 `limit` 天的 FGI 时间序列(默认 30 天)。

        alternative.me 数据按天滚动 · 每天 UTC 00:00 更新一次。
        """
        async def _do() -> list[FearGreedPoint]:
            url = f"{self._base_url}/fng/"
            try:
                resp = await self._client.get(url, params={"limit": limit, "format": "json"})
            except httpx.HTTPError as exc:
                raise UpstreamUnavailableError(
                    f"alternative.me 网络错: {type(exc).__name__}: {exc}",
                    market="crypto", upstream="alternative-me",
                ) from exc

            if not resp.is_success:
                raise UpstreamUnavailableError(
                    f"alternative.me HTTP {resp.status_code}",
                    market="crypto", upstream="alternative-me",
                )

            try:
                body = resp.json()
            except ValueError as exc:
                raise DataFormatError(
                    f"alternative.me 响应非 JSON: {resp.text[:200]}",
                    market="crypto", upstream="alternative-me",
                ) from exc

            data = body.get("data", []) if isinstance(body, dict) else []
            if not isinstance(data, list):
                raise DataFormatError(
                    f"alternative.me data 字段非数组: {type(data).__name__}",
                    market="crypto", upstream="alternative-me",
                )

            results: list[FearGreedPoint] = []
            for entry in data:
                try:
                    results.append(FearGreedPoint(
                        ts=datetime.fromtimestamp(int(entry["timestamp"]), tz=UTC),
                        value=int(entry["value"]),
                        classification=str(entry["value_classification"]),
                    ))
                except (KeyError, ValueError, TypeError) as exc:
                    logger.warning("[alternative-me] FGI 行解析失败 skip: %s · %s", entry, exc)
                    continue

            # alternative.me 返回是 newest first · 我们按 ts ASC 升序(跟 K 线契约一致)
            return sorted(results, key=lambda p: p.ts)

        return await self._retry(op="fetch_fear_greed", symbol="*", coro_factory=_do)

    # BaseDataSource 抽象方法兜底
    async def fetch_kline(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("AlternativeMeSource 不提供 K 线 · 只有 FGI")

    async def list_symbols(self) -> Any:
        raise NotImplementedError("AlternativeMeSource 不提供 symbol_meta")
