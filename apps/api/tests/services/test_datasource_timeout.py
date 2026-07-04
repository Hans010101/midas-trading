"""数据源超时 + 不阻塞事件循环 · 根治 2026-05-27 生产卡死的回归测试。

验证 BaseDataSource._run_blocking / _retry 的三条保证:
1. 卡住的上游调用在超时后抛 UpstreamUnavailableError,绝不无限等待。
2. 一个上游调用卡住时,事件循环 + 其它协程照常运行(不被冻死)。
3. 正常(快速返回)路径零回归。
4. _retry 受总时长上限约束(不会 4 次重试把卡住的上游拖很久)。
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.schemas.market import Kline, Period, SymbolMeta
from app.services.data_sources import base
from app.services.data_sources.base import BaseDataSource
from app.services.data_sources.exceptions import UpstreamUnavailableError


class _DummySource(BaseDataSource):
    """测试用数据源:把同步调用塞进 _run_blocking(被测路径)。"""

    name = "dummy"
    market = "cn"

    def __init__(self) -> None:
        self.call_count = 0

    def _slow_sync(self) -> str:
        self.call_count += 1
        time.sleep(1.0)  # 模拟上游"接了连接不回数据"的阻塞
        return "should-not-reach"

    def _fast_sync(self, value: str) -> str:
        self.call_count += 1
        return f"ok:{value}"

    async def fetch_kline(
        self, _symbol: str, _period: Period, *, _limit: int = 500,
    ) -> list[Kline]:
        return []

    async def list_symbols(self) -> list[SymbolMeta]:
        return []


@pytest.mark.asyncio
async def test_run_blocking_times_out_not_hangs(monkeypatch: pytest.MonkeyPatch) -> None:
    """慢/卡住的上游调用超时后抛 UpstreamUnavailableError,绝不无限等待。"""
    monkeypatch.setattr(base, "UPSTREAM_CALL_TIMEOUT", 0.3)
    src = _DummySource()

    start = time.monotonic()
    with pytest.raises(UpstreamUnavailableError):
        await src._run_blocking(src._slow_sync)
    elapsed = time.monotonic() - start

    assert elapsed < 0.9, f"应 ~0.3s 超时,实际 {elapsed:.2f}s(疑似无限等待)"


@pytest.mark.asyncio
async def test_slow_upstream_does_not_block_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一个上游调用卡住时,事件循环 + 其它协程照常运行(不被冻死)。

    ★flaky 修(2026-07-04·CI run 28707325755 首跑红重跑绿):原 UPSTREAM_CALL_TIMEOUT=1.0 与
    _slow_sync 的 time.sleep(1.0) 是【精确平局竞态】——executor 若比 timeout 早一瞬完成,
    _run_blocking 正常返回不抛错 → "DID NOT RAISE UpstreamUnavailableError" 偶发红。
    改 0.3(与 test_run_blocking_times_out_not_hangs 同款)拉开 0.7s 决定性差距消除竞态;
    fast 阈值 0.5→0.75 容 CI runner 噪音(冻结时 fast_elapsed≈1.0s=sync sleep 时长·仍可判别)。
    测试意图(慢上游不冻事件循环 + 超时必抛)不变。
    """
    monkeypatch.setattr(base, "UPSTREAM_CALL_TIMEOUT", 0.3)
    src = _DummySource()

    async def _swallow() -> None:
        with pytest.raises(UpstreamUnavailableError):
            await src._run_blocking(src._slow_sync)

    async def other_fast_work() -> str:
        await asyncio.sleep(0.05)  # 模拟"其它接口":纯事件循环工作,应几乎瞬间完成
        return "fast-done"

    slow_task = asyncio.create_task(_swallow())
    start = time.monotonic()
    fast_result = await other_fast_work()
    fast_elapsed = time.monotonic() - start

    assert fast_result == "fast-done"
    # 0.75 容 CI 噪音:未冻死 ≈0.05s;冻死 ≈1.0s(被 sync sleep 拖满)· 判别边界依然清晰
    assert fast_elapsed < 0.75, (
        f"其它协程被阻塞了 {fast_elapsed:.2f}s · 事件循环疑似被同步调用冻死"
    )
    await slow_task  # 收尾(慢调用会超时退出)


@pytest.mark.asyncio
async def test_run_blocking_happy_path() -> None:
    """正常(快速返回)路径零回归:_run_blocking 正常透传结果。"""
    src = _DummySource()
    result = await src._run_blocking(src._fast_sync, "hello")
    assert result == "ok:hello"
    assert src.call_count == 1


@pytest.mark.asyncio
async def test_retry_bounded_by_total_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_retry 受总时长上限约束:全部超时也不会把 4 次重试全跑完、无限拖时间。"""
    monkeypatch.setattr(base, "UPSTREAM_CALL_TIMEOUT", 0.3)
    monkeypatch.setattr(base, "RETRY_TOTAL_DEADLINE", 0.5)
    monkeypatch.setattr(base, "_RETRY_DELAYS", (0.0, 0.2, 0.2, 0.2))
    src = _DummySource()

    async def _do() -> str:
        return await src._run_blocking(src._slow_sync)

    start = time.monotonic()
    with pytest.raises(UpstreamUnavailableError):
        await src._retry(op="test", symbol="X", coro_factory=_do)
    elapsed = time.monotonic() - start

    # 4 次尝试 × 0.3s + 0.6s 延迟 ≈ 1.8s;总时长护栏应在 ~0.5s 内截断 → 远少于 1.8s。
    assert elapsed < 1.2, f"总重试时长 {elapsed:.2f}s 未受上限约束(疑似跑满 4 次)"
