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

from app.models.perp import VirtualPerpOrder, VirtualPerpPosition
from app.models.virtual import MARKET_CURRENCY, VirtualAccount, VirtualOrder
from app.services.notifications.dispatcher import dispatch
from app.services.notifications.events import (
    LiquidationEvent,
    PerpFilledEvent,
    PriceAnomalyEvent,
)
from app.services.notifications.perp_events import (
    build_liquidation_event_single,
    build_perp_filled_event,
    build_trade_filled_event,
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

            event = build_trade_filled_event(order, account)
            result = await dispatch(db, account.user_id, event)
            # #296:成功发送补一条 info 日志(方便以后搜"发没发")
            logger.info(
                "[notify] trade sent order_id=%s ok=%s",
                order_id, [r.channel for r in result.results if r.ok],
            )
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


# ============================================================================
# #296 · 永续合约成交 + 强平 通知
# ============================================================================
# 事件 builder 见 app.services.notifications.perp_events(纯函数 · apps/api 单测覆盖)。


async def _async_send_perp_order(order_id: int) -> dict[str, object]:
    db_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(db_url, future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as db:
            order = await db.scalar(
                select(VirtualPerpOrder).where(VirtualPerpOrder.id == order_id),
            )
            if order is None:
                logger.warning("[notify] perp order_id=%s 不存在", order_id)
                return {"skipped": "order_not_found"}
            account = await db.scalar(
                select(VirtualAccount).where(
                    VirtualAccount.id == order.account_id,
                ),
            )
            if account is None:
                logger.warning("[notify] perp order=%s account 不存在", order_id)
                return {"skipped": "account_not_found"}
            position = None
            if order.position_id is not None:
                position = await db.scalar(
                    select(VirtualPerpPosition).where(
                        VirtualPerpPosition.id == order.position_id,
                    ),
                )

            event: LiquidationEvent | PerpFilledEvent = (
                build_liquidation_event_single(order, position, account)
                if order.is_liquidation
                else build_perp_filled_event(order, position, account)
            )
            result = await dispatch(db, account.user_id, event)
            logger.info(
                "[notify] perp order_id=%s liq=%s ok=%s",
                order_id, order.is_liquidation,
                [r.channel for r in result.results if r.ok],
            )
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
    name="tasks.notifications.send_perp_order_notification",
    bind=True,
    max_retries=3,
    default_retry_delay=2,
)
def send_perp_order_notification(self, order_id):  # type: ignore[no-untyped-def]
    """永续成交 / 逐仓强平 → 用户配置通道(按 is_liquidation 分流)。失败重试 3 次。"""
    try:
        return asyncio.run(_async_send_perp_order(order_id))
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[notify] perp order_id=%s 失败,重试 · %s", order_id, e,
        )
        raise self.retry(exc=e, countdown=2 ** self.request.retries) from e


async def _async_send_cross_liquidation(
    account_id: int,
    liquidated_count: int,
    floored: bool,
    remaining_cash: str,
) -> dict[str, object]:
    db_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(db_url, future=True, poolclass=NullPool)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as db:
            account = await db.scalar(
                select(VirtualAccount).where(VirtualAccount.id == account_id),
            )
            if account is None:
                logger.warning("[notify] cross liq account=%s 不存在", account_id)
                return {"skipped": "account_not_found"}
            event = LiquidationEvent(
                is_cross=True,
                position_count=liquidated_count,
                remaining_cash=Decimal(remaining_cash),
                floored=floored,
                currency=account.currency.value,
            )
            result = await dispatch(db, account.user_id, event)
            logger.info(
                "[notify] cross liq account_id=%s count=%s ok=%s",
                account_id, liquidated_count,
                [r.channel for r in result.results if r.ok],
            )
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
    name="tasks.notifications.send_cross_liquidation_notification",
    bind=True,
    max_retries=3,
    default_retry_delay=2,
)
def send_cross_liquidation_notification(  # type: ignore[no-untyped-def]
    self, account_id, liquidated_count, floored, remaining_cash,
):
    """全仓账户级强平 → 账户级汇总一条。失败重试 3 次。"""
    try:
        return asyncio.run(
            _async_send_cross_liquidation(
                account_id, liquidated_count, floored, remaining_cash,
            ),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[notify] cross liq account=%s 失败,重试 · %s", account_id, e,
        )
        raise self.retry(exc=e, countdown=2 ** self.request.retries) from e
