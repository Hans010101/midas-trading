"""11 因子结构快照聚合 · 结构分析助手第1刀(数据层)· 三期第一批扩到 11。

★ 只 import clickhouse_crypto.py 现成读层(select_*),零新 SQL、零复制查询逻辑;
  全程只读 CH(绝不调 insert_* / merge_*——merge_fear_greed 是采集端写函数,红线不碰)。

窗口口径(window 字段 · TTL 60d 约束的产品化,下游/LLM 不得冒充长期基线):
  - LSR 15min 采集 → 24h = limit 96;OI 5min → 24h = limit 288;funding 8h 结算 → 7d = limit 21。
  - premium(基差/预测费率)表仅存 7 天 → window="latest";FGI/dominance → window="latest"。
  - 三期第一批(零新采集):funding 读窗扩到 60d(limit 180)给 z-score,7d 统计用尾部切片
    语义不变;预测费率取自已读 premium 对象;OI/成交额比组合 OI 表 + ticker 表;
    全市场人数比取自 LSR 响应已带的 global 列(刀C)。

🔴 红线:客观结构数据,非价格预测;不下单/不撮合;单因子查无数据返 None 不阻塞整体。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable
from datetime import UTC, datetime
from statistics import fmean, pstdev
from typing import TYPE_CHECKING, TypeVar

from app.core.redis_client import get_redis
from app.schemas.structure import StructureFactor, StructureSnapshot
from app.services.ai.cache import compute_trading_day
from app.services.clickhouse_crypto import (
    select_fear_greed_series,
    select_funding_rates,
    select_latest_overview,
    select_latest_premium_index,
    select_long_short,
    select_open_interest,
    select_tickers_by_symbols,
)

if TYPE_CHECKING:
    from clickhouse_connect.driver.asyncclient import AsyncClient

logger = logging.getLogger(__name__)

# 窗口 → limit(按各表采集节奏换算,见模块头)
_LSR_24H_LIMIT = 96
_OI_24H_LIMIT = 288
_FUNDING_7D_LIMIT = 21
# 三期批1:z-score 用 60d 全窗(8h×3/天×60)· funding 因子的 7d 统计用尾部切片,语义不变
_FUNDING_60D_LIMIT = 180

# 缓存:快照层按 symbol 共享(所有自然语言问题命中同一份)· crypto 6h 分桶 + TTL 1h(对齐决策卡)
_CACHE_TTL_S = 3600

T = TypeVar("T")


# 已知 quote 后缀(长优先匹配)· 因子表 universe 全是 {COIN}USDT(_all_usdt_perp_symbols 采集口径)。
# ★ structure 域内自有规则,独立于 vibe loader 的 to_ch_symbol(那是 vibe 域,不碰不复制)。
_KNOWN_QUOTES: tuple[str, ...] = ("USDT", "USDC", "BUSD", "FDUSD", "USD")


def normalize_symbol(symbol: str) -> str:
    """入参归一成 Binance 风格无斜杠 + 缺省补 USDT 后缀('eth' → 'ETHUSDT')。

    规则(symbol 模糊输入根治 · Hans 真机实证 "eth" 只剩 FGI 的根因 = 缺后缀查空):
      - strip/upper/去斜杠横杠(原有);
      - 已带任一已知 quote 后缀(长优先)→ 原样(BTCUSDC 保持 · 查空走诚实 null,零误伤);
      - 无后缀 → 补 USDT(因子 universe 全 {COIN}USDT)。
    """
    s = symbol.strip().upper().replace("/", "").replace("-", "")
    if not s:
        return s
    if any(s.endswith(q) and len(s) > len(q) for q in _KNOWN_QUOTES):
        return s
    return f"{s}USDT"


async def _safe(label: str, coro: Awaitable[T]) -> T | None:
    """单因子读失败 → None + warning(覆盖不均是常态,不让一个因子拖垮快照)。"""
    try:
        return await coro
    except Exception as e:  # noqa: BLE001 — 因子级兜底:任何读失败都降级为该因子缺失
        logger.warning("[structure] 因子 %s 读取失败:%s", label, e)
        return None


def _round(v: float, nd: int = 4) -> float:
    return round(float(v), nd)


def _to_ccxt_symbol(sym: str) -> str:
    """'BTCUSDT' → 'BTC/USDT'(ticker 表存 ccxt 斜杠形态 · 长 quote 优先切尾)。"""
    for q in _KNOWN_QUOTES:
        if sym.endswith(q) and len(sym) > len(q):
            return f"{sym[: -len(q)]}/{q}"
    return sym


async def build_structure_snapshot(client: AsyncClient, symbol: str) -> StructureSnapshot:
    """聚合 11 因子 → StructureSnapshot(纯读 · 不进缓存,缓存在 get_structure_snapshot)。"""
    sym = normalize_symbol(symbol)
    ccxt_sym = _to_ccxt_symbol(sym)

    lsr_rows = await _safe("long_short", select_long_short(client, sym, limit=_LSR_24H_LIMIT))
    oi_rows = await _safe("open_interest", select_open_interest(client, sym, limit=_OI_24H_LIMIT))
    # 三期批1:60d 窗给 z-score(7d 统计在下方用尾部切片 · 语义不变)
    funding_rows = await _safe(
        "funding_rate", select_funding_rates(client, sym, limit=_FUNDING_60D_LIMIT),
    )
    premium = await _safe("premium_index", select_latest_premium_index(client, sym))
    overview = await _safe("overview", select_latest_overview(client))
    # FGI 单独走按天序列(WHERE value>0 · 最新 overview 行的 FGI 常为 0,采集端合并节奏所致)
    fgi_rows = await _safe("fear_greed", select_fear_greed_series(client, limit=1))
    # 三期批1 · OI/成交额比的分母(ticker 表 ccxt 斜杠形态 · 单 symbol 精确取)
    tickers = await _safe(
        "ticker_24h",
        select_tickers_by_symbols(client, instrument="perp", symbols=[ccxt_sym]),
    )

    # ── ①② 大户账户/持仓多空比 + ③ taker + ⑧ 全市场人数比(同一张 LSR 表)─────
    account = position = taker = global_ls = None
    if lsr_rows:
        # ⑧ 全市场人数比(刀C global 列 · 0 = 未采哨兵,过滤后才有格;零新读取)
        g_rows = [r for r in lsr_rows if r.global_account_ratio > 0]
        if g_rows:
            global_ls = StructureFactor(
                value={
                    "latest": _round(g_rows[-1].global_account_ratio),
                    "avg_24h": _round(fmean(r.global_account_ratio for r in g_rows)),
                },
                window="24h",
                asof=g_rows[-1].ts,
            )
    if lsr_rows:
        last = lsr_rows[-1]
        account = StructureFactor(
            value={
                "latest": _round(last.top_account_ratio),
                "avg_24h": _round(fmean(r.top_account_ratio for r in lsr_rows)),
            },
            window="24h",
            asof=last.ts,
        )
        position = StructureFactor(
            value={
                "latest": _round(last.top_position_ratio),
                "avg_24h": _round(fmean(r.top_position_ratio for r in lsr_rows)),
            },
            window="24h",
            asof=last.ts,
        )
        taker = StructureFactor(
            value={
                "latest": _round(last.taker_ratio),
                "avg_24h": _round(fmean(r.taker_ratio for r in lsr_rows)),
            },
            window="24h",
            asof=last.ts,
        )

    # ── ④ OI(最新 + 24h 变化率)────────────────────────────────────────────
    oi = None
    if oi_rows:
        last_oi, first_oi = oi_rows[-1], oi_rows[0]
        change_pct = (
            _round((last_oi.oi_usd - first_oi.oi_usd) / first_oi.oi_usd * 100, 2)
            if first_oi.oi_usd > 0
            else 0.0
        )
        oi = StructureFactor(
            value={
                "oi_usd": _round(last_oi.oi_usd, 0),
                "oi_coin": _round(last_oi.oi_coin, 2),
                "change_pct_24h": change_pct,
            },
            window="24h",
            asof=last_oi.ts,
        )

    # ── ⑤ 资金费率(最新 + 近7天均值/极值 · 8h 结算点)──────────────────────────
    #     60d 全窗已读 · 7d 统计用尾部切片(语义与三期批1 之前完全一致)
    funding = None
    funding_zscore = None
    if funding_rows:
        rates_7d = [r.rate for r in funding_rows[-_FUNDING_7D_LIMIT:]]
        funding = StructureFactor(
            value={
                "latest": _round(funding_rows[-1].rate, 6),
                "avg_7d": _round(fmean(rates_7d), 6),
                "max_7d": _round(max(rates_7d), 6),
                "min_7d": _round(min(rates_7d), 6),
            },
            window="7d",
            asof=funding_rows[-1].ts,
        )
        # ── ⑨ 费率 z-score(60d 全窗均值/总体标准差 · σ=0 → 该格 None)──────────
        rates_60d = [r.rate for r in funding_rows]
        sigma = pstdev(rates_60d) if len(rates_60d) > 1 else 0.0
        if sigma > 0:
            mu = fmean(rates_60d)
            funding_zscore = StructureFactor(
                value={
                    "z": _round((rates_60d[-1] - mu) / sigma, 2),
                    "mean_60d": _round(mu, 6),
                    "std_60d": _round(sigma, 6),
                },
                window="60d",
                asof=funding_rows[-1].ts,
            )

    # ── ⑩ 预测资金费率(premium 同一对象的 last_funding_rate · 1min 实时滚动预估)──
    funding_predicted = None
    if premium is not None:
        funding_predicted = StructureFactor(
            value={"latest": _round(premium.last_funding_rate, 6)},
            window="latest",
            asof=premium.ts,
        )

    # ── ⑥ 基差 mark-index(premium 表仅存 7 天 → 只给最新点)─────────────────────
    basis = None
    if premium is not None:
        basis_abs = premium.mark_price - premium.index_price
        basis = StructureFactor(
            value={
                "mark_price": _round(premium.mark_price, 2),
                "index_price": _round(premium.index_price, 2),
                "basis": _round(basis_abs, 2),
                "basis_pct": (
                    _round(basis_abs / premium.index_price * 100, 4)
                    if premium.index_price > 0
                    else 0.0
                ),
            },
            window="latest",
            asof=premium.ts,
        )

    # ── ⑪ OI/成交额比(OI 表 × ticker 表组合 · 仓位沉淀 vs 24h 换手)──────────────
    oi_volume_ratio = None
    if oi_rows and tickers:
        tk = tickers.get(ccxt_sym)
        if tk is not None and tk.quote_volume_24h > 0:
            oi_volume_ratio = StructureFactor(
                value={
                    "ratio": _round(oi_rows[-1].oi_usd / tk.quote_volume_24h, 3),
                    "oi_usd": _round(oi_rows[-1].oi_usd, 0),
                    "quote_volume_24h": _round(tk.quote_volume_24h, 0),
                },
                window="24h",
                asof=oi_rows[-1].ts,
            )

    # ── ⑦ 情绪(FGI 按天序列取最新非零 + dominance 取 overview)· 全市场非单 symbol ──
    sentiment = None
    if fgi_rows or overview is not None:
        value: dict[str, float] = {}
        text: str | None = None
        asof = datetime.now(UTC)
        if fgi_rows:
            value["fear_greed"] = float(fgi_rows[-1].value)
            text = fgi_rows[-1].classification or None
            asof = fgi_rows[-1].ts
        if overview is not None:
            value["btc_dominance"] = _round(overview.btc_dominance, 2)
            asof = max(asof, overview.ts) if fgi_rows else overview.ts
        sentiment = StructureFactor(value=value, window="latest", asof=asof, text=text)

    return StructureSnapshot(
        symbol=sym,
        generated_at=datetime.now(UTC),
        account_long_short=account,
        position_long_short=position,
        taker_flow=taker,
        open_interest=oi,
        funding_rate=funding,
        basis=basis,
        sentiment=sentiment,
        funding_predicted=funding_predicted,
        funding_zscore=funding_zscore,
        oi_volume_ratio=oi_volume_ratio,
        global_long_short=global_ls,
    )


# ── 缓存 wrapper(照 ai/cache.py 范式:失败不阻塞 · crypto 6h 分桶 · TTL 1h)──────


def _cache_key(symbol: str) -> str:
    return f"ai:structure:snapshot:{symbol}:{compute_trading_day('crypto')}"


async def get_structure_snapshot(client: AsyncClient, symbol: str) -> StructureSnapshot:
    """缓存优先取快照:命中直接返;未命中 build + 写缓存。Redis 异常一律降级直读。"""
    sym = normalize_symbol(symbol)
    key = _cache_key(sym)
    try:
        redis = await get_redis()
        raw = await redis.get(key)
        if raw is not None:
            return StructureSnapshot.model_validate(json.loads(raw))
    except Exception as e:  # noqa: BLE001 — 缓存读失败不阻塞主链路
        logger.warning("[structure.cache] get failed key=%s err=%s", key, e)

    snapshot = await build_structure_snapshot(client, sym)

    try:
        redis = await get_redis()
        await redis.setex(
            key, _CACHE_TTL_S, json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False),
        )
    except Exception as e:  # noqa: BLE001 — 缓存写失败不阻塞主链路
        logger.warning("[structure.cache] set failed key=%s err=%s", key, e)

    return snapshot
