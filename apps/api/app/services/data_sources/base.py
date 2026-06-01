"""数据源抽象基类。

三家数据源适配器(AKShare / yfinance / ccxt)继承 BaseDataSource。

【根治 2026-05-27 生产卡死】基类对所有【同步】上游调用提供三层保护:
  1. `socket.setdefaulttimeout`(进程级):给阻塞 socket(akshare / yfinance 内部
     用 requests / urllib)兜底读超时。原故障正是"上游接了连接但不回数据 + 无超时
     → 无限死等"。设了默认超时后,卡住的工作线程最终会抛 socket 超时、自己退出。
  2. 专用隔离线程池 `_UPSTREAM_POOL`:同步上游调用全部走这里,跟 asyncio 默认
     executor(DNS getaddrinfo / loop.run_in_executor(None,...) 等内部操作)**物理隔离**。
     即使上游全卡住,也只占用本池线程 → 事件循环、/health、其它请求、DNS 解析都不受影响。
  3. `_run_blocking` 的 `asyncio.wait_for` 超时:协程层兜底,卡住时也能拿回控制权、
     抛 UpstreamUnavailableError 优雅报错,绝不无限等待。

`_retry` 对 UpstreamUnavailableError 指数退避重试,且受 **总时长上限** 约束
(避免 4 次重试把一个卡住的上游累计拖很久)。

终态异常(SymbolNotFoundError / DataFormatError)不重试,直接上抛。
"""

from __future__ import annotations

import abc
import asyncio
import logging
import socket
import time
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from app.schemas.market import Kline, Market, Period, SymbolMeta
from app.services.data_sources.exceptions import UpstreamUnavailableError

logger = logging.getLogger(__name__)

R = TypeVar("R")

# ── 超时 / 隔离常量(根治生产卡死)──────────────────────────────────────
# 单次上游同步调用的网络读超时:akshare/yfinance 内部 requests/urllib 的 socket 读超时。
UPSTREAM_SOCKET_TIMEOUT = 15.0
# asyncio 层超时(wait_for):略大于 socket 超时,作为兜底 —— 即使线程卡在非 socket 处
# (锁 / CPU),协程也能在此超时后拿回控制权、优雅报错。
UPSTREAM_CALL_TIMEOUT = 18.0
# _retry 总时长上限:多次重试累计墙钟不超过此值。
RETRY_TOTAL_DEADLINE = 30.0
# 专用线程池大小:隔离同步上游调用,即使全卡住也不动 asyncio 默认池。
_UPSTREAM_POOL_SIZE = 12

# 进程级 socket 默认超时:只影响【阻塞】socket(同步 requests/urllib → akshare/yfinance/
# clickhouse-connect)。asyncio / asyncpg / aiohttp(ccxt 异步)用非阻塞 socket,不受影响。
socket.setdefaulttimeout(UPSTREAM_SOCKET_TIMEOUT)

# 专用隔离线程池:所有同步上游调用走这里(详见模块 docstring 第 2 条)。
_UPSTREAM_POOL = ThreadPoolExecutor(
    max_workers=_UPSTREAM_POOL_SIZE, thread_name_prefix="ds-upstream",
)

# 退避策略:首次立即,失败后 1 / 5 / 15 秒重试。最多 4 次尝试(且受 RETRY_TOTAL_DEADLINE 约束)。
_RETRY_DELAYS: tuple[float, ...] = (0.0, 1.0, 5.0, 15.0)


class BaseDataSource(abc.ABC):
    """三市场数据源的统一接口。子类必须设置 `name` + `market`。

    实现要求:
    - 返回的 Kline 列表必须 ts 升序(最早 → 最新)
    - 所有 ts 字段必须是 tz-aware UTC datetime
    - 失败必须抛 DataSourceError 子类,**严禁返回空列表**
    - 网络 / 限流类失败要包成 UpstreamUnavailableError(或 RateLimitError)
    - **同步上游调用一律经 `self._run_blocking(...)`**,绝不直接 `asyncio.to_thread`
      或在事件循环上同步阻塞(根治生产卡死)。
    """

    name: str  # 子类设置:"akshare" / "yfinance" / "ccxt-binance"
    market: Market

    async def _run_blocking(
        self, fn: Callable[..., R], *args: object, timeout: float | None = None,
    ) -> R:
        """把【同步】上游调用放到隔离线程池执行,带 asyncio 超时。

        - 隔离线程池:不阻塞事件循环、不耗尽 asyncio 默认池(DNS 等内部操作不受影响)。
        - 超时:默认 UPSTREAM_CALL_TIMEOUT(18s)· 超时抛 UpstreamUnavailableError(可被 _retry 接住)。
          底层 socket 超时(更短)通常先让线程自己结束、线程池自愈。
        - timeout:覆盖默认值 · 给全市场分页等慢调用(如港股 stock_hk_spot ~46 页)用 · 默认 None=18s。
        """
        loop = asyncio.get_running_loop()
        to = UPSTREAM_CALL_TIMEOUT if timeout is None else timeout
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(_UPSTREAM_POOL, fn, *args),
                timeout=to,
            )
        except TimeoutError as e:
            raise UpstreamUnavailableError(
                f"上游同步调用超时(>{to:.0f}s)· 已隔离线程池,未阻塞事件循环",
                market=self.market,
                upstream=self.name,
            ) from e

    async def _retry(
        self,
        *,
        op: str,
        symbol: str,
        coro_factory: Callable[[], Awaitable[R]],
    ) -> R:
        """指数退避重试 · 受 RETRY_TOTAL_DEADLINE 总时长上限约束。

        `coro_factory` 每次重新构造一个新的协程。
        """
        last_exc: UpstreamUnavailableError | None = None
        max_attempts = len(_RETRY_DELAYS)
        start = time.monotonic()

        for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
            # 总时长护栏:若"等 delay + 再跑一次(最多 UPSTREAM_CALL_TIMEOUT)"会超总上限,停止重试。
            # 第 1 次尝试永远执行(attempt == 1);只对后续重试做护栏。
            elapsed = time.monotonic() - start
            if (
                attempt > 1
                and elapsed + delay + UPSTREAM_CALL_TIMEOUT > RETRY_TOTAL_DEADLINE
            ):
                logger.warning(
                    "[%s] %s symbol=%s · 已用 %.1fs · 超总上限 %.0fs 停止重试 · 末次:%s",
                    self.name, op, symbol, elapsed, RETRY_TOTAL_DEADLINE, last_exc,
                )
                break

            if delay > 0:
                logger.warning(
                    "[%s] %s symbol=%s · 第 %d/%d 次尝试,等待 %.1fs 后重试。上次失败:%s",
                    self.name, op, symbol, attempt, max_attempts, delay, last_exc,
                )
                await asyncio.sleep(delay)
            else:
                logger.info(
                    "[%s] %s symbol=%s · 第 %d/%d 次尝试",
                    self.name, op, symbol, attempt, max_attempts,
                )
            try:
                return await coro_factory()
            except UpstreamUnavailableError as e:
                last_exc = e
                continue

        # 全部尝试失败(或触发总时长护栏),带完整 traceback 打到 stderr 再抛。
        assert last_exc is not None  # noqa: S101
        logger.error(
            "[%s] %s symbol=%s · 重试结束仍失败,最后异常:%s",
            self.name, op, symbol, last_exc, exc_info=True,
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
