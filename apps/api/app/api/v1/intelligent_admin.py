"""智能交易 admin 端点(智能交易 PR-2 地基)· 🔴纯虚拟绝不真单。

★独立模块(架构守卫 test_admin_domain_no_engine_no_login_import 禁 admin.py import virtual_trading)·
直接在 v1 router 注册(admin.py 不 import 本模块)· 挂 AdminDep(403 边界)。
PR-2 = 开关 + 账户 + 账户管理(金额可改/清零)· 看板端点(positions/history/stats)= PR-6。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep, ClickHouseDep
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.perp import PerpSide, VirtualPerpPosition
from app.models.user import User
from app.models.virtual import VirtualAccount
from app.services.clickhouse_crypto import select_premium_index_marks
from app.services.virtual_trading import account_admin
from app.services.virtual_trading.intelligent import account as intelligent_account
from app.services.virtual_trading.intelligent import guard as intelligent_guard
from app.services.virtual_trading.intelligent import stats as intelligent_stats
from app.services.virtual_trading.perp_cross_engine import _cross_available_margin
from app.services.virtual_trading.perp_fees import unrealized_pnl

router = APIRouter(prefix="/admin/intelligent", tags=["intelligent"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _intelligent_account_row(db: AsyncSession) -> VirtualAccount | None:
    acc: VirtualAccount | None = await db.scalar(
        select(VirtualAccount).where(
            VirtualAccount.user_id.in_(
                select(User.id).where(User.email == intelligent_account.INTELLIGENT_BOT_EMAIL),
            ),
            VirtualAccount.market == intelligent_account.INTELLIGENT_MARKET,
        ),
    )
    return acc


class IntelligentStatus(BaseModel):
    enabled: bool             # 智能交易开关(默认 OFF)
    account_ready: bool       # 智能交易账户已建
    account_value: float      # ★账户总价值(权益·浮动)= 现金 + Σ未实现浮盈浮亏 · 复用引擎算法
    initial_capital: float    # ★起始资金(可改 · 取自 account.initial_capital · 默认 10万U)
    cash_balance: float       # 账户现金(只扣手续费 · 不含浮盈)
    open_positions: int       # 当前活仓数
    open_margin: float        # ★每单本金(U·可调 10-10000·默认 100)
    open_leverage: int        # ★杠杆(可调 1-20·默认 5·不影响 ATR 止损止盈价)
    max_positions: int        # ★最大总持仓数(可调·默认 50·到上限不开新)
    allow_long: bool          # ★PR-8 允许开多(默认 ON·OFF=滤掉做多信号)
    allow_short: bool         # ★PR-8 允许开空(默认 ON·OFF=滤掉做空信号)


class IntelligentToggleIn(BaseModel):
    enabled: bool


class CapitalIn(BaseModel):
    amount: float             # 起始资金(> 0)


async def _status(db: AsyncSession, ch: ClickHouseDep) -> IntelligentStatus:
    redis = await get_redis()
    enabled = await intelligent_guard.is_enabled(redis)
    acc = await _intelligent_account_row(db)
    open_n = await intelligent_guard.count_open_positions(db, acc.id) if acc is not None else 0
    default_cap = float(intelligent_account.INTELLIGENT_INITIAL_CAPITAL)
    open_margin = await intelligent_guard.get_open_margin(redis)        # ★每单本金
    open_leverage = await intelligent_guard.get_open_leverage(redis)    # ★杠杆
    max_positions = await intelligent_guard.get_max_positions(redis)    # ★最大总持仓
    allow_long = await intelligent_guard.get_allow_long(redis)          # ★PR-8 允许开多(全局)
    allow_short = await intelligent_guard.get_allow_short(redis)        # ★PR-8 允许开空(全局)
    account_value = 0.0
    if acc is not None:
        async def _fetch_mark(symbol: str) -> Decimal | None:
            marks = await select_premium_index_marks(ch._client, [symbol])  # noqa: SLF001
            return marks.get(symbol)

        # ★复用引擎 _cross_available_margin(equity=现金+ΣuPnL)· 零重写盈亏 · 与活仓浮盈同算法对得上
        equity, _used, _avail = await _cross_available_margin(db, acc, _fetch_mark)
        account_value = float(equity)
    return IntelligentStatus(
        enabled=enabled,
        account_ready=acc is not None,
        account_value=account_value,
        initial_capital=float(acc.initial_capital) if acc else default_cap,
        cash_balance=float(acc.cash_balance) if acc else 0.0,
        open_positions=open_n,
        open_margin=float(open_margin),
        open_leverage=open_leverage,
        max_positions=max_positions,
        allow_long=allow_long,
        allow_short=allow_short,
    )


@router.get("/status", summary="智能交易状态(开关/账户/起始资金/活仓)")
async def get_status(_admin: AdminDep, db: DbDep, ch: ClickHouseDep) -> IntelligentStatus:
    return await _status(db, ch)


@router.post("/toggle", summary="开/关智能交易(★默认 OFF · 开则首次建账户)")
async def toggle(
    payload: IntelligentToggleIn, _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> IntelligentStatus:
    """★开关 · 开启时幂等建智能交易账户(系统用户 + perp 钱包)· 开仓编排 = PR-4。"""
    redis = await get_redis()
    if payload.enabled:
        await intelligent_account.ensure_intelligent_account(db)
    await intelligent_guard.set_enabled(redis, payload.enabled)
    return await _status(db, ch)


@router.post("/account/reset", summary="★清零重来(删智能账户持仓+历史 · cash 重置初始)")
async def reset(_admin: AdminDep, db: DbDep, ch: ClickHouseDep) -> IntelligentStatus:
    """清零重置:删智能账户【持仓+历史】+ cash 重置 initial_capital · ★只该账户 · 不碰引擎。"""
    acc = await intelligent_account.ensure_intelligent_account(db)
    await account_admin.reset_account(db, acc)
    return await _status(db, ch)


@router.post("/account/capital", summary="★改起始资金(>0 · 清持仓 + 用新资金重来)")
async def set_capital(
    payload: CapitalIn, _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> IntelligentStatus:
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="起始资金必须 > 0")
    acc = await intelligent_account.ensure_intelligent_account(db)
    await account_admin.set_account_capital(db, acc, Decimal(str(payload.amount)))
    return await _status(db, ch)


# ── 开仓参数(每单本金 / 杠杆 / 最大单数 · 即时生效)──────────────────────
class OpenMarginIn(BaseModel):
    margin: float             # 每单本金(U·10-10000)


class OpenLeverageIn(BaseModel):
    leverage: int             # 杠杆(1-20)


class MaxPositionsIn(BaseModel):
    max_positions: int        # 最大总持仓数(> 0)


@router.post("/open-margin", summary="★设每单本金(U·10-10000 · 即时生效)")
async def set_open_margin(
    payload: OpenMarginIn, _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> IntelligentStatus:
    if not (10 <= payload.margin <= 10000):  # noqa: PLR2004
        raise HTTPException(status_code=400, detail="每单本金必须在 10-10000 U")
    redis = await get_redis()
    await intelligent_guard.set_open_margin(redis, Decimal(str(payload.margin)))
    return await _status(db, ch)


@router.post("/open-leverage", summary="★设杠杆(1-20 · 即时生效 · 不影响 ATR 止损止盈价)")
async def set_open_leverage(
    payload: OpenLeverageIn, _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> IntelligentStatus:
    if not (1 <= payload.leverage <= 20):  # noqa: PLR2004
        raise HTTPException(status_code=400, detail="杠杆必须在 1-20 倍")
    redis = await get_redis()
    await intelligent_guard.set_open_leverage(redis, payload.leverage)
    return await _status(db, ch)


@router.post("/max-positions", summary="★设最大总持仓数(>0 · 到上限不开新 · 即时生效)")
async def set_max_positions(
    payload: MaxPositionsIn, _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> IntelligentStatus:
    if payload.max_positions <= 0:
        raise HTTPException(status_code=400, detail="最大总持仓数必须 > 0")
    redis = await get_redis()
    await intelligent_guard.set_max_positions(redis, payload.max_positions)
    return await _status(db, ch)


# ── 方向过滤器(PR-8 · 允许做多/做空 · 默认 ON · 即时生效 · 只滤方向不改策略)──────
class AllowDirectionIn(BaseModel):
    which: str                # long / short
    on: bool                  # True=允许该方向 / False=滤掉该方向信号


@router.post("/allow-direction", summary="★设方向过滤(which=long/short · on · 即时生效)")
async def set_allow_direction(
    payload: AllowDirectionIn, _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
) -> IntelligentStatus:
    if payload.which not in ("long", "short"):
        raise HTTPException(status_code=400, detail="which 必须是 long/short")
    redis = await get_redis()
    if payload.which == "long":
        await intelligent_guard.set_allow_long(redis, payload.on)
    else:
        await intelligent_guard.set_allow_short(redis, payload.on)
    return await _status(db, ch)


# ── 策略参数(阈值 / 6 权重 / ATR 倍数 · 前向测试迭代调参 · 即时生效)──────────
_INDICATORS = ("boll", "macd", "ma", "rsi", "kdj", "extreme")


class StrategyParams(BaseModel):
    threshold: float                # 开仓阈值(> 0 · 默认 3.0)
    weights: dict[str, float]       # 6 指标权重(boll/macd/ma/rsi/kdj/extreme · ≥ 0)
    atr_stop_mult: float            # ATR 止损倍数(> 0 · 默认 2.0)
    atr_tp_mult: float              # ATR 止盈倍数(> 0 · 默认 4.0)


async def _strategy_params(redis: object) -> StrategyParams:
    return StrategyParams(
        threshold=await intelligent_guard.get_strategy_threshold(redis),
        weights=await intelligent_guard.get_strategy_weights(redis),
        atr_stop_mult=await intelligent_guard.get_strategy_atr_stop_mult(redis),
        atr_tp_mult=await intelligent_guard.get_strategy_atr_tp_mult(redis),
    )


@router.get("/strategy-params", summary="读策略参数(阈值/6权重/ATR倍数)")
async def get_strategy_params(_admin: AdminDep) -> StrategyParams:
    return await _strategy_params(await get_redis())


@router.post("/strategy-params", summary="★设策略参数(批量 · 阈值/6权重/ATR倍数 · 即时生效)")
async def set_strategy_params(payload: StrategyParams, _admin: AdminDep) -> StrategyParams:
    """前向测试迭代调参 · open/close 每轮读传 decide(纯函数)· 范围校验后逐项写 Redis。"""
    if payload.threshold <= 0:
        raise HTTPException(status_code=400, detail="阈值必须 > 0")
    if payload.atr_stop_mult <= 0 or payload.atr_tp_mult <= 0:
        raise HTTPException(status_code=400, detail="ATR 倍数必须 > 0")
    if set(payload.weights) != set(_INDICATORS):
        raise HTTPException(status_code=400, detail=f"权重必须含且仅含 {_INDICATORS}")
    if any(v < 0 for v in payload.weights.values()):
        raise HTTPException(status_code=400, detail="权重必须 ≥ 0")
    redis = await get_redis()
    await intelligent_guard.set_strategy_threshold(redis, payload.threshold)
    await intelligent_guard.set_strategy_atr_stop_mult(redis, payload.atr_stop_mult)
    await intelligent_guard.set_strategy_atr_tp_mult(redis, payload.atr_tp_mult)
    for ind, v in payload.weights.items():
        await intelligent_guard.set_strategy_weight(redis, ind, v)
    return await _strategy_params(redis)


# ── 看板:活仓 / 历史 / 统计(PR-6 · 前向测试 · ★做多做空 + 共振信号)──────


class IntelligentPosition(BaseModel):
    id: int
    symbol: str
    side: str                      # ★long / short(做多做空)
    leverage: int
    entry_price: float
    quantity: float
    margin: float                  # 本金(initial_margin)
    opened_at: str
    mark: float | None             # 当前标记价(无则 null)
    unrealized_pnl: float | None   # 浮盈 U(★复用引擎 unrealized_pnl · 做多做空对称)
    unrealized_pct: float | None   # 浮盈 % = uPnL / 本金
    stop_price: float | None       # ATR 止损价(PR-4 记 · PR-5 判)
    tp_price: float | None         # 2:1 止盈价
    signals: dict[str, object] | None  # ★共振明细(contributions + score)


class IntelligentTrade(BaseModel):
    symbol: str
    side: str                      # ★long / short
    leverage: int
    entry_price: float
    exit_price: float              # ≈ entry + realized_pnl/qty(纯价格反推)
    quantity: float
    pnl_usdt: float                # realized_pnl
    pnl_pct: float                 # realized_pnl / 本金
    close_reason: str | None       # stop_loss / take_profit / signal_reversal
    opened_at: str
    closed_at: str | None
    hold_seconds: int


class IntelligentPositionsPage(BaseModel):
    items: list[IntelligentPosition]
    total: int  # ★全部活仓数(前端算总页数)


@router.get("/positions", summary="智能交易当前活仓(含浮盈 + 共振 · ★分页 100/页)")
async def list_intelligent_positions(
    _admin: AdminDep, db: DbDep, ch: ClickHouseDep,
    offset: int = 0, limit: int = 100,
) -> IntelligentPositionsPage:
    acc = await _intelligent_account_row(db)
    if acc is None:
        return IntelligentPositionsPage(items=[], total=0)
    base_where = (
        VirtualPerpPosition.account_id == acc.id,
        VirtualPerpPosition.intelligent.is_(True),
        VirtualPerpPosition.closed_at.is_(None),
    )
    total = await db.scalar(
        select(func.count()).select_from(VirtualPerpPosition).where(*base_where),
    )
    rows = list(await db.scalars(
        select(VirtualPerpPosition)
        .where(*base_where)
        .order_by(VirtualPerpPosition.opened_at.desc())
        .offset(max(offset, 0))
        .limit(max(min(limit, 500), 1)),  # ★限 1~500 防滥用
    ))
    marks = (
        await select_premium_index_marks(ch._client, [r.symbol for r in rows]) if rows else {}  # noqa: SLF001
    )
    out: list[IntelligentPosition] = []
    for r in rows:
        mark = marks.get(r.symbol)
        # ★复用引擎 unrealized_pnl(做多做空对称 · 不重写盈亏 · 引擎零碰)
        upnl = unrealized_pnl(r.side, r.entry_price, mark, r.quantity) if mark is not None else None
        margin = r.initial_margin
        out.append(IntelligentPosition(
            id=r.id, symbol=r.symbol, side=r.side.value, leverage=r.leverage,
            entry_price=float(r.entry_price), quantity=float(r.quantity), margin=float(margin),
            opened_at=r.opened_at.isoformat(),
            mark=float(mark) if mark is not None else None,
            unrealized_pnl=float(upnl) if upnl is not None else None,
            unrealized_pct=float(upnl / margin) if upnl is not None and margin > 0 else None,
            stop_price=float(r.intelligent_stop_price) if r.intelligent_stop_price else None,
            tp_price=float(r.intelligent_tp_price) if r.intelligent_tp_price else None,
            signals=r.intelligent_signals,
        ))
    return IntelligentPositionsPage(items=out, total=total or 0)


class IntelligentHistoryPage(BaseModel):
    items: list[IntelligentTrade]
    total: int  # ★全部历史单数(前端算总页数)


@router.get("/history", summary="智能交易历史平仓(每单明细 · ★分页 50/页 · 照搬托管 PR#82)")
async def list_intelligent_history(
    _admin: AdminDep, db: DbDep,
    offset: int = 0, limit: int = 50,
) -> IntelligentHistoryPage:
    acc = await _intelligent_account_row(db)
    if acc is None:
        return IntelligentHistoryPage(items=[], total=0)
    base_where = (
        VirtualPerpPosition.account_id == acc.id,
        VirtualPerpPosition.intelligent.is_(True),
        VirtualPerpPosition.closed_at.is_not(None),
    )
    total = await db.scalar(
        select(func.count()).select_from(VirtualPerpPosition).where(*base_where),
    )
    rows = list(await db.scalars(
        select(VirtualPerpPosition)
        .where(*base_where)
        .order_by(VirtualPerpPosition.closed_at.desc())
        .offset(max(offset, 0))
        .limit(max(min(limit, 200), 1)),  # ★限 1~200 防滥用
    ))
    out: list[IntelligentTrade] = []
    for r in rows:
        qty = r.quantity or Decimal("1")
        # exit_price 反推:做多做空对称(long entry+pnl/qty · short entry−pnl/qty)
        delta = r.realized_pnl / qty if qty > 0 else Decimal("0")
        exit_price = r.entry_price + delta if r.side == PerpSide.LONG else r.entry_price - delta
        margin = r.initial_margin
        hold = int((r.closed_at - r.opened_at).total_seconds()) if r.closed_at else 0
        out.append(IntelligentTrade(
            symbol=r.symbol, side=r.side.value, leverage=r.leverage,
            entry_price=float(r.entry_price), exit_price=float(exit_price), quantity=float(qty),
            pnl_usdt=float(r.realized_pnl),
            pnl_pct=float(r.realized_pnl / margin) if margin > 0 else 0.0,
            close_reason=r.intelligent_close_reason,
            opened_at=r.opened_at.isoformat(),
            closed_at=r.closed_at.isoformat() if r.closed_at else None,
            hold_seconds=hold,
        ))
    return IntelligentHistoryPage(items=out, total=total or 0)


@router.get("/stats", summary="智能交易前向测试统计(胜率/盈亏比/回撤/按原因/做多做空)")
async def get_intelligent_stats(
    _admin: AdminDep, db: DbDep,
) -> dict[str, float | int | dict[str, int]]:
    acc = await _intelligent_account_row(db)
    if acc is None:
        return intelligent_stats.compute_intelligent_stats([])
    rows = list(await db.scalars(
        select(VirtualPerpPosition)
        .where(
            VirtualPerpPosition.account_id == acc.id,
            VirtualPerpPosition.intelligent.is_(True),
            VirtualPerpPosition.closed_at.is_not(None),
        )
        .order_by(VirtualPerpPosition.closed_at.asc()),  # 升序 · 算最大回撤权益曲线
    ))
    trades = [
        intelligent_stats.ClosedIntelligentTrade(
            realized_pnl=r.realized_pnl, close_reason=r.intelligent_close_reason, side=r.side.value,
        )
        for r in rows
    ]
    return intelligent_stats.compute_intelligent_stats(trades)
