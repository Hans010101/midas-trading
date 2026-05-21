"""市场分析路由 · /api/v1/analysis · M1。

GET /chan?symbol=&market=&period=&limit= · 缠论分析(笔 + 分型 + 中枢)
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import (
    BinanceFuturesSourceDep,
    ClickHouseDep,
    CnSourceDep,
    CryptoSourceDep,
    UsSourceDep,
)

# M2-B(0017 ADR)· 缠论 + 决策卡都加 instrument 参数 · perp K 线分析
Instrument = Literal["spot", "perp"]
from app.schemas.ai_decision import DecisionCardResponse
from app.schemas.chan import (
    BiResponse,
    BuySellPointResponse,
    ChanAnalysisResponse,
    FractalPointResponse,
    ZhongshuResponse,
)
from app.services.ai.cache import get_cached_card, set_cached_card
from app.services.ai.workflow import run_decision_workflow
from app.schemas.market import Market, Period
from app.services.analysis.chan import analyze as analyze_chan
from app.services.data_sources.base import BaseDataSource

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get(
    "/chan",
    response_model=ChanAnalysisResponse,
    summary="缠论分析 · 笔 + 顶底分型 + 中枢(M1 第一波)",
    description=(
        "返回笔(BI)/ 顶底分型(FX)/ 中枢(简化版 · 连续 3 笔重叠)。"
        "段 / 买卖点 / 多周期联动 在 M1 第二波 AI 决策卡里扩展。"
        "**结果仅供参考,不构成投资建议。**"
    ),
)
async def get_chan_analysis(
    ch: ClickHouseDep,
    cn: CnSourceDep,
    us: UsSourceDep,
    crypto: CryptoSourceDep,
    binance_futures: BinanceFuturesSourceDep,
    symbol: str = Query(..., min_length=1, examples=["BTC/USDT", "NVDA", "600519", "BTCUSDT"]),
    market: Market = Query(...),
    period: Period = Query("1d"),
    limit: int = Query(300, ge=30, le=1000),
    instrument: Annotated[
        Instrument,
        Query(description="'spot' 现货(默认)· 'perp' USDT-M 永续合约 · 只 crypto 支持"),
    ] = "spot",
) -> ChanAnalysisResponse:
    # M2-B 校验:perp 只允许 crypto
    if instrument == "perp" and market != "crypto":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"instrument=perp 只支持 market=crypto · 当前 market={market}",
        )

    # 拿 K 线 · 复用 market 路由的 cache-aside 路径(直查 CH)
    klines = await ch.select_kline(
        symbol=symbol, market=market, period=period, limit=limit, instrument=instrument,
    )

    if len(klines) < 30:
        # CH 不够 · 回源拉(跟 /kline 路由同源)
        # M2-B · perp 走 BinanceFuturesSource · spot 走原 _source_for
        if instrument == "perp":
            fetch_symbol = symbol.replace("/", "") if "/" in symbol else symbol
            try:
                klines = await binance_futures.fetch_kline(fetch_symbol, period, limit=limit)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"perp K 线数据不足 30 根 · 无法做缠论分析:{e}",
                ) from e
        else:
            source = _source_for(market, cn=cn, us=us, crypto=crypto)
            try:
                klines = await source.fetch_kline(symbol, period, limit=limit)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"K 线数据不足 30 根 · 无法做缠论分析:{e}",
                ) from e

    result = await analyze_chan(klines, period, symbol)

    logger.info(
        "[chan] symbol=%s market=%s period=%s bars=%d → fx=%d bi=%d zs=%d",
        symbol, market, period, result.bar_count,
        len(result.fractals), len(result.bis), len(result.zhongshus),
    )

    return ChanAnalysisResponse(
        symbol=symbol,
        market=market,
        period=period,
        bar_count=result.bar_count,
        fractals=[
            FractalPointResponse(ts=f.ts, price=f.price, kind=f.kind)            for f in result.fractals
        ],
        bis=[
            BiResponse(
                start_ts=b.start_ts, end_ts=b.end_ts,
                start_price=b.start_price, end_price=b.end_price,
                direction=b.direction,                high=b.high, low=b.low,
                power=b.power, length=b.length,
            )
            for b in result.bis
        ],
        zhongshus=[
            ZhongshuResponse(
                start_ts=z.start_ts, end_ts=z.end_ts,
                high=z.high, low=z.low,
            )
            for z in result.zhongshus
        ],
        buy_sell_points=[
            BuySellPointResponse(
                ts=p.ts, price=p.price,
                kind=p.kind,  # type: ignore[arg-type]
                description=p.description,
            )
            for p in result.buy_sell_points
        ],
    )


def _source_for(
    market: Market,
    *,
    cn: CnSourceDep,
    us: UsSourceDep,
    crypto: CryptoSourceDep,
) -> BaseDataSource:
    mapping: dict[Market, BaseDataSource] = {
        "cn": cn, "us": us, "crypto": crypto,
    }
    return mapping[market]


# ===== AI 决策卡 · 0012 ADR M1 二波 =====


@router.get(
    "/decision-card",
    response_model=DecisionCardResponse,
    summary="AI 决策卡 · 技术面单 Agent + 缠论买卖点(M1 第二波)",
    description=(
        "返回结构化 AI 决策卡:综合评分(M1 二波 = 技术面分)/ 解读 / 关键位 / "
        "缠论近期买卖点 / disclaimer 双层兜底。"
        "**结果仅供参考,不构成投资建议。** "
        "当 DEEPSEEK_API_KEY 未配置时,llm_mode='mock' · 返回固定假分析以保持 UI 可用。"
    ),
)
async def get_decision_card(
    ch: ClickHouseDep,
    cn: CnSourceDep,
    us: UsSourceDep,
    crypto: CryptoSourceDep,
    binance_futures: BinanceFuturesSourceDep,
    symbol: str = Query(..., min_length=1, examples=["BTC/USDT", "NVDA", "600519", "BTCUSDT"]),
    market: Market = Query(...),
    period: Period = Query("1d"),
    limit: int = Query(300, ge=30, le=1000),
    instrument: Annotated[
        Instrument,
        Query(description="'spot' 现货(默认)· 'perp' USDT-M 永续合约 · 只 crypto 支持"),
    ] = "spot",
) -> DecisionCardResponse:
    # M2-B 校验
    if instrument == "perp" and market != "crypto":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"instrument=perp 只支持 market=crypto · 当前 market={market}",
        )

    # 1. 缓存命中检查 · 注:cache key 暂用 (market, symbol, period) · M2-D 加 instrument
    # WIP:M2-D 联调时如果发现 spot/perp 缓存串扰 · 改 set_cached_card 接口加 instrument
    cached = await get_cached_card(market, symbol, period)
    if cached is not None:
        logger.info(
            "[decision-card] CACHE HIT symbol=%s market=%s instrument=%s period=%s",
            symbol, market, instrument, period,
        )
        return cached

    # 2. 拿 K 线(跟 /chan 同源,先 CH 后回源)
    klines = await ch.select_kline(
        symbol=symbol, market=market, period=period, limit=limit, instrument=instrument,
    )
    if len(klines) < 30:
        if instrument == "perp":
            fetch_symbol = symbol.replace("/", "") if "/" in symbol else symbol
            try:
                klines = await binance_futures.fetch_kline(fetch_symbol, period, limit=limit)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"perp K 线数据不足 30 根 · 无法生成决策卡:{e}",
                ) from e
        else:
            source = _source_for(market, cn=cn, us=us, crypto=crypto)
            try:
                klines = await source.fetch_kline(symbol, period, limit=limit)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"K 线数据不足 30 根 · 无法生成决策卡:{e}",
                ) from e

    # 3. 跑 LangGraph workflow(mock 或 real,workflow 不关心)
    card = await run_decision_workflow(symbol, market, period, klines)

    logger.info(
        "[decision-card] symbol=%s market=%s period=%s score=%d label=%s"
        " signals=%d mode=%s",
        symbol, market, period, card.composite_score, card.composite_label,
        len(card.chan_signals), card.llm_mode,
    )

    # 4. 写缓存 · 失败不阻塞
    await set_cached_card(card)

    return card
