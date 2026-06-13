"""条件单触发内核(ADR 0041 刀2)· should_trigger 纯函数 + 扫描处理逻辑(依赖注入 · 可单测)。

═══════════════════════════════════════════════════════════════════════════
🔴🔴 最高红线(本文件 review 重点):
  触发成交【只能】调现有唯一入口 —— spot → place_market_order · perp 限价开仓 → route_open_perp ·
  perp SL/TP → route_close_perp。开仓(route_open_perp)与平仓(route_close_perp)对称,
  本文件【零】撮合/滑点/手续费/持仓变更逻辑(全部在被调入口内,继承不重写);
  engine.py / perp_dispatcher 一行不改,只 import 调用。
  成交那一刻走唯一入口 = 全程虚拟 + 成交通知自动继承
  (spot notify=True · perp emit 由壳 commit 后发)。
═══════════════════════════════════════════════════════════════════════════

幂等(防重复成交):无锁批量扫判 → 命中后 SELECT ... WHERE id AND status==ACTIVE FOR UPDATE
二次确认(锁 miss = 已撤/已触发 → 跳过)→ 成交 + 状态流转同一事务(调用方 commit)。
失败(余额不足/无活仓被拒)→ EXPIRED + note,不重试(一次性语义 · rejected 单 id 仍回填供审计)。

被 worker 壳(apps/worker/tasks/conditional_orders.py)以注入方式调用:
  get_spot_price(symbol, market) · get_perp_mark(symbol) · is_market_open(market)
股票休市(cn/us/hk 非交易时段)由 is_market_open 整组跳过;crypto 7×24 恒扫;无价跳过不误触发。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.conditional_order import (
    ConditionalKind,
    ConditionalOrder,
    ConditionalStatus,
)
from app.models.perp import MarginMode, PerpSide
from app.models.virtual import (
    OrderSide,
    OrderStatus,
    PositionSide,
    VirtualAccount,
    VirtualPosition,
)
from app.services.virtual_trading.engine import (
    PlaceOrderRequest,
    PriceFetcher,
    place_market_order,
)
from app.services.virtual_trading.perp_dispatcher import (
    route_close_perp,
    route_open_perp,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.perp import VirtualPerpOrder
    from app.models.virtual import VirtualOrder

# 注入函数签名
SpotPriceGetter = Callable[[str, str], Awaitable[Decimal | None]]
PerpMarkGetter = Callable[[str], Awaitable[Decimal | None]]
MarketOpenChecker = Callable[[str], bool]

_NOTE_MAX = 128


def should_trigger(
    kind: ConditionalKind,
    side: OrderSide,
    position_side: PositionSide,
    trigger_price: Decimal,
    price: Decimal,
) -> bool:
    """触发方向推导(刀1 模型 docstring 矩阵的实现)· 全部含等号(到价即触发)。

    LIMIT 看 side(BUY 低吸 P≤T · SELL 高抛 P≥T);
    SL/TP 看仓向(side 已被刀1 端点钉死为平仓方向):
      STOP_LOSS  平多 P≤T · 平空 P≥T;TAKE_PROFIT 平多 P≥T · 平空 P≤T。
    """
    if kind == ConditionalKind.LIMIT:
        return price <= trigger_price if side == OrderSide.BUY else price >= trigger_price
    closing_long = position_side == PositionSide.LONG
    if kind == ConditionalKind.STOP_LOSS:
        return price <= trigger_price if closing_long else price >= trigger_price
    # TAKE_PROFIT
    return price >= trigger_price if closing_long else price <= trigger_price


async def _spot_close_quantity(
    session: AsyncSession, row: ConditionalOrder,
) -> Decimal | None:
    """spot SL/TP quantity=NULL 平全仓:读当时活仓量(活仓口径 closed_at IS NULL)· 无仓返 None。"""
    account_id = await session.scalar(
        select(VirtualAccount.id).where(
            VirtualAccount.user_id == row.user_id,
            VirtualAccount.market == row.market,
        ),
    )
    if account_id is None:
        return None
    qty = await session.scalar(
        select(VirtualPosition.quantity).where(
            VirtualPosition.account_id == account_id,
            VirtualPosition.symbol == row.symbol,
            VirtualPosition.position_side == row.position_side,
            VirtualPosition.closed_at.is_(None),
        ),
    )
    return qty  # noqa: RET504 — 赋值供 mypy 窄化(直接 return 会 no-any-return)


async def process_active_conditionals(
    session: AsyncSession,
    *,
    get_spot_price: SpotPriceGetter,
    get_perp_mark: PerpMarkGetter,
    is_market_open: MarketOpenChecker,
) -> tuple[dict[str, int], list[int]]:
    """扫 ACTIVE 条件单 → 触发判断 → FOR UPDATE 二次确认 → 调唯一入口成交 → 状态流转。

    不 commit(调用方/壳 commit · 成交与 TRIGGERED 同事务原子)。
    返回 (stats, perp 成交订单 ids) —— perp 通知由壳在 commit 后 emit(照 perp.py #296 口径)。
    """
    stats = {
        "checked": 0, "triggered": 0, "expired": 0,
        "skipped_closed_market": 0, "skipped_no_price": 0, "skipped_raced": 0,
    }
    perp_filled_ids: list[int] = []

    rows = (
        await session.scalars(
            select(ConditionalOrder).where(
                ConditionalOrder.status == ConditionalStatus.ACTIVE,
            ),
        )
    ).all()

    for row in rows:
        # 股票休市整组跳过(开市后第一轮自然处理)· crypto 注入函数恒 True
        if not is_market_open(row.market):
            stats["skipped_closed_market"] += 1
            continue

        # 判价(无价跳过 · 照强平「不误杀」原则)
        if row.market == "crypto":
            price = await get_perp_mark(row.symbol)
        else:
            price = await get_spot_price(row.symbol, row.market)
        if price is None or price <= 0:
            stats["skipped_no_price"] += 1
            continue

        stats["checked"] += 1
        if not should_trigger(
            row.order_kind, row.side, row.position_side, row.trigger_price, price,
        ):
            continue

        # 命中 → 行锁 + status==ACTIVE 二次确认(幂等核心:并发撤单/重复触发都在这挡住)
        locked = await _lock_active(session, row.id)
        if locked is None:
            stats["skipped_raced"] += 1
            continue

        # ── 成交(🔴 只调唯一入口 · 本文件不含任何撮合逻辑)────────────────────
        order: VirtualOrder | VirtualPerpOrder
        if locked.market == "crypto":
            async def _mark(symbol: str) -> Decimal | None:
                return await get_perp_mark(symbol)

            if locked.order_kind == ConditionalKind.LIMIT:
                # perp 限价单 → 开仓唯一入口 route_open_perp(与平仓 route_close_perp 对称)·
                # 命中即开仓:position_side LONG 开多 / SHORT 开空;
                # leverage/margin/margin_mode 由刀1 端点保证非空(perp LIMIT 必填)。
                if (
                    locked.leverage is None
                    or locked.margin is None
                    or locked.margin_mode is None
                ):
                    # 防御:理论不达(端点强制必填)· legacy/脏数据兜底 + mypy 窄化
                    locked.status = ConditionalStatus.EXPIRED
                    locked.note = "perp 限价单缺开仓参数(leverage/margin/mode)"
                    await session.flush()
                    stats["expired"] += 1
                    continue
                order = await route_open_perp(
                    session,
                    user_id=locked.user_id,
                    symbol=locked.symbol,
                    side=PerpSide[locked.position_side.name],  # LONG 开多 / SHORT 开空
                    leverage=locked.leverage,
                    margin=locked.margin,
                    quantity=locked.quantity,
                    preferred_mode=MarginMode(locked.margin_mode),
                    get_mark_price=_mark,
                )
            else:
                # perp SL/TP → route_close_perp(quantity=NULL 平全仓 · 按活仓 mode 自动分流)
                order = await route_close_perp(
                    session,
                    user_id=locked.user_id,
                    symbol=locked.symbol,
                    quantity=locked.quantity,
                    close_all=locked.quantity is None,
                    get_mark_price=_mark,
                )
        else:
            qty = locked.quantity
            if qty is None:  # spot SL/TP 平全仓:读当时活仓量
                qty = await _spot_close_quantity(session, locked)
                if qty is None or qty <= 0:
                    locked.status = ConditionalStatus.EXPIRED
                    locked.note = "触发时无可平持仓"
                    await session.flush()
                    stats["expired"] += 1
                    continue

            async def _spot(symbol: str, market: str) -> Decimal | None:
                return await get_spot_price(symbol, market)

            fetcher: PriceFetcher = _spot
            order = await place_market_order(
                session,
                PlaceOrderRequest(
                    user_id=locked.user_id,
                    symbol=locked.symbol,
                    market=locked.market,
                    side=locked.side,
                    quantity=qty,
                    position_side=locked.position_side,
                    notify=True,  # 成交通知经唯一入口自动继承
                ),
                fetcher,
            )

        # ── 状态流转(与成交同事务 · 调用方 commit 原子落库)──────────────────
        locked.triggered_order_id = order.id  # 成交/拒单都回填(审计链)
        if order.status == OrderStatus.FILLED:
            locked.status = ConditionalStatus.TRIGGERED
            stats["triggered"] += 1
            if locked.market == "crypto":
                perp_filled_ids.append(order.id)
        else:
            locked.status = ConditionalStatus.EXPIRED
            locked.note = (order.reject_reason or "触发成交被拒")[:_NOTE_MAX]
            stats["expired"] += 1
        # 状态流转落 flush(房规:调用方 commit;flush 保证同事务内可见 · 不靠 autoflush 时机)
        await session.flush()

    return stats, perp_filled_ids


async def _lock_active(session: AsyncSession, cond_id: int) -> ConditionalOrder | None:
    """FOR UPDATE 锁行 + status==ACTIVE 条件(照 perp_liquidation 防竞争范式)。"""
    locked = await session.scalar(
        select(ConditionalOrder)
        .where(
            ConditionalOrder.id == cond_id,
            ConditionalOrder.status == ConditionalStatus.ACTIVE,
        )
        .with_for_update(),
    )
    return locked  # noqa: RET504 — 同上 · mypy 窄化需要
