"""选股筛选器服务 · 股票第一批 功能1 · 1a MVP(只读 · 分析非建议 · 复用指标引擎)。

性能(总纲方案 A + C):
- 方案A 轻量预筛:先打 spot 快照(全市场最新价 / 涨跌幅 / 成交额 · 秒级)按价格 / 涨跌幅过滤;
- 方案C 按需批量算指标:仅对预筛候选(成交额 top N 有界)走 select_klines_batch 一次取 K线,
  复用 indicators 引擎现算 RSI / 均线 → 过滤。★不上指标快照表(方案B 是中期 · 不在 1a)。

🔴 红线:结果是"符合条件的标的"客观列表 + 免责,非荐股;全程只读不下单;复用市场无感指标引擎;
不碰写死 crypto 的 perp / 智能 / 托管。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

from app.schemas.screener import ScreenerFilters, ScreenerHit, ScreenerResponse
from app.services import (
    clickhouse_cn_market,
    clickhouse_hk_market,
    clickhouse_us_market,
)
from app.services.ai import indicators
from app.services.clickhouse_client import normalize_kline_symbol

if TYPE_CHECKING:
    from clickhouse_connect.driver.asyncclient import AsyncClient

    from app.schemas.market import Market
    from app.services.clickhouse_client import ClickHouseClient

# 候选池上限(spot 快照取最新 max ts 全市场 · 覆盖 cn ~5500)。
_POOL_LIMIT = 6000
# 技术指标(RSI / 均线)候选上限:按成交额降序取前 N · 有界(防纯技术筛扫全市场算 K线)。
_MAX_TECH_SCAN = 800
# 单标取 K线根数:MA60 需 60 根 · 给 120 余量。
_KLINE_LIMIT = 120
_MIN_KLINE = 60  # 算 MA60 的最少根数

_DISCLAIMER = "以上为符合所选条件的标的客观列表,仅供参考,不构成投资建议。"


class _SpotLike(Protocol):
    """三市场 SpotRow 的共有结构(duck-typing · cn/us/hk 都有这些字段)。"""

    symbol: str
    name: str
    last_price: float
    change_pct: float
    amount: float


async def _fetch_spot_pool(raw: AsyncClient, market: str) -> list[_SpotLike]:
    """取全市场最新 spot 快照(按成交额降序 · 预筛 + 候选限界都靠这个顺序)。"""
    if market == "cn":
        rows: list[object] = list(
            await clickhouse_cn_market.select_latest_spot(
                raw, sort_by="amount", order="DESC", limit=_POOL_LIMIT,
            ),
        )
    elif market == "us":
        rows = list(
            await clickhouse_us_market.select_latest_us_spot(
                raw, sort_by="amount", order="DESC", limit=_POOL_LIMIT,
            ),
        )
    else:  # hk
        rows = list(
            await clickhouse_hk_market.select_latest_spot(
                raw, sort_by="amount", order="DESC", limit=_POOL_LIMIT,
            ),
        )
    return cast("list[_SpotLike]", rows)


def _spot_pass(row: _SpotLike, f: ScreenerFilters) -> bool:
    if f.price_min is not None and row.last_price < f.price_min:
        return False
    if f.price_max is not None and row.last_price > f.price_max:
        return False
    if f.change_pct_min is not None and row.change_pct < f.change_pct_min:
        return False
    return not (f.change_pct_max is not None and row.change_pct > f.change_pct_max)


def _tech_pass(rsi: float | None, ma: dict[int, float], f: ScreenerFilters) -> bool:
    if f.rsi_min is not None and (rsi is None or rsi < f.rsi_min):
        return False
    if f.rsi_max is not None and (rsi is None or rsi > f.rsi_max):
        return False
    if f.ma_bull_aligned:
        m5, m20, m60 = ma.get(5), ma.get(20), ma.get(60)
        if m5 is None or m20 is None or m60 is None:
            return False
        if not (m5 > m20 > m60):
            return False
    return True


async def run_screener(
    ch: ClickHouseClient,
    raw: AsyncClient,
    *,
    market: str,
    filters: ScreenerFilters,
    page: int = 1,
    page_size: int = 30,
) -> ScreenerResponse:
    """跑一次筛选 · 返回分页命中 + 诚实标注 + 红线免责。"""
    pool = await _fetch_spot_pool(raw, market)
    # 方案A 预筛:spot 维度(价格 / 涨跌幅)
    pre = [r for r in pool if _spot_pass(r, filters)]

    capped = False
    if filters.needs_kline():
        # 候选限界(已按 amount DESC)→ 方案C 批量取 K线现算指标(RSI / 均线)
        cand = pre[:_MAX_TECH_SCAN]
        capped = len(pre) > _MAX_TECH_SCAN
        kmap = await ch.select_klines_batch(
            symbols=[r.symbol for r in cand],
            market=cast("Market", market),
            period="1d",
            limit=_KLINE_LIMIT,
        )
        hits: list[ScreenerHit] = []
        for r in cand:
            key = normalize_kline_symbol(r.symbol, market, "spot")
            ks = kmap.get(key, [])
            if len(ks) < _MIN_KLINE:
                continue
            rsi = indicators.compute_rsi(ks).get(14)
            ma = indicators.compute_ma(ks)
            if not _tech_pass(rsi, ma, filters):
                continue
            hits.append(
                ScreenerHit(
                    symbol=r.symbol, name=r.name,
                    last_price=r.last_price, change_pct=r.change_pct,
                    rsi_14=rsi, ma_5=ma.get(5), ma_20=ma.get(20), ma_60=ma.get(60),
                ),
            )
        scanned = len(cand)
    else:
        # 纯 spot 筛(无技术指标)· 秒级 · 不算 K线
        hits = [
            ScreenerHit(
                symbol=r.symbol, name=r.name,
                last_price=r.last_price, change_pct=r.change_pct,
            )
            for r in pre
        ]
        scanned = len(pre)

    total = len(hits)
    start = (page - 1) * page_size
    page_hits = hits[start : start + page_size]
    return ScreenerResponse(
        market=market, total=total, page=page, page_size=page_size,
        scanned=scanned, candidate_capped=capped, hits=page_hits,
        disclaimer=_DISCLAIMER,
    )
