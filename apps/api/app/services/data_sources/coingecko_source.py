"""CoinGecko 全市场 overview 数据源(0017 ADR · M2-A)。

只用 `/api/v3/global` 一个 endpoint · 拉全市场总市值 / dominance / 衍生品总量。

为什么不用 ccxt:ccxt 是交易所抽象 · CoinGecko 是聚合数据服务 · 不在 ccxt 范围。
为什么用 CoinGecko:免费档 30 req/min · 5min/次刚好 12/h · 余量极大。
数据维度比 Binance 自己的 ticker 更完整(跨交易所聚合 + dominance 计算)。

API key 可选:
- 免费 demo plan (无 key):30 req/min · 公共 endpoint
- 付费 pro plan(API key):更高频率(M2 暂不付费)

红线:全部 GET endpoint · 无 trade · 无任何敏感动作。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.schemas.crypto import MarketOverview
from app.services.data_sources.base import BaseDataSource
from app.services.data_sources.exceptions import (
    DataFormatError,
    RateLimitError,
    UpstreamUnavailableError,
)

logger = logging.getLogger(__name__)


class CoinGeckoSource(BaseDataSource):
    """CoinGecko 全市场 overview adapter。"""

    name = "coingecko"
    market = "crypto"

    def __init__(
        self,
        *,
        base_url: str = "https://api.coingecko.com/api/v3",
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self._base_url}{path}"
        headers: dict[str, str] = {}
        if self._api_key:
            # CoinGecko Pro 在 header 传 key
            headers["x-cg-pro-api-key"] = self._api_key
        try:
            resp = await self._client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(
                f"CoinGecko 网络错: {type(exc).__name__}: {exc}",
                market="crypto", upstream="coingecko",
            ) from exc

        if resp.status_code == 429:
            raise RateLimitError(
                "CoinGecko 限流 · HTTP 429",
                market="crypto", upstream="coingecko",
            )
        if 500 <= resp.status_code < 600:
            raise UpstreamUnavailableError(
                f"CoinGecko 5xx · HTTP {resp.status_code}",
                market="crypto", upstream="coingecko",
            )
        if not resp.is_success:
            raise DataFormatError(
                f"CoinGecko 非预期响应 · HTTP {resp.status_code} body={resp.text[:200]}",
                market="crypto", upstream="coingecko",
            )

        try:
            return resp.json()
        except ValueError as exc:
            raise DataFormatError(
                f"CoinGecko 响应非 JSON: {resp.text[:200]}",
                market="crypto", upstream="coingecko",
            ) from exc

    async def fetch_global_overview(self) -> MarketOverview:
        """`/api/v3/global` · 全市场总览。

        返回结构(摘):
        {
          "data": {
            "active_cryptocurrencies": ...,
            "total_market_cap": {"usd": ..., "btc": ..., ...},
            "total_volume": {"usd": ..., ...},
            "market_cap_percentage": {"btc": 50.x, "eth": 18.x, ...}
          }
        }
        """
        async def _do() -> MarketOverview:
            body = await self._get_json("/global")
            try:
                d = body["data"]
                # CoinGecko derivatives 单独 endpoint /derivatives/exchanges · M2-A 不接
                # FGI 来源是 alternative.me · 这里先留 0 · 由 Celery 任务合并写入
                return MarketOverview(
                    ts=datetime.now(tz=UTC),
                    total_market_cap_usd=float(d["total_market_cap"]["usd"]),
                    total_volume_24h_usd=float(d["total_volume"]["usd"]),
                    btc_dominance=float(d["market_cap_percentage"]["btc"]),
                    eth_dominance=float(d["market_cap_percentage"]["eth"]),
                    fear_greed_value=0,             # 由 alternative_me 合并填
                    fear_greed_classification="",   # 同上
                    derivatives_oi_usd=0,           # 留 v2 · 需要单独 endpoint
                    derivatives_volume_24h_usd=0,
                )
            except (KeyError, ValueError, TypeError) as exc:
                keys = list(body.keys()) if isinstance(body, dict) else type(body)
                raise DataFormatError(
                    f"CoinGecko /global 解析失败: {exc} · body keys={keys}",
                    market="crypto", upstream="coingecko",
                ) from exc

        return await self._retry(op="fetch_global_overview", symbol="*", coro_factory=_do)

    # BaseDataSource 抽象方法兜底
    async def fetch_kline(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("CoinGeckoSource 不提供 K 线 · 只有 global overview")

    async def list_symbols(self) -> Any:
        raise NotImplementedError("CoinGeckoSource 不提供 symbol_meta")
