"""缠论分析 service · 0011 ADR § 2-3。

输入:Kline 列表(我们的 schema)
输出:ChanAnalysisResult(笔 + 顶底分型 + 中枢)

简化范围(M1 第一波):
- 分型 / 笔 走 czsc(成熟)
- 中枢用「连续 3 笔重叠区间」简算法(czsc 不暴露默认中枢)
- 段 / 买卖点 / 中枢扩展 defer M1 第二波(0011 § 4)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.schemas.market import Kline, Period

logger = logging.getLogger(__name__)


# czsc Freq 字符串值跟 Period 不完全一致 · 写映射
_CZSC_FREQ_MAP: dict[Period, str] = {
    "1m": "1分钟",
    "5m": "5分钟",
    "15m": "15分钟",
    "30m": "30分钟",
    "1h": "60分钟",
    "1d": "日线",
    "1w": "周线",
}


# ===== 输出 dataclass =====


@dataclass(frozen=True)
class FractalPoint:
    """分型 · 0011 § 2"""
    ts: datetime
    price: float
    kind: str  # 'G' 顶 / 'D' 底


@dataclass(frozen=True)
class Bi:
    """笔"""
    start_ts: datetime
    end_ts: datetime
    start_price: float
    end_price: float
    direction: str  # 'up' / 'down'
    high: float
    low: float
    power: float
    length: int


@dataclass(frozen=True)
class Zhongshu:
    """中枢 · 简化版"""
    start_ts: datetime
    end_ts: datetime
    high: float
    low: float


@dataclass(frozen=True)
class ChanAnalysisResult:
    bar_count: int
    fractals: list[FractalPoint]
    bis: list[Bi]
    zhongshus: list[Zhongshu]


# ===== 同步实现 =====


def _to_aware(ts: datetime) -> datetime:
    """czsc 返回 naive datetime · 我们统一 tz-aware UTC。"""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts


def _analyze_sync(
    klines: list[Kline], period: Period, symbol: str,
) -> ChanAnalysisResult:
    """同步实现 · czsc 是 CPU-bound 库,在线程池跑。"""
    if len(klines) < 30:
        # 少于 30 根识别不出多少笔
        return ChanAnalysisResult(
            bar_count=len(klines), fractals=[], bis=[], zhongshus=[],
        )

    # 延迟 import · czsc 启动开销大
    from czsc import CZSC, Freq, RawBar  # noqa: PLC0415

    czsc_freq_str = _CZSC_FREQ_MAP[period]
    freq_obj = next(f for f in Freq.__members__.values() if f.value == czsc_freq_str)

    # czsc.RawBar 用 naive datetime · 把我们的 tz-aware 去掉 tz
    raw_bars = []
    for i, k in enumerate(klines):
        ts_naive = k.ts.astimezone(UTC).replace(tzinfo=None)
        raw_bars.append(
            RawBar(
                symbol=symbol,
                id=i,
                dt=ts_naive,
                freq=freq_obj,
                open=float(k.open),
                close=float(k.close),
                high=float(k.high),
                low=float(k.low),
                vol=float(k.volume),
                amount=float(k.amount or 0),
            ),
        )

    c = CZSC(raw_bars)

    # 提取分型 + 笔
    fractals: list[FractalPoint] = []
    seen_fx: set[tuple[datetime, str]] = set()
    bis: list[Bi] = []

    for bi in c.bi_list:
        # 提取分型(去重 · bi 起止可能跟下一笔起点重合)
        for fx in (bi.fx_a, bi.fx_b):
            mark_value = (
                fx.mark.value if hasattr(fx.mark, "value") else str(fx.mark)
            )
            kind = "G" if mark_value in ("G", "顶分型") else "D"
            ts = _to_aware(fx.dt)
            key = (ts, kind)
            if key in seen_fx:
                continue
            seen_fx.add(key)
            fractals.append(
                FractalPoint(ts=ts, price=float(fx.fx), kind=kind),
            )

        # 笔(direction str)
        direction = (
            "up" if bi.direction.value in ("Up", "向上") else "down"
        )
        bis.append(
            Bi(
                start_ts=_to_aware(bi.fx_a.dt),
                end_ts=_to_aware(bi.fx_b.dt),
                start_price=float(bi.fx_a.fx),
                end_price=float(bi.fx_b.fx),
                direction=direction,
                high=float(bi.high),
                low=float(bi.low),
                power=float(bi.power),
                length=int(bi.length),
            ),
        )

    fractals.sort(key=lambda f: f.ts)

    # 中枢:简化算法 · 连续 3 笔重叠区间
    zhongshus: list[Zhongshu] = []
    if len(bis) >= 3:
        for i in range(len(bis) - 2):
            b1, _b2, b3 = bis[i], bis[i + 1], bis[i + 2]
            # 第一笔跟第三笔同向 · b2 反向(czsc bi 序列默认是相邻反向 · 所以 b1/b3 同向)
            zs_high = min(b1.high, b3.high)
            zs_low = max(b1.low, b3.low)
            if zs_low < zs_high:  # 有重叠
                zhongshus.append(
                    Zhongshu(
                        start_ts=b1.start_ts,
                        end_ts=b3.end_ts,
                        high=zs_high,
                        low=zs_low,
                    ),
                )

    # 合并相邻 / 重叠的中枢段(避免相邻 4 笔生成两个高度重合的中枢)
    merged_zs: list[Zhongshu] = []
    for zs in zhongshus:
        if merged_zs:
            prev = merged_zs[-1]
            # 时间重叠 + 价位重叠 → 合并
            if (
                zs.start_ts <= prev.end_ts
                and not (zs.low > prev.high or zs.high < prev.low)
            ):
                merged_zs[-1] = Zhongshu(
                    start_ts=prev.start_ts,
                    end_ts=max(prev.end_ts, zs.end_ts),
                    high=max(prev.high, zs.high),
                    low=min(prev.low, zs.low),
                )
                continue
        merged_zs.append(zs)

    return ChanAnalysisResult(
        bar_count=len(klines),
        fractals=fractals,
        bis=bis,
        zhongshus=merged_zs,
    )


async def analyze(
    klines: list[Kline], period: Period, symbol: str,
) -> ChanAnalysisResult:
    """异步入口 · 把 CPU-bound czsc 调用扔线程池。"""
    return await asyncio.to_thread(_analyze_sync, klines, period, symbol)


__all__ = [
    "Bi",
    "ChanAnalysisResult",
    "FractalPoint",
    "Zhongshu",
    "analyze",
]


# 让 mypy 满意 · czsc 没 stubs
_: Any = None
