"""虚拟交易路由 · /api/v1/virtual/* · 0008 v2。

8 个端点 · 全部 CurrentUserDep + 三独立子账户 + 原币种,无 FX。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import delete, desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ClickHouseDep, CurrentUserDep
from app.core.database import get_db
from app.models.conditional_order import (
    ConditionalKind,
    ConditionalOrder,
    ConditionalStatus,
)
from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.models.virtual import (
    MARKET_CURRENCY,
    OrderSide,
    PositionSide,
    SnapshotTrigger,
    VirtualAccount,
    VirtualEquitySnapshot,
    VirtualOrder,
    VirtualPosition,
)
from app.schemas.conditional_order import (
    ConditionalOrderCreate,
    ConditionalOrderResponse,
)
from app.schemas.market import Market
from app.schemas.virtual import (
    AccountActivateIn,
    AccountResponse,
    AccountSummaryResponse,
    AiOrderRequest,
    AiOrderResponse,
    AiPlanOrderRequest,
    EquityCurvesResponse,
    EquitySnapshotResponse,
    HkBoardLotResponse,
    OrderPlaceIn,
    OrderResponse,
    PositionResponse,
    PositionWithQuoteResponse,
)
from app.services.bot import order as bot_order
from app.services.clickhouse_client import ClickHouseClient
from app.services.data_sources.base import BaseDataSource
from app.services.data_sources.exceptions import DataSourceError
from app.services.hk_board_lot import resolve_hk_board_lot
from app.services.hk_pool import normalize_hk_code
from app.services.kline_freshness import get_fresh_kline
from app.services.virtual_trading.engine import (
    PlaceOrderRequest,
    PriceFetcher,
    place_market_order,
)
from app.services.virtual_trading.equity import (
    aggregate_portfolio,
    snapshot_equity_for_account,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/virtual", tags=["virtual"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


# ===== 价格 fetcher · 注入式 =====


def make_price_fetcher(
    ch: ClickHouseClient, *, crypto_source: BaseDataSource | None = None,
) -> PriceFetcher:
    """走 ClickHouse 拉最新 1d K 的 close · cache-aside 同源。

    刀A2-1 甲案:crypto(spot)末根过期时经 get_fresh_kline 回源刷新 ——
    撮合/估值价不再吃 stale kline 快照(BTC/USDT 停 5/31 价偏 18% 事故)。
    cn/us/hk 有采集任务保新鲜、crypto_source=None(测试/无 lifespan)时,
    均退化为纯读缓存 = 原行为。🔴 只换取数路径 · 撮合入口/engine 零碰。
    """

    async def fetcher(symbol: str, market: str) -> Decimal | None:
        # market 在 engine 层已校验 Market Literal,但 fetcher 签名宽容 str
        try:
            rows = await get_fresh_kline(
                ch,
                symbol=symbol,
                market=market,  # type: ignore[arg-type]
                period="1d",
                limit=1,
                source=crypto_source if market == "crypto" else None,
            )
        except DataSourceError:
            # 空缓存 + 回源失败 → 维持「无法取价 → 拒单」语义(不冒 500)
            return None
        if not rows:
            return None
        return Decimal(str(rows[-1].close))

    return fetcher


def _crypto_source_of(request: Request) -> BaseDataSource | None:
    """app.state 取 crypto spot source(lifespan 单例)· 测试无 lifespan 时 None=纯读缓存。"""
    return getattr(request.app.state, "crypto_source", None)


# ===== /accounts CRUD =====


@router.get(
    "/accounts",
    response_model=list[AccountResponse],
    summary="当前用户已激活的全部子账户(0~3)",
)
async def list_accounts(
    current_user: CurrentUserDep, db: DbDep,
) -> list[AccountResponse]:
    accounts = (
        await db.scalars(
            select(VirtualAccount)
            .where(VirtualAccount.user_id == current_user.id)
            .order_by(VirtualAccount.market),
        )
    ).all()
    return [AccountResponse.model_validate(a) for a in accounts]


@router.get(
    "/accounts/{market}",
    response_model=AccountResponse,
    summary="单市场子账户详情(404 = 未激活)",
)
async def get_account(
    market: Market, current_user: CurrentUserDep, db: DbDep,
) -> AccountResponse:
    account = await db.scalar(
        select(VirtualAccount).where(
            VirtualAccount.user_id == current_user.id,
            VirtualAccount.market == market,
        ),
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该市场资金未激活",
        )
    return AccountResponse.model_validate(account)


@router.put(
    "/accounts/{market}",
    response_model=AccountResponse,
    summary="激活 / 重置市场子账户(重置会清空活仓 + 曲线)",
)
async def activate_or_reset_account(
    market: Market,
    payload: AccountActivateIn,
    current_user: CurrentUserDep,
    db: DbDep,
) -> AccountResponse:
    currency = MARKET_CURRENCY[market]
    capital = payload.initial_capital

    # 检查是否已存在(已激活)→ 走重置路径
    existing = await db.scalar(
        select(VirtualAccount).where(
            VirtualAccount.user_id == current_user.id,
            VirtualAccount.market == market,
        ),
    )

    if existing is not None:
        # 重置:清活仓 + 清快照 + 重写 cash/realized
        await db.execute(
            delete(VirtualPosition).where(
                VirtualPosition.account_id == existing.id,
                VirtualPosition.closed_at.is_(None),
            ),
        )
        await db.execute(
            delete(VirtualEquitySnapshot).where(
                VirtualEquitySnapshot.account_id == existing.id,
            ),
        )
        existing.initial_capital = capital
        existing.cash_balance = capital
        existing.realized_pnl = Decimal("0")
        await db.commit()
        await db.refresh(existing)
        return AccountResponse.model_validate(existing)

    # 首次激活 → 走 pg_insert 路径
    stmt = (
        pg_insert(VirtualAccount)
        .values(
            user_id=current_user.id,
            market=market,
            currency=currency,
            initial_capital=capital,
            cash_balance=capital,
        )
        .returning(VirtualAccount)
    )
    result = await db.execute(stmt)
    account = result.scalar_one()
    await db.commit()
    return AccountResponse.model_validate(account)


# ===== /portfolio =====


@router.get(
    "/portfolio",
    response_model=list[AccountSummaryResponse],
    summary="聚合 · 全部已激活市场 + 活仓 + 实时估值",
)
async def get_portfolio(
    request: Request, ch: ClickHouseDep, current_user: CurrentUserDep, db: DbDep,
) -> list[AccountSummaryResponse]:
    fetcher = make_price_fetcher(ch, crypto_source=_crypto_source_of(request))
    summaries = await aggregate_portfolio(
        db, user_id=current_user.id, price_fetcher=fetcher,
    )
    return [
        AccountSummaryResponse(
            account_id=s.account_id,
            market=s.market,
            currency=s.currency,
            initial_capital=s.initial_capital,
            cash_balance=s.cash_balance,
            realized_pnl=s.realized_pnl,
            positions=[
                PositionWithQuoteResponse(
                    id=p.id,
                    symbol=p.symbol,
                    market=p.market,
                    position_side=p.position_side,
                    quantity=p.quantity,
                    avg_entry_price=p.avg_entry_price,
                    current_price=p.current_price,
                    unrealized_pnl=p.unrealized_pnl,
                    value=p.value,
                )
                for p in s.positions
            ],
            positions_value=s.positions_value,
            total_equity=s.total_equity,
        )
        for s in summaries
    ]


# ===== /orders =====


@router.post(
    "/orders",
    response_model=OrderResponse,
    summary="市价单下单 · 200 + status=filled/rejected",
)
async def place_order(
    request: Request,
    payload: OrderPlaceIn,
    ch: ClickHouseDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> OrderResponse:
    fetcher = make_price_fetcher(ch, crypto_source=_crypto_source_of(request))
    # 港股按手取整(board lot)· ★全程虚拟 · 复用 place_market_order · 不接真实通道。
    #   floor(qty/lot)*lot:不能买零散股 · lot 取自 lot 表(HKEX 官方 ~2406 · 表无回退 18 种子)。
    #   不在池 → 拒;不足一手 → 拒。cn/us/crypto 不进此分支(零影响)。
    quantity = payload.quantity
    if payload.market == "hk":
        lot = await resolve_hk_board_lot(db, payload.symbol)
        if lot is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该标的不在港股可下单池",
            )
        lots = int(quantity // lot)
        if lots < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"港股按手交易 · 每手 {lot} 股 · 最少下单 1 手({lot} 股)",
            )
        quantity = Decimal(lots * lot)
    req = PlaceOrderRequest(
        user_id=current_user.id,
        symbol=payload.symbol,
        market=payload.market,
        side=payload.side,
        position_side=payload.position_side,
        quantity=quantity,
    )
    order = await place_market_order(db, req, fetcher)
    await db.commit()
    return _serialize_order(order)


@router.get(
    "/hk-board-lot",
    response_model=HkBoardLotResponse,
    summary="港股每手股数(board lot)· 下单按手取整 / UI 提示用 · 只读",
)
async def get_hk_board_lot(
    db: DbDep,
    symbol: str = Query(..., min_length=1, description="港股代码 · 容错任意位数 / .HK 后缀"),
) -> HkBoardLotResponse:
    """返回港股某标的每手股数 · 不在下单池(lot 表 ~2406 + 18 种子兜底)→ 404。

    ★ 只读查询 · 不下单、不触账户;lot 优先 HKEX 官方 lot 表(worker 每日采)· 表无回退 18 种子。
    """
    lot = await resolve_hk_board_lot(db, symbol)
    if lot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该标的不在港股可下单池",
        )
    return HkBoardLotResponse(symbol=normalize_hk_code(symbol), board_lot=lot)


@router.post(
    "/ai-order",
    response_model=AiOrderResponse,
    summary="AI 建议一键模拟下单 · source=ai_signal · 同一虚拟撮合引擎",
)
async def place_ai_order(
    payload: AiOrderRequest,
    ch: ClickHouseDep,
    current_user: CurrentUserDep,
    db: DbDep,
) -> AiOrderResponse:
    """AI 决策卡「一键模拟下单」· 构造 source='ai_signal' 的 OrderIntent → 复用 U0 的 execute。

    🔴 红线:AI 下单【只能】走现有虚拟撮合引擎(execute → place_market_order /
       route_open_perp / route_close_perp),不新开下单出口、绝不接真实交易通道。
    二次确认:由前端 AiOrderConfirmDialog 保证(与手动下单同口径)· 本端点只在确认后被调用。
    仓位:execute 内部按用户 BotOrderPreset 派生(拍板③),本端点不收数量。
    港股:execute 内派生数量按手取整(resolve_hk_board_lot · 不在池 / 不足一手拒 · 同手动)。
    现货 sell(拍板④):execute → 有持仓才平、无持仓返回「无可平持仓」· 绝不裸做空。
    """
    # 方向必须是该市场合法方向(cn/us/hk=buy/sell · crypto=open_long/open_short)
    # 港股已接入(bot_order.execute 内按手取整 · 不在池 / 不足一手拒 · 同手动虚拟引擎)
    if not bot_order.direction_valid(payload.market, payload.direction):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"市场 {payload.market} 不支持方向 {payload.direction}",
        )
    intent = bot_order.OrderIntent(
        market=payload.market,
        symbol=payload.symbol,
        direction=payload.direction,
        source="ai_signal",
    )
    # ★ 走 U0 的 execute(db, ch, user_id, intent)· 与手动单 / bot 单同一虚拟撮合引擎
    #   execute 内部按市场分流(现货 place_market_order / 加密 perp_dispatcher)并 commit。
    #   notify_user=True:网页 AI 一键路径恢复成交异步推送(bot 默认 False 保持 #296 去重)。
    result = await bot_order.execute(db, ch, current_user.id, intent, notify_user=True)
    return AiOrderResponse(filled=result.filled, title=result.title, detail=result.detail)


async def _floor_spot_qty(
    db: AsyncSession, market: str, symbol: str, raw_qty: Decimal,
) -> Decimal | None:
    """现货数量按市场最小交易单位下取整(hk 按手 / cn 100 股 / us 整股)· 不足→None。"""
    if market == "hk":
        lot = await resolve_hk_board_lot(db, symbol)
        if lot is None:
            return None
        units = int(raw_qty // lot)
        return Decimal(units * lot) if units > 0 else None
    if market == "cn":
        units = int(raw_qty // 100)  # A 股 1 手 = 100 股
        return Decimal(units * 100) if units > 0 else None
    n = int(raw_qty)  # us 整股
    return Decimal(n) if n > 0 else None


@router.post(
    "/ai-plan-order",
    response_model=ConditionalOrderResponse,
    summary="按 AI 交易计划入场价挂限价单 · 复用 conditional LIMIT · 同一虚拟撮合",
)
async def place_ai_plan_order(
    payload: AiPlanOrderRequest, current_user: CurrentUserDep, db: DbDep,
) -> ConditionalOrderResponse:
    """决策卡「按计划入场价挂限价单」· entry_price → trigger_price · 仓位走 BotOrderPreset。

    🔴 红线:复用现成 create_conditional_order(LIMIT)· 触发由 60s 扫描器走唯一虚拟撮合入口
       (route_open_perp / place_market_order)· 不新增下单出口、绝不接真实交易。
    crypto:perp 限价开仓(杠杆/保证金来自预设)· spot:仅限价买入(数量=预设名义/入场价下取整)。
    """
    if not bot_order.direction_valid(payload.market, payload.direction):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"市场 {payload.market} 不支持方向 {payload.direction}",
        )
    preset = await bot_order.load_preset(db, current_user.id)

    if payload.market == "crypto":
        is_long = payload.direction == "open_long"
        leverage = preset.perp_leverage
        margin = (preset.perp_notional_usdt / Decimal(leverage)).quantize(Decimal("0.0001"))
        create = ConditionalOrderCreate(
            symbol=payload.symbol,
            market="crypto",
            order_kind=ConditionalKind.LIMIT,
            side=OrderSide.BUY if is_long else OrderSide.SELL,
            position_side=PositionSide.LONG if is_long else PositionSide.SHORT,
            trigger_price=payload.entry_price,
            leverage=leverage,
            margin=margin,
            margin_mode=MarginMode(preset.perp_margin_mode),
        )
    else:
        if payload.direction != "buy":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="现货仅支持按计划价限价买入(看空请走平仓,不经此端点)",
            )
        raw_qty = preset.spot_notional(payload.market) / payload.entry_price
        qty = await _floor_spot_qty(db, payload.market, payload.symbol, raw_qty)
        if qty is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="按预设名义与入场价算出的数量不足一个最小交易单位",
            )
        create = ConditionalOrderCreate(
            symbol=payload.symbol,
            market=payload.market,
            order_kind=ConditionalKind.LIMIT,
            side=OrderSide.BUY,
            position_side=PositionSide.LONG,
            trigger_price=payload.entry_price,
            quantity=qty,
        )
    return await create_conditional_order(create, current_user, db)


@router.get(
    "/orders",
    response_model=list[OrderResponse],
    summary="订单流水 · cursor 翻页",
)
async def list_orders(
    current_user: CurrentUserDep,
    db: DbDep,
    market: Market | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    before_id: int | None = Query(None, description="cursor · 拿小于此 id 的"),
) -> list[OrderResponse]:
    # 仅当前用户的子账户下的订单
    stmt = (
        select(VirtualOrder)
        .join(VirtualAccount, VirtualAccount.id == VirtualOrder.account_id)
        .where(VirtualAccount.user_id == current_user.id)
        .order_by(desc(VirtualOrder.id))
        .limit(limit)
    )
    if market is not None:
        stmt = stmt.where(VirtualOrder.market == market)
    if before_id is not None:
        stmt = stmt.where(VirtualOrder.id < before_id)
    orders = (await db.scalars(stmt)).all()
    return [_serialize_order(o) for o in orders]


# ===== /positions =====


@router.get(
    "/positions",
    response_model=list[PositionResponse],
    summary="持仓列表(默认活仓 · include_closed=true 含历史)",
)
async def list_positions(
    current_user: CurrentUserDep,
    db: DbDep,
    include_closed: bool = Query(False),
    market: Market | None = Query(None),
) -> list[PositionResponse]:
    stmt = (
        select(VirtualPosition)
        .join(VirtualAccount, VirtualAccount.id == VirtualPosition.account_id)
        .where(VirtualAccount.user_id == current_user.id)
        .order_by(
            VirtualPosition.closed_at.is_(None).desc(),
            desc(VirtualPosition.opened_at),
        )
    )
    if not include_closed:
        stmt = stmt.where(VirtualPosition.closed_at.is_(None))
    if market is not None:
        stmt = stmt.where(VirtualPosition.market == market)
    positions = (await db.scalars(stmt)).all()
    return [PositionResponse.model_validate(p) for p in positions]


# ===== /equity-curves =====


@router.get(
    "/equity-curves",
    response_model=EquityCurvesResponse,
    summary="多市场权益曲线(按 market 分组)",
)
async def get_equity_curves(
    current_user: CurrentUserDep,
    db: DbDep,
    days: int = Query(30, ge=1, le=365),
) -> EquityCurvesResponse:
    since = datetime.now(UTC) - timedelta(days=days)
    stmt = (
        select(VirtualEquitySnapshot)
        .join(
            VirtualAccount,
            VirtualAccount.id == VirtualEquitySnapshot.account_id,
        )
        .where(
            VirtualAccount.user_id == current_user.id,
            VirtualEquitySnapshot.snapshot_at >= since,
        )
        .order_by(VirtualEquitySnapshot.snapshot_at)
    )
    snapshots = (await db.scalars(stmt)).all()

    curves: dict[str, list[EquitySnapshotResponse]] = {}
    for s in snapshots:
        market = s.market
        if market not in curves:
            curves[market] = []
        curves[market].append(EquitySnapshotResponse.model_validate(s))

    return EquityCurvesResponse(curves=curves)


# ===== 内部 helper =====


def _serialize_order(order: VirtualOrder) -> OrderResponse:
    """统一序列化 · 处理临时未持久化的 rejected 订单(id=None)。"""
    return OrderResponse(
        id=order.id if order.id else None,
        account_id=order.account_id if order.account_id else None,
        symbol=order.symbol,
        market=order.market,
        side=order.side,
        position_side=order.position_side,
        order_type=order.order_type,
        quantity=order.quantity,
        price=order.price,
        notional=order.notional,
        commission=order.commission,
        slippage_cost=order.slippage_cost,
        realized_pnl=order.realized_pnl,
        status=order.status,
        reject_reason=order.reject_reason,
        placed_at=order.placed_at if order.id else None,
        filled_at=order.filled_at,
    )


# ════════════════════════════════════════════════════════════════════════════
# 条件单挂单簿(ADR 0041 刀1)· 挂 / 撤 / 列
# 🔴 红线:这些端点只读写 conditional_orders 表 —— 不调 place_market_order、不碰 engine。
#   本刀条件单【不会触发成交】(刀2 扫描器才接触发),是有意分界。
# ════════════════════════════════════════════════════════════════════════════

# SL/TP 的平仓方向:LONG 仓只能 SELL 平 · SHORT 仓只能 BUY 平(与触发矩阵自洽,防脏数据)
_CLOSING_SIDE = {PositionSide.LONG: OrderSide.SELL, PositionSide.SHORT: OrderSide.BUY}
# perp 限价开仓方向:开多=BUY+LONG · 开空=SELL+SHORT(二期刀1 · 防 BUY+SHORT 这类矛盾脏数据)
_OPENING_SIDE = {PositionSide.LONG: OrderSide.BUY, PositionSide.SHORT: OrderSide.SELL}


def _has_perp_open_fields(payload: ConditionalOrderCreate) -> bool:
    """是否携带 perp 开仓参数(leverage/margin/margin_mode)· 二期刀1 仅 perp 限价单可带。"""
    return (
        payload.leverage is not None
        or payload.margin is not None
        or payload.margin_mode is not None
    )


async def _has_active_position(
    db: AsyncSession, account_id: int, market: str, symbol: str, position_side: PositionSide,
) -> bool:
    """SL/TP 挂单软校验:有无对应活仓(纯读 · 活仓条件照 engine 口径 closed_at IS NULL)。"""
    if market == "crypto":
        # crypto 语义=perp(symbol Binance 风格)· PerpSide 与 PositionSide 同名映射
        return (
            await db.scalar(
                select(VirtualPerpPosition.id).where(
                    VirtualPerpPosition.account_id == account_id,
                    VirtualPerpPosition.symbol == symbol,
                    VirtualPerpPosition.side == PerpSide[position_side.name],
                    VirtualPerpPosition.closed_at.is_(None),
                ),
            )
            is not None
        )
    return (
        await db.scalar(
            select(VirtualPosition.id).where(
                VirtualPosition.account_id == account_id,
                VirtualPosition.symbol == symbol,
                VirtualPosition.position_side == position_side,
                VirtualPosition.closed_at.is_(None),
            ),
        )
        is not None
    )


@router.post(
    "/conditional-orders",
    response_model=ConditionalOrderResponse,
    summary="挂条件单(限价/止损/止盈)· 本刀仅挂单簿,触发成交随刀2",
)
async def create_conditional_order(
    payload: ConditionalOrderCreate, current_user: CurrentUserDep, db: DbDep,
) -> ConditionalOrderResponse:
    """挂单不冻结资金(ADR 0041 决策二)· 触发时由 place_market_order 现有余额校验把关。"""
    symbol = payload.symbol.strip()
    if payload.market == "crypto":
        symbol = symbol.upper().replace("/", "")  # perp 语义 · Binance 风格(与持仓表一致)

    if payload.order_kind == ConditionalKind.LIMIT:
        if payload.market == "crypto":
            # 二期刀1:perp 限价单放开挂单。perp=开仓单 → 需杠杆/保证金/仓位模式
            # (route_open_perp 口径,用 margin×leverage 定仓 · quantity 可空)。
            # ⛔ 本刀【不接触发→开仓】:触发器对 perp LIMIT 仍走现有 EXPIRED 防御(半成品安全);
            #    真正触发开仓(route_open_perp)留刀2。挂单能挂进 ACTIVE,被扫到即 EXPIRED。
            if (
                payload.leverage is None
                or payload.margin is None
                or payload.margin_mode is None
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="perp 限价单须填写杠杆 / 保证金 / 仓位模式",
                )
            expected_open = _OPENING_SIDE[payload.position_side]
            if payload.side != expected_open:
                msg = (
                    f"perp 限价开仓:{payload.position_side.value} 仓须用 "
                    f"{expected_open.value} 方向"
                )
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
        else:
            # spot 限价:quantity 必填;不接受 perp 开仓参数(保持数据干净)
            if payload.quantity is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="限价单必须填写数量",
                )
            if _has_perp_open_fields(payload):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="现货限价单不接受杠杆 / 保证金 / 仓位模式",
                )
    else:
        # SL/TP(未决②定型 (a):持仓后独立挂)—— side 必须是该仓向的平仓方向 + 须有活仓
        if _has_perp_open_fields(payload):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="止损/止盈单不接受杠杆 / 保证金 / 仓位模式",
            )
        expected = _CLOSING_SIDE[payload.position_side]
        if payload.side != expected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"止损/止盈是平仓单:{payload.position_side.value} 仓须用 {expected.value}",
            )
        account = await db.scalar(
            select(VirtualAccount).where(
                VirtualAccount.user_id == current_user.id,
                VirtualAccount.market == payload.market,
            ),
        )
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该市场资金未设置 · 请先去个人设置页填写",
            )
        if not await _has_active_position(
            db, account.id, payload.market, symbol, payload.position_side,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无对应活仓 · 止损/止盈需先持有该方向仓位",
            )

    row = ConditionalOrder(
        user_id=current_user.id,
        symbol=symbol,
        market=payload.market,
        order_kind=payload.order_kind,
        side=payload.side,
        position_side=payload.position_side,
        trigger_price=payload.trigger_price,
        quantity=payload.quantity,
        # 二期刀1:perp 限价开仓字段(spot/SLTP 落 None)· margin_mode 存纯字符串
        leverage=payload.leverage,
        margin=payload.margin,
        margin_mode=payload.margin_mode.value if payload.margin_mode else None,
        expires_at=payload.expires_at,
        status=ConditionalStatus.ACTIVE,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return ConditionalOrderResponse.model_validate(row)


@router.get(
    "/conditional-orders",
    response_model=list[ConditionalOrderResponse],
    summary="我的条件单(倒序 · 可按状态过滤)",
)
async def list_conditional_orders(
    current_user: CurrentUserDep,
    db: DbDep,
    status_filter: Annotated[ConditionalStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ConditionalOrderResponse]:
    stmt = (
        select(ConditionalOrder)
        .where(ConditionalOrder.user_id == current_user.id)
        # created_at 平局(同事务 now() 恒定)时顺序未定义 → 显式 id tie-break
        # (项目铁律:涉及「最新」语义的 ORDER BY 必须显式,不依赖偶然 · 0010 先例)
        .order_by(desc(ConditionalOrder.created_at), desc(ConditionalOrder.id))
        .limit(limit)
    )
    if status_filter is not None:
        stmt = stmt.where(ConditionalOrder.status == status_filter)
    rows = (await db.execute(stmt)).scalars().all()
    return [ConditionalOrderResponse.model_validate(r) for r in rows]


@router.delete(
    "/conditional-orders/{cond_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="撤条件单(仅本人 ACTIVE · 状态机转 cancelled 留审计)",
)
async def cancel_conditional_order(
    cond_id: int, current_user: CurrentUserDep, db: DbDep,
) -> None:
    """ADR 0041 状态机:撤单 = ACTIVE → CANCELLED(保留行供审计,非物理删除);
    鉴权与 404 口径照 alert_rules 范式(不存在/非本人/非 ACTIVE 统一 404,不泄露状态)。
    """
    row = await db.scalar(
        select(ConditionalOrder).where(
            ConditionalOrder.id == cond_id,
            ConditionalOrder.user_id == current_user.id,
            ConditionalOrder.status == ConditionalStatus.ACTIVE,
        ),
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="条件单不存在或不可撤销",
        )
    row.status = ConditionalStatus.CANCELLED
    await db.commit()


# Public re-export for celery beat job
__all__ = ["router", "snapshot_equity_for_account", "SnapshotTrigger"]
