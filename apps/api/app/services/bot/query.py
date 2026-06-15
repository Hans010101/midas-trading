"""Bot 行情 / 自选 / 持仓查询(核心层 · 平台无关)· 0025 M1-G G3。

只读【已采数据】:K 线走 ClickHouseClient.select_kline,crypto 衍生指标走 clickhouse_crypto
历史快照,持仓 / 自选走 Postgres。**绝不打实时上游**(0025 R4 · 结构性规避 akshare 卡死)。

返回结构化 dataclass(无任何 Telegram 字符串)· 由 replies.build_* → 各通道 renderer 渲染。
飞书将来复用同一查询(ADR 0032)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy import select

from app.models.alert_rule import AlertRule
from app.models.perp import VirtualPerpPosition
from app.models.virtual import VirtualAccount, VirtualPosition
from app.models.watchlist import WatchlistItem
from app.services import (
    clickhouse_cn_market,
    clickhouse_crypto,
    clickhouse_hk_market,
)
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
class SpotLite:
    """无 kline 时的轻量信息(只读 spot 快照 · 仅 cn/hk)· 给「无K线轻量卡」用。"""

    market: str
    symbol: str
    name: str
    last_price: float
    change_pct: float
    amount: float
    ts: datetime


@dataclass(frozen=True)
class NameHit:
    """中文名搜索命中(候选列表用)· market+symbol 定位 · name 展示。"""

    market: str
    symbol: str
    name: str


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


_PERP_QUOTES = ("USDT", "USDC", "BUSD", "FDUSD")


def _to_ccxt(symbol: str) -> str:
    """归一到 ccxt 形态 BTC/USDT(crypto_ticker_24h 表的 symbol 键)· 带斜杠原样 upper ·
    无斜杠按 quote 后缀补斜杠(BTCUSDT→BTC/USDT)。"""
    if "/" in symbol:
        return symbol.upper()
    s = symbol.upper()
    for q in _PERP_QUOTES:
        if s.endswith(q) and len(s) > len(q):
            return f"{s[: -len(q)]}/{q}"
    return s


async def _crypto_ticker_quote(
    ch: ClickHouseClient, symbol: str,
) -> tuple[float | None, float | None, float | None]:
    """crypto 实时 价/24h涨跌/24h量 ← perp ticker(与下单页 _perp_mark 同源)。

    修「显示价≠下单价」:原行情卡价取 1d kline(日线收盘 · 可能几天前),与下单页实时 perp ticker
    差几个点。改用同源 ticker → 卡价≈下单价。取不到(理论上主流币不会)→ (None,None,None),
    调用方兜底回 1d kline(fail-soft · 不报错)。
    """
    raw = ch._client  # noqa: SLF001 · 同 _crypto_extras:复用底层 client 读 ticker 快照
    ccxt = _to_ccxt(symbol)
    try:
        tickers = await clickhouse_crypto.select_tickers_by_symbols(
            raw, instrument="perp", symbols=[ccxt],
        )
    except Exception:  # noqa: BLE001 · 取价失败 fail-soft → 调用方兜底 1d kline
        return None, None, None
    t = tickers.get(ccxt)
    if t is None or t.last_price <= 0:
        return None, None, None
    return float(t.last_price), float(t.change_pct_24h), float(t.volume_24h) or None


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
    """单标的核心信息卡 · 无任何 K 线数据(标的不存在/未采)→ None。

    crypto 价/涨跌走【实时 perp ticker】(与下单页同源 · 修"显示价≠下单价");ticker 缺则兜底 1d ·
    cn/us/hk 维持 1d kline(各自市场日线 · 行为不变 · 零回归)。
    """
    if market == "crypto":
        price, change, volume = await _crypto_ticker_quote(ch, symbol)
        if price is None:  # ticker 缺 → 兜底 1d kline
            price, change, volume = await _kline_quote(ch, market, symbol)
    else:
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


_SPOT_LITE_MARKETS = {"cn", "hk"}


async def get_spot_lite(
    ch: ClickHouseClient, market: str, symbol: str,
) -> SpotLite | None:
    """无 kline 时的轻量数据源:从 {market}_spot_snapshot 取该 symbol 最新一行。

    仅 cn/hk(us/crypto 有自己的 kline 路径,不走轻量卡)· 无行 → None。
    market 经白名单后内插表名(防注入)· ts DESC LIMIT 1 取最新快照行。
    """
    if market not in _SPOT_LITE_MARKETS:
        return None
    table = f"{market}_spot_snapshot"  # market 已白名单 cn/hk · 表名内插无注入风险
    result = await ch._client.query(  # noqa: SLF001 · 与 _crypto_extras 一致:复用底层 client 只读查
        "SELECT symbol, name, last_price, change_pct, amount, ts "  # noqa: S608
        f"FROM {table} WHERE symbol = %(s)s ORDER BY ts DESC LIMIT 1",
        parameters={"s": symbol},
    )
    rows = result.result_rows
    if not rows:
        return None
    r = rows[0]
    ts = r[5]
    return SpotLite(
        market=market, symbol=str(r[0]), name=str(r[1]),
        last_price=float(r[2]), change_pct=float(r[3]), amount=float(r[4]),
        ts=ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts,
    )


async def search_by_name(
    ch: ClickHouseClient, raw: str, limit: int = 8,
) -> list[NameHit]:
    """中文名搜索 A股 + 港股(只读 spot 快照 · symbol/name 子串)· 跨市场按成交额降序 · 截断 limit。

    不含 us(产品决策:us 用代码搜,英文名搜索另议)· 返回 (market, symbol, name) 列表(可空)。
    """
    q = raw.strip()
    if not q:
        return []
    raw_client = ch._client  # noqa: SLF001 · 同 _crypto_extras:market 服务函数收底层 client
    cn_rows = await clickhouse_cn_market.select_spot_search(
        raw_client, query=q, limit=limit,
    )
    hk_rows = await clickhouse_hk_market.select_hk_spot_search(
        raw_client, query=q, limit=limit,
    )
    merged = [("cn", row) for row in cn_rows] + [("hk", row) for row in hk_rows]
    merged.sort(key=lambda mr: mr[1].amount, reverse=True)  # 活跃(成交额)优先
    return [
        NameHit(market=mkt, symbol=row.symbol, name=row.name)
        for mkt, row in merged[:limit]
    ]


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

