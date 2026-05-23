"""Celery beat · 加密永续合约虚拟仓强平监控(混合 60s · ADR-0019 §4.7 / D4)。

每 60s 扫所有 perp 活仓:perp ticker 最新价(crypto_ticker_24h · instrument=perp)
对比 liquidation_price。
- 多仓:mark ≤ 强平价 → 强平
- 空仓:mark ≥ 强平价 → 强平
强平走 perp_engine.liquidate_position(close_reason=liquidated · is_liquidation)。

🔴 红线:全程【虚拟资金】· 只读行情 · 绝不接真实平仓。
- 取不到 mark(行情未到 / 下架)→ 跳过该仓,绝不误杀(ADR-0019 §8 风险 2)。
- 重新 SELECT … FOR UPDATE 再平,避免与用户手动平 / 加仓竞争(§4.10)。
- 这是「混合方案」里的周期 worker;用户交互(平仓/查持仓)是另一条兜底路径。
"""

from __future__ import annotations

import asyncio
import logging
import os
from decimal import Decimal
from typing import Any

import clickhouse_connect
from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.perp import PerpSide, VirtualPerpPosition
from app.services.clickhouse_crypto import select_tickers_by_symbols
from app.services.virtual_trading.perp_engine import liquidate_position

logger = logging.getLogger(__name__)

_QUOTES = ("USDT", "USDC", "BUSD", "FDUSD")


def _to_ccxt(binance_symbol: str) -> str:
    """'BTCUSDT' → 'BTC/USDT'(perp ticker 表是 ccxt 风格)。"""
    for q in _QUOTES:
        if binance_symbol.endswith(q) and len(binance_symbol) > len(q):
            return f"{binance_symbol[: -len(q)]}/{q}"
    return binance_symbol


async def _get_ch_client() -> Any:
    """raw clickhouse async client · 跟 crypto 采集 worker 一致(UTC tz · 0002 教训)。"""
    return await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
        settings={"session_timezone": "UTC"},
    )


async def _scan_and_liquidate() -> dict[str, int]:
    engine = create_async_engine(
        os.environ["DATABASE_URL"], future=True, poolclass=NullPool,
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    ch: Any = None
    checked = 0
    liquidated = 0
    try:
        async with session_maker() as session:
            positions = (
                await session.scalars(
                    select(VirtualPerpPosition).where(
                        VirtualPerpPosition.closed_at.is_(None),
                    ),
                )
            ).all()
            if not positions:
                return {"checked": 0, "liquidated": 0}

            # 批量取活仓涉及的 symbol 的最新 perp 价
            ch = await _get_ch_client()
            symbols = sorted({p.symbol for p in positions})
            tickers = await select_tickers_by_symbols(
                ch, instrument="perp", symbols=[_to_ccxt(s) for s in symbols],
            )
            marks: dict[str, Decimal] = {}
            for s in symbols:
                t = tickers.get(_to_ccxt(s))
                if t is not None and t.last_price > 0:
                    marks[s] = Decimal(str(t.last_price))

            for p in positions:
                mark = marks.get(p.symbol)
                if mark is None:
                    continue  # 无价不误杀
                checked += 1
                hit = (
                    p.side == PerpSide.LONG and mark <= p.liquidation_price
                ) or (
                    p.side == PerpSide.SHORT and mark >= p.liquidation_price
                )
                if not hit:
                    continue
                # 重新加锁 · 防与用户手动平竞争
                locked = await session.scalar(
                    select(VirtualPerpPosition)
                    .where(
                        VirtualPerpPosition.id == p.id,
                        VirtualPerpPosition.closed_at.is_(None),
                    )
                    .with_for_update(),
                )
                if locked is None:
                    continue  # 已被用户平掉
                await liquidate_position(session, locked, mark)
                liquidated += 1
                logger.warning(
                    "[perp.liquidation] 强平虚拟仓 id=%s symbol=%s side=%s "
                    "mark=%s liq=%s",
                    locked.id, locked.symbol, locked.side, mark,
                    locked.liquidation_price,
                )

            await session.commit()
        return {"checked": checked, "liquidated": liquidated}
    finally:
        if ch is not None:
            await ch.close()
        await engine.dispose()


@shared_task(name="tasks.perp.scan_liquidations")
def scan_liquidations() -> dict[str, int]:
    """Celery 入口 · sync wrapper。"""
    result = asyncio.run(_scan_and_liquidate())
    if result["liquidated"]:
        logger.warning(
            "[perp.liquidation] 本轮强平 %d 仓(扫 %d)",
            result["liquidated"], result["checked"],
        )
    return result
