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
class BuySellPoint:
    """缠论买卖点 · czsc 1/2/3 类买卖点 · 0012 M1 二波 § 缠论买卖点提取。

    kind 取值:
      - B1 一买:在中枢下方出现底背离 → 反转启动
      - B2 二买:从一买后回踩不破前低
      - B3 三买:突破中枢上沿后回踩不破上沿
      - S1 一卖:在中枢上方出现顶背离 → 反转启动
      - S2 二卖:从一卖后反弹不破前高
      - S3 三卖:跌破中枢下沿后反弹不破下沿
    """
    ts: datetime
    price: float
    kind: str  # B1/B2/B3/S1/S2/S3
    description: str


@dataclass(frozen=True)
class ChanAnalysisResult:
    bar_count: int
    fractals: list[FractalPoint]
    bis: list[Bi]
    zhongshus: list[Zhongshu]
    buy_sell_points: list[BuySellPoint]


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
            buy_sell_points=[],
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

    buy_sell_points = _extract_buy_sell_points(bis, merged_zs)

    return ChanAnalysisResult(
        bar_count=len(klines),
        fractals=fractals,
        bis=bis,
        zhongshus=merged_zs,
        buy_sell_points=buy_sell_points,
    )


# ===== 买卖点提取 · 0012 M1 二波 =====


def _extract_buy_sell_points(
    bis: list[Bi], zhongshus: list[Zhongshu],
) -> list[BuySellPoint]:
    """从笔 + 中枢提取 6 类买卖点(B1-3 / S1-3)。

    采用「规则化」实现 · 没用 czsc.signals 体系(那套是为策略回测设计的,
    接进来需要配 Position / Event 三层 schema · 0011 § 4 已经说明 defer)。

    规则简述(0012 § 缠论买卖点提取):
      B1 一买:前一笔向下 · 终点价 < 笔起点价 · 在最近中枢的下沿附近
      B2 二买:跟在 B1 之后 · 反弹后回踩 · 不破 B1 低点
      B3 三买:笔向上突破中枢上沿后 · 下一笔回踩不破上沿
      S1 一卖:前一笔向上 · 终点价 > 笔起点价 · 在最近中枢的上沿附近
      S2 二卖:跟在 S1 之后 · 回落后反弹 · 不破 S1 高点
      S3 三卖:笔向下跌破中枢下沿后 · 下一笔反弹不破下沿

    M1 二波每个中枢只识别 0-1 个 B3 或 S3(突破点),
    以及笔序列里末端的 B1/B2/S1/S2(反转点)· 不追求完美准确度。
    """
    if len(bis) < 3 or not zhongshus:
        return []

    points: list[BuySellPoint] = []

    # 1. 三类买卖点:从每个中枢提取(笔穿越中枢上/下沿后回踩)
    for zs in zhongshus:
        # 找中枢后第一笔向上突破上沿 · 紧接着回踩不破上沿 → B3
        # 找中枢后第一笔向下跌破下沿 · 紧接着反弹不破下沿 → S3
        for i, bi in enumerate(bis):
            if bi.start_ts < zs.end_ts:
                continue  # 跳过中枢内的笔
            if i + 1 >= len(bis):
                continue
            next_bi = bis[i + 1]
            # B3:向上突破上沿,下一笔回踩不破上沿
            if (
                bi.direction == "up"
                and bi.end_price > zs.high
                and next_bi.direction == "down"
                and next_bi.end_price >= zs.high
            ):
                points.append(
                    BuySellPoint(
                        ts=next_bi.end_ts,
                        price=next_bi.end_price,
                        kind="B3",
                        description=(
                            f"三买 · 突破中枢({zs.high:.2f})后回踩不破上沿"
                        ),
                    ),
                )
                break  # 每个中枢最多一个 B3
            # S3:向下跌破下沿,下一笔反弹不破下沿
            if (
                bi.direction == "down"
                and bi.end_price < zs.low
                and next_bi.direction == "up"
                and next_bi.end_price <= zs.low
            ):
                points.append(
                    BuySellPoint(
                        ts=next_bi.end_ts,
                        price=next_bi.end_price,
                        kind="S3",
                        description=(
                            f"三卖 · 跌破中枢({zs.low:.2f})后反弹不破下沿"
                        ),
                    ),
                )
                break

    # 2. 一二类买卖点:在最近的笔序列里找反转(简化版 · 只识别近 5 笔)
    recent = bis[-5:] if len(bis) >= 5 else bis
    last_zs = zhongshus[-1]
    for i, bi in enumerate(recent):
        # B1 一买:笔向下到中枢下沿以下,且是序列里出现的新低
        if (
            bi.direction == "down"
            and bi.end_price < last_zs.low
            and bi.end_price < bi.start_price
        ):
            points.append(
                BuySellPoint(
                    ts=bi.end_ts,
                    price=bi.end_price,
                    kind="B1",
                    description=(
                        f"一买 · 跌破中枢下沿({last_zs.low:.2f})后底背离"
                    ),
                ),
            )
            # B2:紧跟着的下一笔(向上) · 再下一笔(向下)不破 B1 低点
            if (
                i + 2 < len(recent)
                and recent[i + 1].direction == "up"
                and recent[i + 2].direction == "down"
                and recent[i + 2].end_price > bi.end_price
            ):
                p2 = recent[i + 2]
                points.append(
                    BuySellPoint(
                        ts=p2.end_ts,
                        price=p2.end_price,
                        kind="B2",
                        description="二买 · 一买后回踩不破前低",
                    ),
                )
            break  # 只识别最近一个 B1/B2 组合
        # S1 一卖:笔向上到中枢上沿以上,且是序列里出现的新高
        if (
            bi.direction == "up"
            and bi.end_price > last_zs.high
            and bi.end_price > bi.start_price
        ):
            points.append(
                BuySellPoint(
                    ts=bi.end_ts,
                    price=bi.end_price,
                    kind="S1",
                    description=(
                        f"一卖 · 突破中枢上沿({last_zs.high:.2f})后顶背离"
                    ),
                ),
            )
            if (
                i + 2 < len(recent)
                and recent[i + 1].direction == "down"
                and recent[i + 2].direction == "up"
                and recent[i + 2].end_price < bi.end_price
            ):
                p2 = recent[i + 2]
                points.append(
                    BuySellPoint(
                        ts=p2.end_ts,
                        price=p2.end_price,
                        kind="S2",
                        description="二卖 · 一卖后反弹不破前高",
                    ),
                )
            break

    # 按时间排序 · 前端 overlay 渲染需要稳定顺序
    points.sort(key=lambda p: p.ts)
    return points


async def analyze(
    klines: list[Kline], period: Period, symbol: str,
) -> ChanAnalysisResult:
    """异步入口 · 把 CPU-bound czsc 调用扔线程池。"""
    return await asyncio.to_thread(_analyze_sync, klines, period, symbol)


__all__ = [
    "Bi",
    "BuySellPoint",
    "ChanAnalysisResult",
    "FractalPoint",
    "Zhongshu",
    "analyze",
]


# 让 mypy 满意 · czsc 没 stubs
_: Any = None
