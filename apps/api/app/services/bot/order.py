"""bot 虚拟下单 facade(核心层 · 平台无关)· 0025 M1-G G4。

═══════════════════════════════════════════════════════════════════════════
🔴 红线(逐条对应 0025 §7 + DP5):
1. 全程【虚拟资金】· 只调点金现有虚拟撮合引擎(现货 engine / perp_engine),
   绝不接任何真实交易 / 下单通道。本文件【不实现任何撮合逻辑】,只是把已上线引擎
   封一个 bot 入口 —— 引擎核心一行不改。
2. user_id 由【调用方(router)从已验证 webhook 的 chat.id 解析】后传入,本文件
   绝不从用户文本 / 会话里猜身份。下单永远只作用于 chat 绑定的那个账号。
3. 参数(杠杆 / 名义金额 / 逐仓)本期走【安全默认常量】(下方 DEFAULT_*);
   G5 接网页「后台预设」后改为读用户预设(§9:前端设置页属 G5)。本期仅逐仓。
4. 危险操作(下单)的「二次确认」由 router 的会话流程保证(本文件只做预览 + 执行)。
═══════════════════════════════════════════════════════════════════════════

下单类型:
- crypto → 永续合约(复用 M2-C perp_engine · 逐仓)· 开多 / 开空 / 平仓(平全仓)
- cn 现货 → 买入(开多)/ 卖出(平多全仓)
- us 现货 → 买入 / 卖出 / 卖空(开空)/ 平空(平空全仓)
开仓量 = 默认名义 / 现价;平仓 = 平掉当前活仓全部。引擎做保证金/余额/方向校验并返回
拒单(不抛)· execute 后显式 commit(get_db 不自动 commit)。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy import select

from app.models.bot_order_preset import BotOrderPreset
from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.models.virtual import (
    OrderSide,
    OrderStatus,
    PositionSide,
    VirtualAccount,
    VirtualPosition,
)
from app.services.clickhouse_crypto import (
    select_premium_index_marks,
    select_tickers_by_symbols,
)
from app.services.notifications.perp_events import (
    build_perp_filled_event,
    build_trade_filled_event,
)
from app.services.notifications.templates import render_telegram
from app.services.virtual_trading.engine import PlaceOrderRequest, place_market_order
from app.services.virtual_trading.perp_dispatcher import (
    route_close_perp,
    route_open_perp,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.clickhouse_client import ClickHouseClient

# ── 安全默认参数(G4 常量 · G5 起作为「无预设行」的回退值,与 DB server_default 一致)──
DEFAULT_PERP_LEVERAGE = 3
DEFAULT_PERP_NOTIONAL_USDT = Decimal("100")  # 每单名义额(USDT)· margin = 名义/杠杆
DEFAULT_SPOT_NOTIONAL: dict[str, Decimal] = {
    "cn": Decimal("10000"),  # 每单名义额(CNY)
    "us": Decimal("1000"),   # 每单名义额(USD)
}


@dataclass(frozen=True)
class PresetValues:
    """bot 下单后台预设的取值(G5)· 单一接入点 load_preset 产出。"""

    perp_leverage: int
    perp_notional_usdt: Decimal
    perp_margin_mode: str
    spot_notional_cny: Decimal
    spot_notional_usd: Decimal

    def spot_notional(self, market: str) -> Decimal:
        return self.spot_notional_cny if market == "cn" else self.spot_notional_usd


# 无预设行时的回退默认(= G4 行为 · 与 bot_order_preset 的 server_default 完全一致)
DEFAULT_PRESET = PresetValues(
    perp_leverage=DEFAULT_PERP_LEVERAGE,
    perp_notional_usdt=DEFAULT_PERP_NOTIONAL_USDT,
    perp_margin_mode="isolated",
    spot_notional_cny=DEFAULT_SPOT_NOTIONAL["cn"],
    spot_notional_usd=DEFAULT_SPOT_NOTIONAL["us"],
)


async def load_preset(db: AsyncSession, user_id: UUID) -> PresetValues:
    """G5 唯一接入点:读用户后台预设;无行 → DEFAULT_PRESET(= G4 行为 · 零回归)。"""
    row = await db.get(BotOrderPreset, user_id)
    if row is None:
        return DEFAULT_PRESET
    return PresetValues(
        perp_leverage=row.perp_leverage,
        perp_notional_usdt=Decimal(row.perp_notional_usdt),
        perp_margin_mode=row.perp_margin_mode,
        spot_notional_cny=Decimal(row.spot_notional_cny),
        spot_notional_usd=Decimal(row.spot_notional_usd),
    )

_MARKET_CCY: dict[str, str] = {"cn": "CNY", "us": "USD", "crypto": "USDT"}
_PERP_QUOTES = ("USDT", "USDC", "BUSD", "FDUSD")
_QTY_Q = Decimal("0.00000001")  # 8 位 · 开仓量量化(ROUND_DOWN 防超支)

# 每市场支持的下单方向(bot 按钮)
_DIRECTIONS: dict[str, tuple[str, ...]] = {
    "crypto": ("open_long", "open_short", "close"),
    "cn": ("buy", "sell"),
    "us": ("buy", "sell", "short", "cover"),
}
_DIR_LABEL: dict[str, str] = {
    "open_long": "开多", "open_short": "开空", "close": "平仓",
    "buy": "买入", "sell": "卖出", "short": "卖空", "cover": "平空",
}
_OPEN_DIRS = {"open_long", "open_short", "buy", "short"}


@dataclass(frozen=True)
class OrderIntent:
    """一次下单意图(只含「下什么」· 不含身份 · 身份由 router 从 chat 解析)。"""

    market: str
    symbol: str  # 用户输入;crypto 会归一到 Binance 风格
    direction: str


@dataclass(frozen=True)
class OrderPreview:
    market: str
    symbol: str
    direction: str
    direction_label: str
    is_open: bool
    est_price: float
    quantity: float
    notional: float
    currency: str
    leverage: int | None  # 仅 perp 开仓


@dataclass(frozen=True)
class OrderResult:
    filled: bool
    title: str
    detail: str
    # #296 去重:成交时填已渲染的富回执正文(复用 A 的 render_telegram · 含品牌标题+免责)·
    # router 成交走 render_order_receipt(body);拒单仍用 title/detail。
    body: str | None = None


def directions_for(market: str) -> tuple[str, ...]:
    return _DIRECTIONS.get(market, ())


def direction_valid(market: str, direction: str) -> bool:
    return direction in _DIRECTIONS.get(market, ())


def direction_label(direction: str) -> str:
    return _DIR_LABEL.get(direction, direction)


# ── 价格 helper(镜像 api/v1 的注入式 fetcher · 避免 services→api 反向依赖)──


def _to_binance(symbol: str) -> str:
    return symbol.replace("/", "").upper()


def _to_ccxt(binance_symbol: str) -> str:
    for q in _PERP_QUOTES:
        if binance_symbol.endswith(q) and len(binance_symbol) > len(q):
            return f"{binance_symbol[: -len(q)]}/{q}"
    return binance_symbol


def normalize_symbol(market: str, raw: str) -> str:
    """规范化 bot 下单输入的标的(#296 改动二 · 只两档,纯字符串 · 可单测)。

    - 大小写无关:btc / BTC / Btc → 同一标的。
    - crypto 简称 / 缺斜杠:upper + 去 / 和空格;不以 USDT/USDC/BUSD/FDUSD 结尾则补 USDT
      (加密以永续合约为主体 · 默认指向 perp 交易对)· 对外用 ccxt 风格 BTC/USDT
      (下游 _to_binance 幂等兼容)。
    - cn:strip(纯数字代码);us:upper + strip。
    不做中文别名、不做模糊候选 / 纠错补全(产品定范围)。空输入返回 ""。
    """
    s = raw.strip()
    if not s:
        return ""
    if market == "crypto":
        s = s.upper().replace("/", "").replace(" ", "")
        if not s.endswith(_PERP_QUOTES):
            s = f"{s}USDT"
        return _to_ccxt(s)
    if market == "us":
        return s.upper()
    return s  # cn:数字代码,strip 即可


async def _spot_price(ch: ClickHouseClient, market: str, symbol: str) -> Decimal | None:
    rows = await ch.select_kline(
        symbol=symbol, market=cast("Any", market), period=cast("Any", "1d"), limit=1,
    )
    return Decimal(str(rows[-1].close)) if rows else None


async def _perp_mark(ch: ClickHouseClient, binance_symbol: str) -> Decimal | None:
    """真标记价优先,perp ticker 兜底(与 perp 路由同源逻辑)。"""
    marks = await select_premium_index_marks(ch._client, [binance_symbol])  # noqa: SLF001
    m = marks.get(binance_symbol)
    if m is not None and m > 0:
        return m
    ccxt = _to_ccxt(binance_symbol)
    tickers = await select_tickers_by_symbols(
        ch._client, instrument="perp", symbols=[ccxt],  # noqa: SLF001
    )
    t = tickers.get(ccxt)
    return Decimal(str(t.last_price)) if t and t.last_price > 0 else None


# ── 活仓查询(平仓用 · 永远按 user_id 限定 · 跨用户隔离)─────────────────


async def _crypto_account(db: AsyncSession, user_id: UUID) -> VirtualAccount | None:
    acct: VirtualAccount | None = await db.scalar(
        select(VirtualAccount).where(
            VirtualAccount.user_id == user_id, VirtualAccount.market == "crypto",
        ),
    )
    return acct


async def _active_perp(
    db: AsyncSession, user_id: UUID, binance_symbol: str,
) -> VirtualPerpPosition | None:
    acct = await _crypto_account(db, user_id)
    if acct is None:
        return None
    pos: VirtualPerpPosition | None = await db.scalar(
        select(VirtualPerpPosition).where(
            VirtualPerpPosition.account_id == acct.id,
            VirtualPerpPosition.symbol == binance_symbol,
            VirtualPerpPosition.closed_at.is_(None),
        ),
    )
    return pos


async def _active_spot(
    db: AsyncSession, user_id: UUID, market: str, symbol: str, side: PositionSide,
) -> VirtualPosition | None:
    acct: VirtualAccount | None = await db.scalar(
        select(VirtualAccount).where(
            VirtualAccount.user_id == user_id, VirtualAccount.market == market,
        ),
    )
    if acct is None:
        return None
    pos: VirtualPosition | None = await db.scalar(
        select(VirtualPosition).where(
            VirtualPosition.account_id == acct.id,
            VirtualPosition.symbol == symbol,
            VirtualPosition.position_side == side,
            VirtualPosition.closed_at.is_(None),
        ),
    )
    return pos


async def quote_price(
    ch: ClickHouseClient, market: str, symbol: str,
) -> Decimal | None:
    """下单将用到的价(crypto=perp 标记价 · cn/us=现货 1d close)· 给方向页展示用。"""
    if market == "crypto":
        return await _perp_mark(ch, _to_binance(symbol))
    return await _spot_price(ch, market, symbol)


# ── 预览(确认页用 · 不落库)──────────────────────────────────────────────


async def build_preview(
    ch: ClickHouseClient, db: AsyncSession, user_id: UUID, intent: OrderIntent,
) -> OrderPreview | None:
    """生成下单预览;无报价 / 平仓时无活仓 → None(调用方提示)。"""
    if not direction_valid(intent.market, intent.direction):
        return None
    is_open = intent.direction in _OPEN_DIRS
    preset = await load_preset(db, user_id)  # G5:读用户预设(无行=默认)

    if intent.market == "crypto":
        bsym = _to_binance(intent.symbol)
        price = await _perp_mark(ch, bsym)
        if price is None:
            return None
        if is_open:
            notional = preset.perp_notional_usdt
            qty = (notional / price).quantize(_QTY_Q, rounding=ROUND_DOWN)
            lev: int | None = preset.perp_leverage
        else:
            pos = await _active_perp(db, user_id, bsym)
            if pos is None:
                return None
            qty = Decimal(pos.quantity)
            notional = (qty * price).quantize(Decimal("0.0001"))
            lev = None
        return OrderPreview(
            "crypto", bsym, intent.direction, _DIR_LABEL[intent.direction],
            is_open, float(price), float(qty), float(notional), "USDT", lev,
        )

    # 现货
    price = await _spot_price(ch, intent.market, intent.symbol)
    if price is None:
        return None
    if is_open:
        notional = preset.spot_notional(intent.market)
        qty = (notional / price).quantize(_QTY_Q, rounding=ROUND_DOWN)
    else:
        side = PositionSide.LONG if intent.direction == "sell" else PositionSide.SHORT
        pos2 = await _active_spot(db, user_id, intent.market, intent.symbol, side)
        if pos2 is None:
            return None
        qty = Decimal(pos2.quantity)
        notional = (qty * price).quantize(Decimal("0.0001"))
    return OrderPreview(
        intent.market, intent.symbol, intent.direction, _DIR_LABEL[intent.direction],
        is_open, float(price), float(qty), float(notional),
        _MARKET_CCY.get(intent.market, "USD"), None,
    )


# ── 执行(调引擎 + commit)────────────────────────────────────────────────


async def execute(
    db: AsyncSession, ch: ClickHouseClient, user_id: UUID, intent: OrderIntent,
) -> OrderResult:
    """执行虚拟下单 · user_id 必须由调用方从已验证 chat 解析后传入(红线 R1)。"""
    if not direction_valid(intent.market, intent.direction):
        return OrderResult(filled=False, title="下单失败", detail="不支持的操作")
    if intent.market == "crypto":
        return await _exec_perp(db, ch, user_id, intent)
    return await _exec_spot(db, ch, user_id, intent)


async def _exec_perp(
    db: AsyncSession, ch: ClickHouseClient, user_id: UUID, intent: OrderIntent,
) -> OrderResult:
    bsym = _to_binance(intent.symbol)

    async def fetcher(symbol: str) -> Decimal | None:
        return await _perp_mark(ch, symbol)

    if intent.direction == "close":
        # MC-4:平仓走 dispatcher,按【活仓 margin_mode】自动分流(逐仓/全仓)
        order = await route_close_perp(
            db, user_id=user_id, symbol=bsym,
            quantity=None, close_all=True, get_mark_price=fetcher,
        )
    else:
        preset = await load_preset(db, user_id)  # G5:杠杆 / 名义来自用户预设
        side = PerpSide.LONG if intent.direction == "open_long" else PerpSide.SHORT
        margin = (
            preset.perp_notional_usdt / Decimal(preset.perp_leverage)
        ).quantize(Decimal("0.0001"))
        # MC-4:开仓走 dispatcher,按 preset.perp_margin_mode 偏好分流(默认 isolated · 零回归)
        order = await route_open_perp(
            db, user_id=user_id, symbol=bsym, side=side,
            leverage=preset.perp_leverage, margin=margin, quantity=None,
            preferred_mode=MarginMode(preset.perp_margin_mode),
            get_mark_price=fetcher,
        )
    await db.commit()
    if order.status == OrderStatus.FILLED:
        # #296 去重:bot 不再发异步 A(网页 perp.py 的 emit 保留)· 改用富回执:
        # 复用 A 的事件 + 模板(build_perp_filled_event + render_telegram)· 文案单一事实源。
        account = await db.scalar(
            select(VirtualAccount).where(VirtualAccount.id == order.account_id),
        )
        position = None
        if order.position_id is not None:
            position = await db.scalar(
                select(VirtualPerpPosition).where(
                    VirtualPerpPosition.id == order.position_id,
                ),
            )
        body = (
            render_telegram(build_perp_filled_event(order, position, account))
            if account is not None
            else None
        )
        detail = (
            f"{order.symbol} · {_DIR_LABEL.get(intent.direction, intent.direction)}\n"
            f"数量 {_num(order.quantity)} @ {_num(order.price)}"
        )
        return OrderResult(filled=True, title="✅ 已成交", detail=detail, body=body)
    return OrderResult(
        filled=False, title="⚠️ 已拒绝",
        detail=order.reject_reason or "下单被拒(虚拟)",
    )


async def _exec_spot(
    db: AsyncSession, ch: ClickHouseClient, user_id: UUID, intent: OrderIntent,
) -> OrderResult:
    market, symbol, direction = intent.market, intent.symbol, intent.direction

    async def fetcher(s: str, m: str) -> Decimal | None:
        return await _spot_price(ch, m, s)

    side, pside, qty = await _resolve_spot_order(db, ch, user_id, market, symbol, direction)
    if qty is None or qty <= 0:
        return OrderResult(
            filled=False, title="下单失败",
            detail="无最新报价,或(平仓)当前无可平持仓",
        )

    order = await place_market_order(
        db,
        PlaceOrderRequest(
            user_id=user_id, symbol=symbol, market=market,
            side=side, quantity=qty, position_side=pside,
            notify=False,  # #296 去重:bot 走富回执 · 抑制引擎异步成交推送(网页默认 True 不变)
        ),
        fetcher,
    )
    await db.commit()
    if order.status == OrderStatus.FILLED:
        # #296 去重:复用 A 的事件 + 模板(build_trade_filled_event + render_telegram)
        account = await db.scalar(
            select(VirtualAccount).where(VirtualAccount.id == order.account_id),
        )
        body = (
            render_telegram(build_trade_filled_event(order, account))
            if account is not None
            else None
        )
        detail = (
            f"{order.symbol} · {_DIR_LABEL.get(direction, direction)}\n"
            f"数量 {_num(order.quantity)} @ {_num(order.price)}"
        )
        return OrderResult(filled=True, title="✅ 已成交", detail=detail, body=body)
    return OrderResult(
        filled=False, title="⚠️ 已拒绝",
        detail=order.reject_reason or "下单被拒(虚拟)",
    )


async def _resolve_spot_order(
    db: AsyncSession, ch: ClickHouseClient, user_id: UUID,
    market: str, symbol: str, direction: str,
) -> tuple[OrderSide, PositionSide, Decimal | None]:
    """把 bot 方向翻成 (side, position_side, quantity)。开仓按默认名义,平仓平全仓。"""
    if direction in {"buy", "short"}:  # 开仓
        side = OrderSide.BUY if direction == "buy" else OrderSide.SELL
        pside = PositionSide.LONG if direction == "buy" else PositionSide.SHORT
        price = await _spot_price(ch, market, symbol)
        if price is None or price <= 0:
            return side, pside, None
        preset = await load_preset(db, user_id)  # G5:每单名义来自用户预设
        notional = preset.spot_notional(market)
        return side, pside, (notional / price).quantize(_QTY_Q, rounding=ROUND_DOWN)
    # 平仓(sell=平多 / cover=平空)· 平全仓
    pside = PositionSide.LONG if direction == "sell" else PositionSide.SHORT
    side = OrderSide.SELL if direction == "sell" else OrderSide.BUY
    pos = await _active_spot(db, user_id, market, symbol, pside)
    if pos is None:
        return side, pside, None
    return side, pside, Decimal(pos.quantity)


def _num(v: Decimal | None) -> str:
    if v is None:
        return "—"
    f = float(v)
    if f == int(f):
        return f"{int(f):,}"
    return f"{f:,.8f}".rstrip("0").rstrip(".")
