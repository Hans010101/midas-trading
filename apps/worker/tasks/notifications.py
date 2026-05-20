"""Celery tasks for notifications · 0009 § 3。

- send_trade_notification(order_id):查 order + dispatch 给用户配置的通道
- send_price_anomaly_notification(user_id, ...): 同上,价格异动路径
"""

from __future__ import annotations

import asyncio
import logging
import os
from decimal import Decimal
from uuid import UUID

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.virtual import MARKET_CURRENCY, VirtualAccount, VirtualOrder
from app.services.notifications.dispatcher import dispatch
from app.services.notifications.events import (
    PriceAnomalyEvent,
    TradeFilledEvent,
)

logger = logging.getLogger(__name__)


async def _async_send_trade(order_id: int) -> dict[str, object]:
    db_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(db_url, future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as db:
            order = await db.scalar(
                select(VirtualOrder).where(VirtualOrder.id == order_id),
            )
            if order is None:
                logger.warning("[notify] order_id=%s 不存在", order_id)
                return {"skipped": "order_not_found"}

            account = await db.scalar(
                select(VirtualAccount).where(
                    VirtualAccount.id == order.account_id,
                ),
            )
            if account is None:
                logger.warning(
                    "[notify] order=%s 的 account 不存在", order_id,
                )
                return {"skipped": "account_not_found"}

            event = TradeFilledEvent(
                symbol=order.symbol,
                market=order.market,
                side=order.side,
                quantity=order.quantity,
                price=order.price or Decimal("0"),
                notional=order.notional or Decimal("0"),
                commission=order.commission or Decimal("0"),
                realized_pnl=order.realized_pnl,
                currency=account.currency.value,
            )
            result = await dispatch(db, account.user_id, event)
            return {
                "channels_ok": [r.channel for r in result.results if r.ok],
                "channels_failed": [
                    {"channel": r.channel, "error": r.error}
                    for r in result.results if not r.ok
                ],
            }
    finally:
        await engine.dispose()


@shared_task(
    name="tasks.notifications.send_trade_notification",
    bind=True,
    max_retries=3,
    default_retry_delay=2,
)
def send_trade_notification(self, order_id):  # type: ignore[no-untyped-def]
    """成交事件 → 用户配置通道。失败重试 3 次(2/4/8s 退避)。"""
    try:
        return asyncio.run(_async_send_trade(order_id))
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[notify] trade order_id=%s 失败,重试 · %s", order_id, e,
        )
        raise self.retry(exc=e, countdown=2 ** self.request.retries) from e


async def _async_send_price_anomaly(
    user_id_str: str,
    symbol: str,
    market: str,
    current_price: str,
    reference_price: str,
    change_pct: str,
) -> dict[str, object]:
    db_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(db_url, future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as db:
            event = PriceAnomalyEvent(
                symbol=symbol, market=market,
                current_price=Decimal(current_price),
                reference_price=Decimal(reference_price),
                change_pct=Decimal(change_pct),
                currency=MARKET_CURRENCY[market].value,
            )
            result = await dispatch(db, UUID(user_id_str), event)
            return {
                "channels_ok": [r.channel for r in result.results if r.ok],
                "channels_failed": [
                    {"channel": r.channel, "error": r.error}
                    for r in result.results if not r.ok
                ],
            }
    finally:
        await engine.dispose()


@shared_task(
    name="tasks.notifications.send_price_anomaly_notification",
    bind=True,
    max_retries=3,
    default_retry_delay=2,
)
def send_price_anomaly_notification(  # type: ignore[no-untyped-def]
    self, user_id, symbol, market,
    current_price, reference_price, change_pct,
):
    try:
        return asyncio.run(
            _async_send_price_anomaly(
                user_id, symbol, market,
                current_price, reference_price, change_pct,
            ),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[notify] price anomaly %s 失败 · %s", symbol, e,
        )
        raise self.retry(exc=e, countdown=2 ** self.request.retries) from e
