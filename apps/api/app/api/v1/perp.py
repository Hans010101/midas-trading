"""加密永续合约虚拟交易路由 · /api/v1/virtual/perp/* · ADR-0019 v2 · M2-C.1。

🔴 红线:全程【虚拟资金】· 绝不接任何真实交易 / 下单通道。撮合走 perp_engine。

3 个端点(全部 CurrentUserDep · 复用 0008 crypto USDT 子账户做钱包):
- POST /orders     · 开多 / 开空 / 平仓 · 200 + status=filled/rejected
- GET  /positions  · 合约持仓(默认活仓 · 含实时浮盈 / 强平距离 / ROE)
- GET  /orders     · 合约流水 · cursor 翻页

价源(§4.1 · M2-C.2.1 起):真标记价 mark price(crypto_premium_index · premiumIndex
  每分钟回源)· perp ticker 最新价兜底。注入式换源 —— 撮合/强平引擎核心逻辑不改。
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ClickHouseDep, CurrentUserDep
from app.core.database import get_db
from app.models.perp import (
    MarginMode,
    PerpSide,
    VirtualPerpFunding,
    VirtualPerpOrder,
    VirtualPerpPosition,
)
from app.models.virtual import OrderStatus, VirtualAccount
from app.schemas.perp import (
    PerpFundingResponse,
    PerpOrderPlaceIn,
    PerpOrderResponse,
    PerpPositionResponse,
)
from app.services.clickhouse_client import ClickHouseClient
from app.services.clickhouse_crypto import (
    select_premium_index_marks,
    select_tickers_by_symbols,
)
from app.services.notifications.emit import emit_perp_order
from app.services.virtual_trading.perp_dispatcher import (
    route_close_perp,
    route_open_perp,
)
from app.services.virtual_trading.perp_engine import PerpPriceFetcher
from app.services.virtual_trading.perp_fees import (
    liquidation_distance_pct,
    q_money,
    unrealized_pnl,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/virtual/perp", tags=["virtual-perp"])

DbDep = Annotated[AsyncSession, Depends(get_db)]

_QUOTES = ("USDT", "USDC", "BUSD", "FDUSD")


# ===== 价格 fetcher · 注入式(perp ticker 最新价)=====


def _to_ccxt(binance_symbol: str) -> str:
    """'BTCUSDT' → 'BTC/USDT'(perp ticker 表是 ccxt 风格)。"""
    for q in _QUOTES:
        if binance_symbol.endswith(q) and len(binance_symbol) > len(q):
            return f"{binance_symbol[: -len(q)]}/{q}"
    return binance_symbol


def make_perp_mark_price_fetcher(ch: ClickHouseClient) -> PerpPriceFetcher:
    """撮合/强平价源 · 真标记价(premiumIndex.mark_price)优先,perp ticker 最新价兜底。

    M2-C.2.1 起价源从 perp ticker last_price 切到真 mark price(crypto_premium_index)·
    撮合/强平引擎核心逻辑不改(注入式换源)。
    兜底:premium_index 无该 symbol(刚上市未采 / 采集瞬时缺)→ 退回 ticker last_price,
    保证 M2-C.1 撮合/强平零回归(不因价源切换而拒单 / 漏强平)。
    稳态(premium 每分钟刷)永远走 mark price;ticker 只是过渡/缺数安全网。
    symbol 为 Binance 风格无斜杠 'BTCUSDT'(premium_index 表一致)· ticker 兜底时转 ccxt。
    """

    async def fetcher(symbol: str) -> Decimal | None:
        marks = await select_premium_index_marks(ch._client, [symbol])  # noqa: SLF001
        mark = marks.get(symbol)
        if mark is not None and mark > 0:
            return mark
        # 兜底 · perp ticker 最新价(crypto_ticker_24h · ccxt 风格)
        ccxt_symbol = _to_ccxt(symbol)
        tickers = await select_tickers_by_symbols(
            ch._client,  # noqa: SLF001
            instrument="perp",
            symbols=[ccxt_symbol],
        )
        t = tickers.get(ccxt_symbol)
        if t is None or t.last_price <= 0:
            return None
        return Decimal(str(t.last_price))

    return fetcher


# ===== POST /orders =====


@router.post(
    "/orders",
    response_model=PerpOrderResponse,
    summary="合约下单(开多/开空/平仓)· 市价 · 200 + filled/rejected",
)
async def place_perp_order(
    payload: PerpOrderPlaceIn,
    ch: ClickHouseDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> PerpOrderResponse:
    fetcher = make_perp_mark_price_fetcher(ch)

    if payload.intent in ("open_long", "open_short"):
        side = PerpSide.LONG if payload.intent == "open_long" else PerpSide.SHORT
        assert payload.leverage is not None  # noqa: S101 · schema 已校验
        # MC-4:走 dispatcher 按 margin_mode 分流(默认 isolated · 零回归)
        order = await route_open_perp(
            db,
            user_id=current_user.id,
            symbol=payload.symbol,
            side=side,
            leverage=payload.leverage,
            margin=payload.margin,
            quantity=payload.quantity,
            preferred_mode=MarginMode(payload.margin_mode),
            get_mark_price=fetcher,
        )
    else:  # close · 按活仓 mode 自动分流
        order = await route_close_perp(
            db,
            user_id=current_user.id,
            symbol=payload.symbol,
            quantity=payload.quantity,
            close_all=payload.close_all,
            get_mark_price=fetcher,
        )

    await db.commit()
    logger.info(
        "[perp.order] user=%s symbol=%s intent=%s status=%s",
        current_user.id, payload.symbol, payload.intent, order.status,
    )
    # #296:commit 之后才 emit(避免"通知发了但事务回滚")· 仅成交单 · 旁路不影响下单
    if order.status == OrderStatus.FILLED:
        emit_perp_order(order.id)
    return _serialize_order(order)


# ===== GET /positions =====


@router.get(
    "/positions",
    response_model=list[PerpPositionResponse],
    summary="合约持仓(默认活仓 · include_closed=true 含历史)· 含实时浮盈/强平距离",
)
async def list_perp_positions(
    ch: ClickHouseDep,
    current_user: CurrentUserDep,
    db: DbDep,
    include_closed: bool = Query(False),
) -> list[PerpPositionResponse]:
    stmt = (
        select(VirtualPerpPosition)
        .join(VirtualAccount, VirtualAccount.id == VirtualPerpPosition.account_id)
        .where(VirtualAccount.user_id == current_user.id)
        .order_by(
            VirtualPerpPosition.closed_at.is_(None).desc(),
            desc(VirtualPerpPosition.opened_at),
        )
    )
    if not include_closed:
        stmt = stmt.where(VirtualPerpPosition.closed_at.is_(None))
    positions = (await db.scalars(stmt)).all()

    fetcher = make_perp_mark_price_fetcher(ch)
    out: list[PerpPositionResponse] = []
    for p in positions:
        mark = await fetcher(p.symbol) if p.closed_at is None else None
        upnl: Decimal | None = None
        dist: Decimal | None = None
        roe: Decimal | None = None
        if mark is not None:
            upnl = unrealized_pnl(p.side, p.entry_price, mark, p.quantity)
            dist = liquidation_distance_pct(mark, p.liquidation_price)
            roe = (
                q_money(upnl / p.initial_margin * Decimal("100"))
                if p.initial_margin > 0
                else None
            )
        out.append(
            PerpPositionResponse(
                id=p.id, symbol=p.symbol, side=p.side, leverage=p.leverage,
                # MC-4 暴露:'isolated' / 'cross' · MC-1 列已是 String 直接返
                margin_mode="cross" if p.margin_mode == "cross" else "isolated",
                quantity=p.quantity, entry_price=p.entry_price,
                initial_margin=p.initial_margin, liquidation_price=p.liquidation_price,
                realized_pnl=p.realized_pnl, fee_paid=p.fee_paid,
                funding_paid=p.funding_paid,
                opened_at=p.opened_at, closed_at=p.closed_at,
                close_reason=p.close_reason,
                mark_price=mark, unrealized_pnl=upnl,
                liquidation_distance_pct=dist, roe_pct=roe,
            ),
        )
    return out


# ===== GET /orders =====


@router.get(
    "/orders",
    response_model=list[PerpOrderResponse],
    summary="合约订单流水 · cursor 翻页",
)
async def list_perp_orders(
    current_user: CurrentUserDep,
    db: DbDep,
    symbol: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    before_id: int | None = Query(None, description="cursor · 拿小于此 id 的"),
) -> list[PerpOrderResponse]:
    stmt = (
        select(VirtualPerpOrder)
        .join(VirtualAccount, VirtualAccount.id == VirtualPerpOrder.account_id)
        .where(VirtualAccount.user_id == current_user.id)
        .order_by(desc(VirtualPerpOrder.id))
        .limit(limit)
    )
    if symbol is not None:
        stmt = stmt.where(VirtualPerpOrder.symbol == symbol)
    if before_id is not None:
        stmt = stmt.where(VirtualPerpOrder.id < before_id)
    orders = (await db.scalars(stmt)).all()
    return [_serialize_order(o) for o in orders]


# ===== GET /funding =====


@router.get(
    "/funding",
    response_model=list[PerpFundingResponse],
    summary="资金费结算流水(M2-C.2.2)· 倒序 · 可按 symbol 过滤",
)
async def list_perp_funding(
    current_user: CurrentUserDep,
    db: DbDep,
    symbol: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> list[PerpFundingResponse]:
    """本用户的资金费结算流水 · 只读(结算由 worker settle_funding 写)· 全程虚拟。"""
    stmt = (
        select(VirtualPerpFunding)
        .join(VirtualAccount, VirtualAccount.id == VirtualPerpFunding.account_id)
        .where(VirtualAccount.user_id == current_user.id)
        .order_by(desc(VirtualPerpFunding.funding_ts), desc(VirtualPerpFunding.id))
        .limit(limit)
    )
    if symbol is not None:
        stmt = stmt.where(VirtualPerpFunding.symbol == symbol)
    rows = (await db.scalars(stmt)).all()
    return [
        PerpFundingResponse(
            id=r.id, symbol=r.symbol, side=r.side,
            funding_rate=r.funding_rate, mark_price=r.mark_price,
            quantity=r.quantity, payment=r.payment,
            funding_ts=r.funding_ts, settled_at=r.settled_at,
        )
        for r in rows
    ]


# ===== 内部 =====


def _serialize_order(o: VirtualPerpOrder) -> PerpOrderResponse:
    """统一序列化 · 处理未激活拒单的临时 sentinel(id / account_id 为 0/None)。"""
    return PerpOrderResponse(
        id=o.id if o.id else None,
        account_id=o.account_id if o.account_id else None,
        position_id=o.position_id,
        symbol=o.symbol,
        action=o.action,
        leverage=o.leverage,
        quantity=o.quantity,
        price=o.price,
        notional=o.notional,
        margin_delta=o.margin_delta,
        fee=o.fee,
        realized_pnl=o.realized_pnl,
        status=o.status,
        reject_reason=o.reject_reason,
        is_liquidation=o.is_liquidation,
        placed_at=o.placed_at if o.id else None,
        filled_at=o.filled_at,
    )
