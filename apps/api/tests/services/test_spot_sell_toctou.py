"""STRAT-001 现货 SELL 平仓 TOCTOU 回归测试。

修复前:_resolve_spot_order 无锁读活仓定 SELL 量(= 活仓全量)→ 并发/重复第二单拿陈旧全量,
        在引擎锁内撞已被第一单平掉的仓 → 拒「持仓不足」(超量误报)。
修复后:_active_spot(lock=True) 锁活仓(对齐 perp 的 _active_position 带锁)→ 串行化并发平仓 →
        第二单阻塞到第一单提交后读到已平仓 None → 干净「无可平持仓」(qty=None)。

★ 红线:引擎超卖守卫(_execute_sell 的 position.quantity < req.quantity → 拒「持仓不足」)不动;
   本修复只加锁消除 TOCTOU,不改撮合语义、不碰超卖守卫。
★ 并发测试需独立 engine(NullPool 独立连接)才能真触发 with_for_update 行锁串行化
   (conftest 的 db_session 是单连接 savepoint,自己不会阻塞自己,测不出行锁)。
"""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.user import User
from app.models.virtual import OrderSide, OrderStatus, PositionSide
from app.services.bot.order import _resolve_spot_order
from app.services.virtual_trading.engine import PlaceOrderRequest, place_market_order
from tests.factories import make_static_price_fetcher, make_user, make_virtual_account

_DUMMY_CH = object()  # _resolve_spot_order 的 sell 分支不碰 ch · 给个占位
_SYM = "600519"
_FETCHER = make_static_price_fetcher({(_SYM, "cn"): Decimal("10")})


def _buy_req(uid: object, qty: str) -> PlaceOrderRequest:
    return PlaceOrderRequest(
        user_id=uid, symbol=_SYM, market="cn", side=OrderSide.BUY,
        quantity=Decimal(qty), position_side=PositionSide.LONG, notify=False,
    )


@pytest.mark.asyncio
async def test_single_spot_sell_close_normal(db_session: AsyncSession) -> None:
    """单请求正常平仓不破:BUY 建仓 → SELL 平全仓 → FILLED(守卫不误伤,SELL 量=活仓全量)。"""
    user = await make_user(db_session)
    await make_virtual_account(db_session, user_id=user.id, market="cn")
    await db_session.commit()

    buy = await place_market_order(db_session, _buy_req(user.id, "100"), _FETCHER)
    await db_session.commit()
    assert buy.status == OrderStatus.FILLED

    side, pside, qty = await _resolve_spot_order(
        db_session, _DUMMY_CH, user.id, "cn", _SYM, "sell",
    )
    assert qty == Decimal("100")  # 平全仓 = 活仓全量
    sell = await place_market_order(
        db_session,
        PlaceOrderRequest(
            user_id=user.id, symbol=_SYM, market="cn", side=side,
            quantity=qty, position_side=pside, notify=False,
        ),
        _FETCHER,
    )
    await db_session.commit()
    assert sell.status == OrderStatus.FILLED


@pytest.mark.asyncio
async def test_concurrent_spot_sell_close_no_oversell() -> None:
    """★并发/重复平仓:两单并发 SELL 同标的 → 恰好一单成交、一单干净「无可平持仓」,
    绝不出现「持仓不足」超量误报(证明 with_for_update 串行化已消除 TOCTOU)。
    """
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    uid = None
    try:
        # seed:user + cn 账户 + BUY 100 建多仓(独立 session · commit 落库)
        async with sm() as s:
            user = await make_user(s)
            await make_virtual_account(s, user_id=user.id, market="cn")
            await s.commit()
            uid = user.id
        async with sm() as s:
            buy = await place_market_order(s, _buy_req(uid, "100"), _FETCHER)
            await s.commit()
            assert buy.status == OrderStatus.FILLED

        async def close_once() -> dict[str, object]:
            async with sm() as s:
                side, pside, qty = await _resolve_spot_order(
                    s, _DUMMY_CH, uid, "cn", _SYM, "sell",
                )
                if qty is None:  # 锁串行化后,第二单读到已平仓 → 干净无可平
                    return {"outcome": "no_position", "reason": None}
                order = await place_market_order(
                    s,
                    PlaceOrderRequest(
                        user_id=uid, symbol=_SYM, market="cn", side=side,
                        quantity=qty, position_side=pside, notify=False,
                    ),
                    _FETCHER,
                )
                await s.commit()
                return {"outcome": order.status, "reason": order.reject_reason}

        results = await asyncio.gather(close_once(), close_once())

        # ★核心:没有任何一单报「持仓不足」(TOCTOU 消除 · 超卖守卫不被并发误触发)
        assert all(r["reason"] != "持仓不足" for r in results), (
            f"TOCTOU 未消除 · 出现持仓不足超量误报:{results}"
        )
        filled = [r for r in results if r["outcome"] == OrderStatus.FILLED]
        no_pos = [r for r in results if r["outcome"] == "no_position"]
        assert len(filled) == 1, f"应恰好一单成交:{results}"
        assert len(no_pos) == 1, f"应恰好一单干净无可平持仓:{results}"
    finally:
        if uid is not None:
            async with sm() as s:
                await s.execute(delete(User).where(User.id == uid))  # CASCADE 清账户/持仓/订单
                await s.commit()
        await engine.dispose()
