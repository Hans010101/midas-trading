"""Bot 行情 / 自选 / 持仓查询(核心层 · 平台无关)· 0025 M1-G G3。

只读【已采数据】:K 线走 ClickHouseClient.select_kline,crypto 衍生指标走 clickhouse_crypto
历史快照,持仓 / 自选走 Postgres。**绝不打实时上游**(0025 R4 · 结构性规避 akshare 卡死)。

返回结构化 dataclass(无任何 Telegram 字符串)· 由 replies.build_* → 各通道 renderer 渲染。
飞书将来复用同一查询(ADR 0032)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy import select

from app.models.alert_rule import AlertRule
from app.models.perp import VirtualPerpPosition
from app.models.virtual import VirtualAccount, VirtualPosition
from app.models.watchlist import WatchlistItem
from app.services import clickhouse_crypto
from app.services.alerts.registry import get_indicator

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.market import Kline
    from app.services.clickhouse_client import ClickHouseClient

# 市场 → 计价货币(对齐 models.virtual.MARKET_CURRENCY · 这里要 str 给渲染层)
_MARKET_CURRENCY: dict[str, str] = {"cn": "CNY", "us": "USD", "crypto": "USDT", "hk": "HKD"}
_WATCHLIST_QUERY_LIMIT = 30  # 自选查询单次最多显示(防超长消息 / 过多 CH 往返)


@dataclass(frozen=True)
class SymbolQuote:
    """单标的核心信息卡(平台无关)。crypto 衍生字段非 crypto / 无数据时为 None。"""

    market: str
    symbol: str
    currency: str
    price: float | None
    change_pct: float | None
    volume: float | None
    funding_rate: float | None = None
    open_interest_usd: float | None = None
    long_short_ratio: float | None = None
    basis_pct: float | None = None


@dataclass(frozen=True)
class WatchlistRow:
    market: str
    symbol: str
    price: float | None
    change_pct: float | None


@dataclass(frozen=True)
class PositionRow:
    """持仓行 · spot(现货/卖空)与 perp(永续)统一结构。"""

    market: str
    symbol: str
    kind: str  # "spot" | "perp"
    side: str  # "long" | "short"
    quantity: float
    avg_entry_price: float
    currency: str
    leverage: int | None = None  # 仅 perp


def _last_price_change(ks: list[Kline]) -> tuple[float | None, float | None, float | None]:
    """从 ASC K 线取(最新价, 日涨跌 %, 最新成交量)· 不足返 None。"""
    if not ks:
        return None, None, None
    price = float(ks[-1].close)
    volume = float(ks[-1].volume)
    change: float | None = None
    if len(ks) >= 2:  # noqa: PLR2004
        prev = float(ks[-2].close)
        if prev > 0:
            change = (price - prev) / prev * 100
    return price, change, volume


async def _kline_quote(
    ch: ClickHouseClient, market: str, symbol: str,
) -> tuple[float | None, float | None, float | None]:
    ks = await ch.select_kline(
        symbol=symbol, market=cast("Any", market), period=cast("Any", "1d"), limit=2,
    )
    return _last_price_change(ks)


async def _crypto_extras(
    ch: ClickHouseClient, symbol: str,
) -> dict[str, float | None]:
    """crypto perp 衍生指标(funding/OI/多空比/基差)· 每项独立 fail-soft → None。

    采集表用 Binance 风格无斜杠('BTCUSDT')· 自选传入是 'BTC/USDT' → 去斜杠对齐。
    """
    raw = ch._client  # noqa: SLF001 · 与 crypto.py 一致:复用同一 AsyncClient 读快照
    bsym = symbol.replace("/", "")
    out: dict[str, float | None] = {
        "funding_rate": None, "open_interest_usd": None,
        "long_short_ratio": None, "basis_pct": None,
    }
    try:
        rows = await clickhouse_crypto.select_funding_rates(raw, bsym, limit=1)
        if rows:
            out["funding_rate"] = float(rows[-1].rate)
    except Exception:  # noqa: BLE001, S110 · 衍生指标缺失不影响主卡
        pass
    try:
        oi = await clickhouse_crypto.select_open_interest(raw, bsym, limit=1)
        if oi:
            out["open_interest_usd"] = float(oi[-1].oi_usd)
    except Exception:  # noqa: BLE001, S110
        pass
    try:
        ls = await clickhouse_crypto.select_long_short(raw, bsym, limit=1)
        if ls:
            out["long_short_ratio"] = float(ls[-1].top_account_ratio)
    except Exception:  # noqa: BLE001, S110
        pass
    try:
        pi = await clickhouse_crypto.select_latest_premium_index(raw, bsym)
        if pi is not None and float(pi.index_price) > 0:
            out["basis_pct"] = (
                (float(pi.mark_price) - float(pi.index_price))
                / float(pi.index_price) * 100
            )
    except Exception:  # noqa: BLE001, S110
        pass
    return out


async def query_symbol(
    ch: ClickHouseClient, market: str, symbol: str,
) -> SymbolQuote | None:
    """单标的核心信息卡 · 无任何 K 线数据(标的不存在/未采)→ None。"""
    price, change, volume = await _kline_quote(ch, market, symbol)
    if price is None:
        return None
    extras: dict[str, float | None] = {}
    if market == "crypto":
        extras = await _crypto_extras(ch, symbol)
    return SymbolQuote(
        market=market,
        symbol=symbol,
        currency=_MARKET_CURRENCY.get(market, market),
        price=price,
        change_pct=change,
        volume=volume,
        funding_rate=extras.get("funding_rate"),
        open_interest_usd=extras.get("open_interest_usd"),
        long_short_ratio=extras.get("long_short_ratio"),
        basis_pct=extras.get("basis_pct"),
    )


async def detect_symbol_markets(
    ch: ClickHouseClient, raw: str,
) -> list[tuple[str, str]]:
    """裸【字母】代码 → 扫库命中的 (market, canonical_symbol) 列表(加密在前、美股在后)。

    问题修复:裸 `btc` 原会被猜成美股查不到、小写 `nvda` 不识别。改为扫库判定 + 统一 upper:
      · 加密 spot 表主流币是带斜杠 `XXX/USDT`(取证最全)→ 探 `<UPPER>/USDT`;
      · 美股 ClickHouse 大写存储 → 探 `<UPPER>`。
    命中即出、两边都中就都出(不做优先级二选一)· 纯数字代码(cn/hk)不走本函数(调用方先判)。
    """
    s = raw.strip().upper()
    hits: list[tuple[str, str]] = []
    if await ch.symbol_exists("crypto", f"{s}/USDT"):
        hits.append(("crypto", f"{s}/USDT"))
    if await ch.symbol_exists("us", s):
        hits.append(("us", s))
    return hits


async def query_watchlist(
    db: AsyncSession, ch: ClickHouseClient, user_id: UUID,
) -> list[WatchlistRow]:
    """用户自选 + 每项最新价 / 日涨跌(只读已采 K 线)。"""
    items = list(
        await db.scalars(
            select(WatchlistItem)
            .where(WatchlistItem.user_id == user_id)
            .order_by(WatchlistItem.sort_order)
            .limit(_WATCHLIST_QUERY_LIMIT),
        ),
    )
    rows: list[WatchlistRow] = []
    for it in items:
        try:
            price, change, _ = await _kline_quote(ch, it.market, it.symbol)
        except Exception:  # noqa: BLE001 · 单标的取价失败不影响整张表
            price, change = None, None
        rows.append(
            WatchlistRow(
                market=it.market, symbol=it.symbol, price=price, change_pct=change,
            ),
        )
    return rows


async def query_positions(db: AsyncSession, user_id: UUID) -> list[PositionRow]:
    """用户全部活仓(现货 + 永续)· 只读 · 不算浮盈(读时现算属下单期/G4)。"""
    accounts = list(
        await db.scalars(
            select(VirtualAccount).where(VirtualAccount.user_id == user_id),
        ),
    )
    if not accounts:
        return []
    acct_market: dict[int, str] = {a.id: a.market for a in accounts}
    acct_ids = list(acct_market.keys())

    rows: list[PositionRow] = []

    spot = list(
        await db.scalars(
            select(VirtualPosition).where(
                VirtualPosition.account_id.in_(acct_ids),
                VirtualPosition.closed_at.is_(None),
            ),
        ),
    )
    for p in spot:
        market = acct_market.get(p.account_id, p.market)
        rows.append(
            PositionRow(
                market=market,
                symbol=p.symbol,
                kind="spot",
                side=str(p.position_side.value),
                quantity=float(p.quantity),
                avg_entry_price=float(p.avg_entry_price),
                currency=_MARKET_CURRENCY.get(market, market),
            ),
        )

    perp = list(
        await db.scalars(
            select(VirtualPerpPosition).where(
                VirtualPerpPosition.account_id.in_(acct_ids),
                VirtualPerpPosition.closed_at.is_(None),
            ),
        ),
    )
    for pp in perp:
        rows.append(
            PositionRow(
                market="crypto",
                symbol=pp.symbol,
                kind="perp",
                side=str(pp.side.value),
                quantity=float(pp.quantity),
                avg_entry_price=float(pp.entry_price),
                currency="USDT",
                leverage=pp.leverage,
            ),
        )
    return rows


@dataclass(frozen=True)
class AlertRuleRow:
    """告警规则行(bot 查看/启停用)。"""

    rule_id: int
    market: str
    symbol: str | None
    indicator_label: str
    operator: str
    threshold: float
    unit: str | None
    enabled: bool


async def query_alert_rules(db: AsyncSession, user_id: UUID) -> list[AlertRuleRow]:
    """用户全部告警规则(只读 · 给 bot 查看/启停)· 永远按 user_id 限定。"""
    rules = list(
        await db.scalars(
            select(AlertRule)
            .where(AlertRule.user_id == user_id)
            .order_by(AlertRule.created_at),
        ),
    )
    out: list[AlertRuleRow] = []
    for r in rules:
        ind = get_indicator(r.indicator)
        out.append(
            AlertRuleRow(
                rule_id=r.id,
                market=r.market,
                symbol=r.symbol,
                indicator_label=ind.label if ind else r.indicator,
                operator=r.operator,
                threshold=float(r.threshold),
                unit=ind.unit if ind else None,
                enabled=r.enabled,
            ),
        )
    return out

