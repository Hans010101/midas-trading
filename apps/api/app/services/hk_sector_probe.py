"""港股行业(板块)源探测 · yfinance `.info` sector/industry 生产可达 + 批量速率(只读)。

板块调研结论(docs · 2026-06):HKEX ListOfSecurities.xlsx 无行业列 · akshare 无港股行业接口 ·
东财 HK 生产死 · 新浪无港股行业等价 → 唯一可达免费源 = **yfinance `Ticker.info` 的 sector**
(GICS 11 大类 · 已是港股 K 线备用源 · 生产可达)。但 `.info` 单只 ~2s 且有 Yahoo 速率限制 →
全量 ~900 只前必须生产实测【批量速率 + 限流 + sector 拿到率】。

★ 本模块只读探测:抽样行情池 N 只,线程池并发调 yfinance `.info` 拿 sector,返成功率/耗时/
sector 分布/限流错误。不写库、不改板块、不碰下单。像 board-lot A1 / K线源 probe 一样先验生产。
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import yfinance as yf

from app.services.hk_pool import normalize_hk_code

logger = logging.getLogger(__name__)


def _to_yf_code(symbol: str) -> str:
    """5 位港股代码 → yfinance ticker(去前导 0 补 4 位 + '.HK')· 与 hk_source 一致。"""
    return normalize_hk_code(symbol).lstrip("0").zfill(4) + ".HK"


@dataclass(frozen=True)
class HkSectorProbeResult:
    requested: int            # 抽样请求数
    ok: int                   # 拿到非空 sector 的数
    empty_sector: int         # .info 成功但 sector 为空(小盘股常见 → 归「其他」)
    failed: int               # 调用异常(含限流 / 超时)
    total_seconds: float      # 批量总耗时(wall-clock · 并发后)
    avg_seconds: float        # 摊到每只(total / requested)
    sector_dist: dict[str, int]   # sector → 命中数(看分布)
    samples: dict[str, str]       # code → sector(抽几条人眼看)
    errors: list[str]             # 失败原因抽样(★看有没有 429 限流 / 超时)


def _probe_one(code: str) -> tuple[str, str | None, str | None]:
    """探一只 · 返 (code, sector|None, error|None)。"""
    try:
        info = yf.Ticker(_to_yf_code(code)).info
        sector = info.get("sector") or None
        return code, sector, None
    except Exception as e:  # noqa: BLE001 · 探测要吞所有异常归类,不能让一只挂掉整批
        return code, None, f"{type(e).__name__}: {str(e)[:80]}"


def probe_hk_sectors(codes: list[str], max_workers: int = 8) -> HkSectorProbeResult:
    """线程池并发探 N 只 sector · 测批量速率 + 限流 + 拿到率(同步阻塞 · 调用方经 to_thread)。"""
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        results = list(ex.map(_probe_one, codes))
    dt = time.monotonic() - t0

    ok = [(c, s) for c, s, e in results if s]
    empty = [c for c, s, e in results if e is None and not s]
    failed = [(c, e) for c, s, e in results if e is not None]
    dist = Counter(s for _, s in ok)
    n = len(codes)
    logger.info(
        "[hk-sector-probe] n=%d ok=%d empty=%d failed=%d total=%.1fs",
        n, len(ok), len(empty), len(failed), dt,
    )
    return HkSectorProbeResult(
        requested=n,
        ok=len(ok),
        empty_sector=len(empty),
        failed=len(failed),
        total_seconds=round(dt, 2),
        avg_seconds=round(dt / n, 3) if n else 0.0,
        sector_dist=dict(dist),
        samples=dict(ok[:8]),
        errors=[e for _, e in failed][:5],
    )
