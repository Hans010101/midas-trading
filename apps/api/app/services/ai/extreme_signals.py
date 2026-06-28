"""极端信号(crypto perp)取数 + 扫描 service · 从 analysis._scan_extreme_for 提取(智能交易 PR-1)。

★行为不变:原 analysis.py 端点 `_scan_extreme_for` 逻辑 1:1 搬来,供 strategy-signals 端点 +
智能交易信号生产 worker 共用(DRY)。funding / OI / 多空比各自 try 降级 None(不阻断)·
非 crypto perp 返空。client = 裸 async ClickHouse client(有 .query)= ch._client。
🔴 只读 CH · 纯计算 · 不下单。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.services.ai.strategy_signals import scan_extreme
from app.services.clickhouse_crypto import (
    select_funding_rates,
    select_long_short,
    select_open_interest,
)

if TYPE_CHECKING:
    from app.schemas.market import Kline
    from app.schemas.strategy import StrategySignal

logger = logging.getLogger(__name__)

_OI_LOOKBACK = 20  # OI 序列回看点数(够算 scan_extreme 的 _OI_WINDOW=12 变动)


async def compute_extreme_signals(
    client: Any, symbol: str, market: str, instrument: str, klines: list[Kline],
) -> list[StrategySignal]:
    """极端信号取数 + 扫描(仅 crypto perp · 只读 CH · 各项缺数据优雅降级 None 不报错)。"""
    if not (market == "crypto" and instrument == "perp"):
        return []
    fut_sym = symbol.upper().replace("/", "")
    funding_rate: float | None = None
    oi_series: list[float] | None = None
    ls_ratio: float | None = None
    try:
        fr = await select_funding_rates(client, fut_sym, limit=1)
        funding_rate = fr[-1].rate if fr else None
    except Exception:  # noqa: BLE001 — 某项缺数据优雅降级,不阻断
        logger.warning("[extreme] funding 取数失败 · 跳过该项", exc_info=True)
    try:
        oi = await select_open_interest(client, fut_sym, limit=_OI_LOOKBACK)
        oi_series = [o.oi_usd for o in oi] if oi else None
    except Exception:  # noqa: BLE001
        logger.warning("[extreme] OI 取数失败 · 跳过该项", exc_info=True)
    try:
        ls = await select_long_short(client, fut_sym, limit=1)
        ls_ratio = ls[-1].top_account_ratio if ls else None
    except Exception:  # noqa: BLE001
        logger.warning("[extreme] 多空比取数失败 · 跳过该项", exc_info=True)
    return scan_extreme(
        klines, funding_rate=funding_rate, oi_usd_series=oi_series, long_short_ratio=ls_ratio,
    )
