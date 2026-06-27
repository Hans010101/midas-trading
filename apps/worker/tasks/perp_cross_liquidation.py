"""Celery beat · 全仓(cross)账户级强平监控 · ADR-0027 MC-3 · 独立 worker。

每 60s 扫所有持有 cross 活仓的账户:按账户算 cross_equity vs Σ维持保证金,
`equity ≤ Σmm` → 一次性全平该账户所有 cross 仓位(穿仓地板到 0)。

🔴 红线:全程【虚拟资金】· 只读行情(mark)· 绝不接真实平仓。
🚫 独立于逐仓强平 worker(perp_liquidation.py):
   - 新文件 / 新 task name(tasks.perp.scan_cross_liquidations)/ 新 beat 入口;
   - 只扫 margin_mode='cross'(逐仓 worker 只扫 'isolated' · MC-1),两者井水不犯河水;
   - **单账户出错隔离**:某账户扫描/强平抛错 → rollback 该账户 + 记日志 + 跳过 + 继续,
     绝不让一个账户的问题拖垮整轮、绝不影响其他账户。
缺 mark(DP-9):该账户任一 cross 仓位缺 mark → 跳过整账户本轮(等下一轮 mark 齐了再说)。

价源与逐仓一致:premiumIndex(真标记价)优先,缺则 perp ticker 最新价兜底,都缺则跳过。
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
from app.models.perp import MarginMode, VirtualPerpPosition
from app.models.virtual import VirtualAccount
from app.services.clickhouse_crypto import (
    select_premium_index_marks,
    select_tickers_by_symbols,
)
from app.services.notifications.emit import emit_cross_liquidation
from app.services.virtual_trading.perp_cross_liquidation import (
    STATUS_LIQUIDATED,
    liquidate_cross_account,
    select_open_cross_account_ids,
)

logger = logging.getLogger(__name__)

_QUOTES = ("USDT", "USDC", "BUSD", "FDUSD")


def _to_ccxt(binance_symbol: str) -> str:
    """'BTCUSDT' → 'BTC/USDT'(perp ticker 表是 ccxt 风格)· 自包含,不依赖逐仓 worker。"""
    for q in _QUOTES:
        if binance_symbol.endswith(q) and len(binance_symbol) > len(q):
            return f"{binance_symbol[: -len(q)]}/{q}"
    return binance_symbol


async def _get_ch_client() -> Any:
    """raw clickhouse async client(UTC tz · 0002 教训)· 与采集 worker 一致。"""
    return await clickhouse_connect.get_async_client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        username=settings.clickhouse_user,
        password=settings.clickhouse_password,
        database=settings.clickhouse_database,
        settings={"session_timezone": "UTC"},
    )


async def _fetch_marks(ch: Any, symbols: list[str]) -> dict[str, Decimal]:
    """取 symbols 的真标记价:premiumIndex 优先,缺的退回 perp ticker 最新价兜底。"""
    marks: dict[str, Decimal] = await select_premium_index_marks(ch, symbols)
    missing = [s for s in symbols if s not in marks]
    if missing:
        tickers = await select_tickers_by_symbols(
            ch, instrument="perp", symbols=[_to_ccxt(s) for s in missing],
        )
        for s in missing:
            t = tickers.get(_to_ccxt(s))
            if t is not None and t.last_price > 0:
                marks[s] = Decimal(str(t.last_price))
    return marks


async def _scan_and_liquidate_cross() -> dict[str, int]:
    engine = create_async_engine(
        os.environ["DATABASE_URL"], future=True, poolclass=NullPool,
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    ch: Any = None
    accounts_scanned = 0
    accounts_liquidated = 0
    positions_liquidated = 0
    try:
        async with session_maker() as session:
            # ★候选账户(已排除 managed 托管单 → 禁强平 · 见 select_open_cross_account_ids)
            account_ids = await select_open_cross_account_ids(session)
            if not account_ids:
                return {
                    "accounts_scanned": 0,
                    "accounts_liquidated": 0,
                    "positions_liquidated": 0,
                }

            ch = await _get_ch_client()
            for account_id in account_ids:
                accounts_scanned += 1
                # 🔴 单账户错误隔离:任何异常 → rollback 该账户 + 跳过 + 继续(不影响其他账户)
                try:
                    account = await session.scalar(
                        select(VirtualAccount).where(VirtualAccount.id == account_id),
                    )
                    if account is None:
                        continue
                    symbols = (
                        await session.scalars(
                            select(VirtualPerpPosition.symbol)
                            .where(
                                VirtualPerpPosition.account_id == account_id,
                                VirtualPerpPosition.closed_at.is_(None),
                                VirtualPerpPosition.margin_mode == MarginMode.CROSS,
                            )
                            .distinct(),
                        )
                    ).all()
                    marks = await _fetch_marks(ch, sorted(set(symbols)))
                    outcome = await liquidate_cross_account(session, account, marks)
                    await session.commit()
                    if outcome.status == STATUS_LIQUIDATED:
                        accounts_liquidated += 1
                        positions_liquidated += outcome.liquidated_count
                        logger.warning(
                            "[perp.cross_liq] 全仓账户级强平 account=%s 平仓=%s "
                            "floored=%s equity=%s mm=%s",
                            account_id, outcome.liquidated_count, outcome.floored,
                            outcome.equity, outcome.maint_margin,
                        )
                        # #296:commit 之后才 emit 全仓强平汇总(账户级一条 · 旁路不影响结算)
                        emit_cross_liquidation(
                            account.id,
                            outcome.liquidated_count,
                            outcome.floored,
                            account.cash_balance,
                        )
                except Exception:
                    await session.rollback()
                    logger.exception(
                        "[perp.cross_liq] 账户 %s 全仓强平扫描失败 · 跳过该账户",
                        account_id,
                    )
                    continue
        return {
            "accounts_scanned": accounts_scanned,
            "accounts_liquidated": accounts_liquidated,
            "positions_liquidated": positions_liquidated,
        }
    finally:
        if ch is not None:
            await ch.close()
        await engine.dispose()


@shared_task(name="tasks.perp.scan_cross_liquidations")
def scan_cross_liquidations() -> dict[str, int]:
    """Celery 入口 · sync wrapper(独立于逐仓 tasks.perp.scan_liquidations)。"""
    result = asyncio.run(_scan_and_liquidate_cross())
    if result["positions_liquidated"]:
        logger.warning(
            "[perp.cross_liq] 本轮全仓账户级强平 %d 账户 / %d 仓(扫 %d 账户)",
            result["accounts_liquidated"], result["positions_liquidated"],
            result["accounts_scanned"],
        )
    return result
