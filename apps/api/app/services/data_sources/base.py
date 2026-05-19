"""数据源抽象基类。

三家数据源适配器(AKShare / yfinance / ccxt)继承 BaseDataSource,
实现 fetch_kline / list_symbols 两个抽象方法。

基类提供 `_retry` helper:对 UpstreamUnavailableError(含 RateLimitError)
做 3 次指数退避重试(1/5/15 秒),并在 stdout 打详细日志(级别 / 上下游 /
标的 / 尝试次数 / 完整 traceback)。

终态异常(SymbolNotFoundError / DataFormatError)不重试,直接上抛。
"""

from __future__ import annotations

import abc
import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.schemas.market import Kline, Market, Period, SymbolMeta
from app.services.data_sources.exceptions import UpstreamUnavailableError

logger = logging.getLogger(__name__)

R = TypeVar("R")

# 退避策略:首次立即,失败后 1 / 5 / 15 秒重试。总共最多 4 次尝试。
_RETRY_DELAYS: tuple[float, ...] = (0.0, 1.0, 5.0, 15.0)


class BaseDataSource(abc.ABC):
    """三市场数据源的统一接口。子类必须设置 `name` + `market`。

    实现要求:
    - 返回的 Kline 列表必须 ts 升序(最早 → 最新)
    - 所有 ts 字段必须是 tz-aware UTC datetime
    - 失败必须抛 DataSourceError 子类,**严禁返回空列表**
    - 网络 / 限流类失败要包成 UpstreamUnavailableError(或 RateLimitError)
      以便 `_retry` 自动退避
    """

    name: str  # 子类设置:"akshare" / "yfinance" / "ccxt-binance"
    market: Market

    async def _retry(
        self,
        *,
        op: str,
        symbol: str,
        coro_factory: Callable[[], Awaitable[R]],
    ) -> R:
        """指数退避重试。`coro_factory` 每次重新构造一个新的协程。"""
        last_exc: UpstreamUnavailableError | None = None
        max_attempts = len(_RETRY_DELAYS)

        for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
            if delay > 0:
                logger.warning(
                    "[%s] %s symbol=%s · 第 %d/%d 次尝试,等待 %.1fs 后重试。上次失败:%s",
                    self.name,
                    op,
                    symbol,
                    attempt,
                    max_attempts,
                    delay,
                    last_exc,
                )
                await asyncio.sleep(delay)
            else:
                logger.info(
                    "[%s] %s symbol=%s · 第 %d/%d 次尝试",
                    self.name,
                    op,
                    symbol,
                    attempt,
                    max_attempts,
                )
            try:
                return await coro_factory()
            except UpstreamUnavailableError as e:
                last_exc = e
                continue

        # 全部尝试失败,带完整 traceback 打到 stderr(用 ERROR 级别)再抛
        assert last_exc is not None
        logger.error(
            "[%s] %s symbol=%s · %d 次尝试全部失败,最后异常:%s",
            self.name,
            op,
            symbol,
            max_attempts,
            last_exc,
            exc_info=True,
        )
        raise last_exc

    @abc.abstractmethod
    async def fetch_kline(
        self,
        symbol: str,
        period: Period,
        *,
        limit: int = 500,
    ) -> list[Kline]:
        """拉取指定标的的 K 线,UTC 时区,最近 `limit` 根,ts 升序。"""

    @abc.abstractmethod
    async def list_symbols(self) -> list[SymbolMeta]:
        """列出当前数据源支持的标的元信息。"""
