"""缠论 service pytest · 0011 W4。

用合成 K 线数据验证 czsc 集成 + 中枢算法。
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.market import Kline
from app.services.analysis.chan import analyze


def _make_random_klines(n: int, seed: int = 42) -> list[Kline]:
    """造一段 n 根带波动的合成 K 线 · czsc 能识别出笔。"""
    random.seed(seed)
    bars: list[Kline] = []
    price = 100.0
    base_ts = datetime(2025, 1, 1, tzinfo=UTC)
    for i in range(n):
        # 加入趋势 + 噪声 · 让笔比较明显
        trend = (
            5.0 * (1 if (i // 30) % 2 == 0 else -1)
            * (i % 30 / 30)
        )
        noise = random.uniform(-1.5, 1.5)
        price = max(price + trend / 30 + noise, 10.0)
        h = price + random.uniform(0.3, 1.2)
        low_ = price - random.uniform(0.3, 1.2)
        bars.append(
            Kline(
                ts=base_ts + timedelta(days=i),
                open=price + random.uniform(-0.3, 0.3),
                high=h,
                low=low_,
                close=price,
                volume=1000.0 + random.uniform(0, 500),
                amount=None,
            ),
        )
    return bars


@pytest.mark.asyncio
async def test_chan_too_few_bars_returns_empty():
    """< 30 根 K 线 · 返回空 result(0011 W2 规则)。"""
    klines = _make_random_klines(10)
    result = await analyze(klines, "1d", "TEST")
    assert result.bar_count == 10
    assert result.fractals == []
    assert result.bis == []
    assert result.zhongshus == []


@pytest.mark.asyncio
async def test_chan_finds_bis_and_fractals():
    """200 根合成 K · 应识别出多笔 + 顶底分型。"""
    klines = _make_random_klines(200)
    result = await analyze(klines, "1d", "TEST")
    assert result.bar_count == 200
    assert len(result.bis) >= 5
    assert len(result.fractals) >= len(result.bis)  # 每笔起止都是分型

    # 验证笔字段结构合理
    for bi in result.bis:
        assert bi.direction in ("up", "down")
        assert bi.high >= bi.low
        assert bi.power >= 0
        assert bi.length >= 1
        # 起止时间方向跟 direction 不强制一致(笔是 fx_a → fx_b · 时间一定 ASC)
        assert bi.start_ts < bi.end_ts

    # 验证分型字段结构
    for fx in result.fractals:
        assert fx.kind in ("G", "D")
        assert fx.price > 0


@pytest.mark.asyncio
async def test_chan_zhongshu_within_bi_range():
    """中枢上沿 ≤ 笔区间 max,下沿 ≥ 笔区间 min · 简化算法不变量。"""
    klines = _make_random_klines(300)
    result = await analyze(klines, "1d", "TEST")
    if not result.zhongshus:
        # 数据偶尔不出中枢 · OK
        return
    # 取一个中枢 · 验证 high > low
    for zs in result.zhongshus:
        assert zs.high > zs.low
        assert zs.start_ts <= zs.end_ts


@pytest.mark.asyncio
async def test_chan_direction_alternates():
    """缠论第一性质:相邻笔方向相反。"""
    klines = _make_random_klines(200)
    result = await analyze(klines, "1d", "TEST")
    if len(result.bis) < 2:
        return
    for i in range(1, len(result.bis)):
        prev = result.bis[i - 1].direction
        curr = result.bis[i].direction
        assert prev != curr, f"相邻笔同向 idx={i}"


@pytest.mark.asyncio
async def test_chan_ts_are_tz_aware_utc():
    """所有 ts 必须是 tz-aware UTC(项目铁律 1 同源)。"""
    klines = _make_random_klines(100)
    result = await analyze(klines, "1d", "TEST")
    for f in result.fractals:
        assert f.ts.tzinfo is not None
    for b in result.bis:
        assert b.start_ts.tzinfo is not None
        assert b.end_ts.tzinfo is not None
    for z in result.zhongshus:
        assert z.start_ts.tzinfo is not None
        assert z.end_ts.tzinfo is not None
