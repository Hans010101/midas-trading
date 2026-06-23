"""Crypto Pro API · /api/v1/crypto(0017 ADR · M2-A)。

7 个新端点 · 给 M2-D 前端 landing page + 详情页合约 tab 消费:

  GET /overview                                · 加密 tab landing 顶层
  GET /tickers/24h?instrument=spot|perp&...    · 涨幅榜 / 跌幅榜 / 量榜
  GET /futures/{symbol}/funding-rate?limit=N   · 资金费率时间序列
  GET /futures/{symbol}/open-interest?limit=N  · OI 时间序列
  GET /futures/{symbol}/long-short-ratio?...   · 多空比时间序列
  GET /futures/{symbol}/info                   · 合约元信息(下次资金费率 / 标记价)
  GET /fear-greed?limit=30                     · FGI 时间序列(给图表用)

数据流:
  · 先查 ClickHouse(预热的快照数据)
  · 缺数据走 cache-aside 回源到 BinanceFuturesSource / CoinGeckoSource 等
  · 回源结果写回 CH(下次直接命中)

注:回源逻辑 M2-A 留 stub · M2-B 实装(目前 only ClickHouse read · 数据由
Celery 任务 M2-A-9 准备 · 见 apps/worker/tasks/crypto_metrics_ingest.py)。

红线:本路由全部 GET · 无任何写动作(crypto 写入由 Celery worker 完成)·
任何「交易」类动作走 /api/v1/virtual(已有的虚拟撮合)· 不在这里。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import ValidationError

from app.api.deps import ClickHouseDep
from app.core.redis_client import get_redis
from app.schemas.crypto import (
    BasisPoint,
    BasisSeriesResponse,
    BollScanItem,
    BollScanResponse,
    BollStructureResponse,
    CryptoOverviewResponse,
    FearGreedResponse,
    FundingRateResponse,
    FuturesMetricItem,
    FuturesMetricsBatchResponse,
    FuturesSymbolInfo,
    IngestStatusResponse,
    LongShortRatioResponse,
    MarketOverview,
    OpenInterestResponse,
    Tickers24hResponse,
)
from app.services.ai.boll_state import classify, to_snapshot_row
from app.services.clickhouse_client import ClickHouseClient
from app.services.clickhouse_crypto import (
    select_fear_greed_series,
    select_funding_rates,
    select_futures_metrics_batch,
    select_latest_funding_rates,
    select_latest_overview,
    select_latest_premium_index,
    select_latest_tickers,
    select_long_short,
    select_open_interest,
    select_perp_total_quote_volume,
    select_premium_index_series,
    select_tickers_by_symbols,
)
from app.services.ingest_monitor import build_ingest_status, select_ingest_freshness

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crypto", tags=["crypto"])


# ============================================================================
# 1 · GET /overview · 加密 tab landing page 顶层数据
# ============================================================================


@router.get(
    "/overview",
    response_model=CryptoOverviewResponse,
    summary="加密市场总览",
    description=(
        "返回:全市场总览(总市值/dominance/FGI) + 涨幅榜 top 5 + "
        "跌幅榜 top 5 + 成交榜 top 5。给加密 tab landing page 用。"
    ),
)
async def get_overview(ch: ClickHouseDep) -> CryptoOverviewResponse:
    # 走 ClickHouse · 实际数据由 Celery 任务定期写入
    # ch 是 ClickHouseClient 对象 · 内部 self._client 是 AsyncClient · M2-A
    # 联调时 type ignore · M2-B 把 ClickHouseClient 改成有 .raw 暴露 AsyncClient
    overview = await select_latest_overview(ch._client)  # noqa: SLF001
    if overview is None:
        # 没数据 · M2-A 阶段允许返 stub · M2-B 之前 Celery 任务确保有数据
        overview = MarketOverview(
            ts=datetime.now(tz=UTC),
            total_market_cap_usd=0,
            total_volume_24h_usd=0,
            btc_dominance=0,
            eth_dominance=0,
            fear_greed_value=0,
            fear_greed_classification="N/A",
        )

    # 涨幅榜 / 跌幅榜 / 成交榜 · 都取 spot top 5(M2-D 可改成 perp)
    try:
        top_gainers = await select_latest_tickers(
            ch._client,  # noqa: SLF001
            instrument="spot",
            sort_by="change_pct_24h",
            order="DESC",
            limit=5,
        )
        top_losers = await select_latest_tickers(
            ch._client,  # noqa: SLF001
            instrument="spot",
            sort_by="change_pct_24h",
            order="ASC",
            limit=5,
        )
        top_volume = await select_latest_tickers(
            ch._client,  # noqa: SLF001
            instrument="spot",
            sort_by="quote_volume_24h",
            order="DESC",
            limit=5,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[crypto.overview] tickers 拉取失败 · 返空榜单: %s", exc)
        top_gainers = []
        top_losers = []
        top_volume = []

    # 24H 合约总成交额:CoinGecko 免费档拿不到 derivatives_volume(硬编码 0),
    # 这里用已采集的全 perp ticker 的 quote_volume_24h 求和兜底(真实数据)。
    btc_ticker = None
    eth_ticker = None
    try:
        if overview.derivatives_volume_24h_usd <= 0:
            perp_total = await select_perp_total_quote_volume(ch._client)  # noqa: SLF001
            if perp_total > 0:
                overview = overview.model_copy(
                    update={"derivatives_volume_24h_usd": perp_total},
                )
        # BTC/ETH 价格卡:按 symbol 精确取 perp ticker(不依赖涨跌幅榜)
        by_sym = await select_tickers_by_symbols(
            ch._client,  # noqa: SLF001
            instrument="perp",
            symbols=["BTC/USDT", "ETH/USDT"],
        )
        btc_ticker = by_sym.get("BTC/USDT")
        eth_ticker = by_sym.get("ETH/USDT")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[crypto.overview] 合约成交额/BTC-ETH ticker 拉取失败: %s", exc)

    return CryptoOverviewResponse(
        market_overview=overview,
        top_gainers=top_gainers,
        top_losers=top_losers,
        top_volume=top_volume,
        btc_ticker=btc_ticker,
        eth_ticker=eth_ticker,
    )


# ============================================================================
# 2 · GET /tickers/24h · 涨幅榜
# ============================================================================


@router.get(
    "/tickers/24h",
    response_model=Tickers24hResponse,
    summary="24h ticker 排行榜",
)
async def get_tickers_24h(
    ch: ClickHouseDep,
    instrument: Annotated[Literal["spot", "perp"], Query()] = "spot",
    sort_by: Annotated[
        Literal["change_pct_24h", "quote_volume_24h", "last_price"], Query()
    ] = "change_pct_24h",
    order: Annotated[Literal["desc", "asc"], Query()] = "desc",
    # ADR-0018 / 列表全域化:上限 100 → 1000,允许前端一次取全市场 perp(~623)做
    # 全域排序 + 无限滚动。USDT 永续 ~527、全 quote ~623,1000 留足头部。
    top: Annotated[int, Query(ge=1, le=1000)] = 20,
) -> Tickers24hResponse:
    try:
        items = await select_latest_tickers(
            ch._client,  # noqa: SLF001
            instrument=instrument,
            sort_by=sort_by,
            order=order.upper(),
            limit=top,
        )
    except ValueError as exc:
        # select_latest_tickers 对 sort_by/order 白名单校验失败
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc),
        ) from exc

    return Tickers24hResponse(
        instrument=instrument, sort_by=sort_by, order=order, items=items,
    )


# ============================================================================
# 2.6 · GET /boll-scan · 布林做T结构信号列表(做T A-1 · 只读 Redis 快照)
# ============================================================================

_BOLL_SNAPSHOT_KEY = "boll:snapshot:latest"  # ★须与 worker tasks/boll_scan._SNAPSHOT_KEY 一致
_BIAS_FILTER = {"long": "偏多", "short": "偏空", "neutral": "中性"}


@router.get(
    "/boll-scan",
    response_model=BollScanResponse,
    summary="布林做T结构信号列表(只读快照 · 结构描述非建议)",
    description=(
        "读 M1 boll_scan 每轮落的全量结构快照(Redis · ★只读不触发计算、不下单、不写任何东西)· "
        "返回各币布林结构状态 + 倾向(偏多/偏空/中性 · 描述非建议)。无快照(未落首份 / TTL 过期)"
        "返回空列表 + as_of=null(不报错)。bias=long/short/neutral 筛选 · transition=true 仅看本轮"
        "转换 · 顶层 disclaimer 供前端展示免责。"
    ),
)
async def get_boll_scan(
    bias: Annotated[Literal["long", "short", "neutral"] | None, Query()] = None,
    transition: Annotated[bool | None, Query()] = None,
    sort: Annotated[Literal["transition", "change", "bias"], Query()] = "transition",
) -> BollScanResponse:
    redis = await get_redis()
    raw = await redis.get(_BOLL_SNAPSHOT_KEY)
    if not raw:
        # M1 还没落第一份 / 快照 TTL 过期 → 空列表(前端显示「暂无信号」· 不报错)
        return BollScanResponse(as_of=None, count=0, items=[])

    data = json.loads(raw)
    # ★容错:旧/不兼容快照行(部署过渡窗口 · 新增字段缺失)跳过,绝不 500 →
    #   降级为可解析子集 / 空列表(待下一轮 beat 写新格式快照即自动恢复)。
    items: list[BollScanItem] = []
    skipped = 0
    for row in data.get("items", []):
        try:
            items.append(BollScanItem(**row))
        except ValidationError:  # noqa: PERF203
            skipped += 1
    if skipped:
        logger.warning(
            "[boll-scan] 跳过 %d 条不兼容快照行(部署过渡?)· 待下一轮 beat 刷新恢复", skipped,
        )

    if bias is not None:
        want = _BIAS_FILTER[bias]
        items = [it for it in items if it.bias == want]
    if transition is not None:
        items = [it for it in items if it.transition is transition]

    if sort == "transition":
        # 本轮转换的排前 · 组内按 24h 涨跌幅绝对值大→小(波动大优先看)
        items.sort(key=lambda it: (not it.transition, -abs(it.change_pct_24h or 0.0)))
    elif sort == "change":
        items.sort(key=lambda it: -(it.change_pct_24h or 0.0))
    else:  # bias:偏多 → 中性 → 偏空
        rank = {"偏多": 0, "中性": 1, "偏空": 2}
        items.sort(key=lambda it: rank.get(it.bias, 1))

    return BollScanResponse(as_of=data.get("as_of"), count=len(items), items=items)


# ============================================================================
# 2.7 · GET /boll-structure/{symbol} · 单币布林做T结构(做T B-1)
# ============================================================================

_BOLL_STRUCT_LOOKBACK = 30  # select_kline 取最近 30 根 15m(布林 20 预热 + 斜率/带宽回看余量)


@router.get(
    "/boll-structure/{symbol}",
    response_model=BollStructureResponse,
    summary="单币布林做T结构(只读 · 结构描述非建议)",
    description=(
        "给定 symbol 返回当前布林 6 态结构(状态/倾向/通道位置/三轨/转换)· 给详情页做T结构模块用。"
        "★Top150 命中 A-1 快照(零重算)· 长尾按需现算 15m 布林 · 数据不足/非加密优雅降级"
        "(available=false · 不报错)· 结构口径与 A-1 列表 / TG 影子同源。倾向仅偏多/偏空/中性。"
    ),
)
async def get_boll_structure(
    ch: ClickHouseDep,
    symbol: Annotated[str, Path(min_length=3, examples=["BTCUSDT"])],
) -> BollStructureResponse:
    sym = symbol.strip().upper().replace("/", "")  # Binance 风格无斜杠 · 与快照 / kline 表对齐
    # ① 优先复用 A-1 全量快照(Top150 命中即【零重算】· 与列表/TG 同一份结构)
    redis = await get_redis()
    raw = await redis.get(_BOLL_SNAPSHOT_KEY)
    if raw:
        data = json.loads(raw)
        for row in data.get("items", []):
            if row.get("symbol") == sym:
                try:
                    item = BollScanItem(**row)
                except ValidationError:
                    break  # 旧/不兼容快照行 → 落到现算兜底(同 boll-scan 端点容错纪律)
                return BollStructureResponse(
                    symbol=sym, available=True, source="snapshot",
                    as_of=data.get("as_of"), item=item,
                )
    # ② 长尾兜底:快照未覆盖的币 → 按需现算一次(复用同一 classify · 不依赖快照)
    return await _compute_boll_structure(ch, sym)


async def _compute_boll_structure(ch: ClickHouseClient, sym: str) -> BollStructureResponse:
    """长尾币按需现算布林结构 · ★复用 boll_state.classify(与 A-1 列表 / TG 影子同源)·
    只读 CH(15m kline + ticker + funding)· 数据不足/失败优雅降级 available=false,绝不崩。
    """
    try:
        klines = await ch.select_kline(
            symbol=sym, market="crypto", period="15m",
            limit=_BOLL_STRUCT_LOOKBACK, instrument="perp",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[boll-structure] %s 取 15m kline 失败: %s", sym, exc)
        klines = []
    snap = classify(klines)  # 不足 24 根 / 数据问题 → None
    if snap is None:
        return BollStructureResponse(symbol=sym, available=False, source="none")
    # 24h 涨跌 / 资金费率:失败降级 None,绝不阻断结构主体(带宽/布林照常)
    change_pct: float | None = None
    funding: float | None = None
    base, quote = _split_symbol(sym)
    ccxt_sym = f"{base}/{quote}" if quote else sym
    try:
        tk = (await select_tickers_by_symbols(
            ch._client, instrument="perp", symbols=[ccxt_sym],  # noqa: SLF001
        )).get(ccxt_sym)
        change_pct = tk.change_pct_24h if tk else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[boll-structure] %s ticker 取失败: %s", sym, exc)
    try:
        funding = (await select_latest_funding_rates(
            ch._client, symbols=[sym],  # noqa: SLF001
        )).get(sym)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[boll-structure] %s funding 取失败: %s", sym, exc)
    row = to_snapshot_row(
        sym, snap, change_pct_24h=change_pct, funding_rate=funding,
        transition=False, prev_state=None,  # ★现算无边沿跟踪 · transition 恒 False
    )
    return BollStructureResponse(
        symbol=sym, available=True, source="computed",
        as_of=datetime.now(tz=UTC), item=BollScanItem(**row),
    )


# ============================================================================
# 2.5 · GET /futures/metrics-batch · 榜单级合约指标批量(任务3)
# ============================================================================


@router.get(
    "/futures/metrics-batch",
    response_model=FuturesMetricsBatchResponse,
    summary="榜单级合约指标批量(资金费率/账户多空比/OI 24H变化)",
    description=(
        "一次性返回多个 symbol 的合约指标 · 给加密列表页 3 列用 · "
        "symbols 逗号分隔 Binance 风格(如 BTCUSDT,ETHUSDT)· 最多 200 个。"
        "不在采集名单(top100)里的 symbol 不返回 → 前端显示「—」。"
    ),
)
async def get_futures_metrics_batch(
    ch: ClickHouseDep,
    symbols: Annotated[str, Query(description="逗号分隔 · Binance 风格 · 如 BTCUSDT,ETHUSDT")],
) -> FuturesMetricsBatchResponse:
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms:
        return FuturesMetricsBatchResponse(items=[])
    if len(syms) > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"symbols 最多 200 个 · 当前 {len(syms)}",
        )
    metrics = await select_futures_metrics_batch(
        ch._client,  # noqa: SLF001
        symbols=syms,
    )
    items = [
        FuturesMetricItem(
            symbol=sym,
            funding_rate=m.get("funding_rate"),
            account_long_short_ratio=m.get("account_long_short_ratio"),
            oi_change_pct_24h=m.get("oi_change_pct_24h"),
        )
        for sym, m in metrics.items()
    ]
    return FuturesMetricsBatchResponse(items=items)


# ============================================================================
# 3 · GET /futures/{symbol}/funding-rate
# ============================================================================


@router.get(
    "/futures/{symbol}/funding-rate",
    response_model=FundingRateResponse,
    summary="合约资金费率时间序列",
    description="symbol 用 Binance Futures 风格 'BTCUSDT'(无斜杠)。",
)
async def get_funding_rate(
    ch: ClickHouseDep,
    symbol: Annotated[str, Path(min_length=3, examples=["BTCUSDT"])],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> FundingRateResponse:
    items = await select_funding_rates(
        ch._client,  # noqa: SLF001
        symbol=symbol, limit=limit,
    )
    return FundingRateResponse(symbol=symbol, items=items)


# ============================================================================
# 4 · GET /futures/{symbol}/open-interest
# ============================================================================


@router.get(
    "/futures/{symbol}/open-interest",
    response_model=OpenInterestResponse,
    summary="合约未平仓量(OI)时间序列",
)
async def get_open_interest(
    ch: ClickHouseDep,
    symbol: Annotated[str, Path(min_length=3, examples=["BTCUSDT"])],
    limit: Annotated[int, Query(ge=1, le=500)] = 288,
) -> OpenInterestResponse:
    items = await select_open_interest(
        ch._client,  # noqa: SLF001
        symbol=symbol, limit=limit,
    )
    return OpenInterestResponse(symbol=symbol, items=items)


# ============================================================================
# 5 · GET /futures/{symbol}/long-short-ratio
# ============================================================================


@router.get(
    "/futures/{symbol}/long-short-ratio",
    response_model=LongShortRatioResponse,
    summary="合约多空比时间序列",
    description="同时返回三套指标:top trader 账户 / top trader 持仓 / taker buy-sell。",
)
async def get_long_short_ratio(
    ch: ClickHouseDep,
    symbol: Annotated[str, Path(min_length=3, examples=["BTCUSDT"])],
    limit: Annotated[int, Query(ge=1, le=500)] = 288,
) -> LongShortRatioResponse:
    items = await select_long_short(
        ch._client,  # noqa: SLF001
        symbol=symbol, limit=limit,
    )
    return LongShortRatioResponse(symbol=symbol, items=items)


# ============================================================================
# 6 · GET /futures/{symbol}/info
# ============================================================================


@router.get(
    "/futures/{symbol}/info",
    response_model=FuturesSymbolInfo,
    summary="合约元信息(下次资金费率 / 标记价 / 指数价 / 最大杠杆)",
    description=(
        "M2-C.2.1 起:mark_price / index_price / next_funding_time / last_funding_rate "
        "取自 crypto_premium_index(premiumIndex 每分钟回源 · 真实值)· 修复原 +8h 硬编码 bug。"
        "premium 未采到该 symbol 时兜底回 funding 表 + 8h 估算(老行为)· "
        "max_leverage 暂留 125(ADR-0020 §1.4 低优先 · 后续从 exchangeInfo 取真值)。"
    ),
)
async def get_futures_info(
    ch: ClickHouseDep,
    symbol: Annotated[str, Path(min_length=3, examples=["BTCUSDT"])],
) -> FuturesSymbolInfo:
    latest_oi = await select_open_interest(
        ch._client, symbol=symbol, limit=1,  # noqa: SLF001
    )
    if not latest_oi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"symbol {symbol} 没有 OI 数据 · 数据预热未覆盖此 symbol",
        )
    oi = latest_oi[-1]

    # base/quote 简单切尾 USDT/USDC/BUSD
    base, quote = _split_symbol(symbol)

    # 价/资金费来源:真标记价(premiumIndex)优先 · 修 +8h 硬编码 bug
    premium = await select_latest_premium_index(
        ch._client, symbol=symbol,  # noqa: SLF001
    )
    if premium is not None:
        mark_price = premium.mark_price
        index_price = premium.index_price  # 真指数价 · 基差 = mark - index(不再用 mark 近似)
        last_funding_rate = premium.last_funding_rate
        next_funding = premium.next_funding_time  # 真 nextFundingTime(回源)
    else:
        # 兜底:premium 未采到 · 退回 funding 表最近一条 + 8h 估算(老 stub 行为)
        latest_funding = await select_funding_rates(
            ch._client, symbol=symbol, limit=1,  # noqa: SLF001
        )
        if not latest_funding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"symbol {symbol} 没有 premium / funding 数据 · 数据预热未覆盖此 symbol",
            )
        fr = latest_funding[-1]
        mark_price = fr.mark_price
        index_price = fr.mark_price  # 兜底无指数价 · 用 mark 近似
        last_funding_rate = fr.rate
        next_funding = fr.ts + timedelta(hours=8)

    return FuturesSymbolInfo(
        symbol=symbol,
        base_asset=base,
        quote_asset=quote,
        contract_type="perpetual",
        mark_price=mark_price,
        index_price=index_price,
        last_funding_rate=last_funding_rate,
        next_funding_time=next_funding,
        max_leverage=125,  # ADR-0020 §1.4 低优先 · 后续从 exchangeInfo 取真值
        open_interest_coin=oi.oi_coin,
        open_interest_usd=oi.oi_usd,
    )


# ============================================================================
# 6.5 · GET /futures/{symbol}/basis · 基差时序(详情页 ⑥ 基差图)· M2-C.2.4
# ============================================================================


@router.get(
    "/futures/{symbol}/basis",
    response_model=BasisSeriesResponse,
    summary="基差时序(合约价 / 指数价 / 基差率)· 读 crypto_premium_index",
    description=(
        "M2-C.2.4 · 来自 premiumIndex 每分钟采集的 crypto_premium_index 时序。"
        "基差率 = (mark − index) / index × 100(% · 可正可负)。空 = 未预热 / 待采集。"
    ),
)
async def get_basis_series(
    ch: ClickHouseDep,
    symbol: Annotated[str, Path(min_length=3, examples=["BTCUSDT"])],
    limit: Annotated[int, Query(ge=1, le=1440)] = 288,
) -> BasisSeriesResponse:
    rows = await select_premium_index_series(
        ch._client, symbol, limit=limit,  # noqa: SLF001
    )
    items = [
        BasisPoint(
            ts=ts, mark_price=mark, index_price=index,
            basis_pct=((mark - index) / index * 100) if index > 0 else 0.0,
        )
        for ts, mark, index in rows
        if mark > 0 and index > 0
    ]
    return BasisSeriesResponse(symbol=symbol, items=items)


# ============================================================================
# 7 · GET /fear-greed
# ============================================================================


@router.get(
    "/fear-greed",
    response_model=FearGreedResponse,
    summary="Fear & Greed Index 时间序列",
)
async def get_fear_greed(
    ch: ClickHouseDep,
    limit: Annotated[int, Query(ge=1, le=365)] = 30,
) -> FearGreedResponse:
    items = await select_fear_greed_series(
        ch._client, limit=limit,  # noqa: SLF001
    )
    return FearGreedResponse(items=items)


# ============================================================================
# 9 · GET /ingest-status · 采集新鲜度监控(刀D 还债 · 丙方案纯读 max(ts))
# ============================================================================


@router.get(
    "/ingest-status",
    response_model=IngestStatusResponse,
    summary="采集新鲜度监控(各 CH 表 max(ts) vs now · 防数据 stale 无人发现)",
    description=(
        "刀D 还债:纯读各表 maxOrNull(ts) 推断每个数据源新鲜度,零侵入采集任务。"
        "加密 7 源判 stale(阈值=max(数据栅格,任务频率)×3 · funding 按 8h 结算栅格、"
        "kline 脉搏按缺今日 bar 超 1 天);股票表 v1 裸报不判(交易时段语义)。"
        "any_stale=true 即有源过期 · curl/浏览器直接看。"
    ),
)
async def get_ingest_status(ch: ClickHouseDep) -> IngestStatusResponse:
    latest_map = await select_ingest_freshness(ch._client)  # noqa: SLF001
    now = datetime.now(tz=UTC)
    crypto_items, equity_items, any_stale = build_ingest_status(latest_map, now)
    return IngestStatusResponse(
        as_of=now, any_stale=any_stale, crypto=crypto_items, equities=equity_items,
    )


# ============================================================================
# helpers
# ============================================================================


def _split_symbol(symbol: str) -> tuple[str, str]:
    """`BTCUSDT` → ('BTC', 'USDT')."""
    for quote in ("USDT", "USDC", "BUSD", "FDUSD"):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)], quote
    return symbol, ""
