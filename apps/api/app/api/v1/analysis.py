"""市场分析路由 · /api/v1/analysis · M1。

GET /chan?symbol=&market=&period=&limit= · 缠论分析(笔 + 分型 + 中枢)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    BinanceFuturesSourceDep,
    ClickHouseDep,
    CnSourceDep,
    CryptoSourceDep,
    HkSourceDep,
    OptionalCurrentUserDep,
    RequestLangDep,
    UsSourceDep,
)
from app.core.database import get_db
from app.schemas.ai_accuracy import AiAccuracyResponse
from app.schemas.ai_decision import DecisionCardResponse
from app.schemas.chan import (
    BiResponse,
    BuySellPointResponse,
    ChanAnalysisResponse,
    FractalPointResponse,
    ZhongshuResponse,
)
from app.schemas.market import Kline, Market, Period
from app.schemas.strategy import (
    StrategyKind,
    StrategyRecommendResponse,
    StrategySignalsResponse,
)
from app.services.ai.accuracy import compute_accuracy
from app.services.ai.actionable import with_actionable
from app.services.ai.cache import get_cached_card, set_cached_card
from app.services.ai.extreme_signals import compute_extreme_signals
from app.services.ai.memory import record_decision
from app.services.ai.strategy_recommend import recommend_strategy
from app.services.ai.strategy_signals import scan_signals
from app.services.ai.workflow import run_decision_workflow
from app.services.analysis.chan import analyze as analyze_chan
from app.services.data_sources.base import BaseDataSource
from app.services.i18n import translate
from app.services.membership import resolve_plan

# 仅本路由用 · 不放 deps.py 避免对其他路由产生隐式依赖(virtual.py 已自定义本地 DbDep)
DbDep = Annotated[AsyncSession, Depends(get_db)]

# M2-B(0017 ADR)· 缠论 + 决策卡都加 instrument 参数 · perp K 线分析
Instrument = Literal["spot", "perp"]

logger = logging.getLogger(__name__)


# ===== Pro 门控空壳(变现强化 · 决策卡 + 策略清单后端真门控)=====
# 🔴 非 Pro(未登录 OR 免费)返回这些空壳:绝不含真实 AI 决策内容(score/解读/信号全空)·
#    防 F12 白嫖。前端据 locked=True + 登录态出遮罩(未登录→注册墙 / 免费→付费墙)。


def _locked_decision_card(
    symbol: str, market: Market, period: Period,
) -> DecisionCardResponse:
    """决策卡门控空壳 · 无真实内容(score=0/中性/空解读/无信号/无 actionable)。"""
    return DecisionCardResponse(
        symbol=symbol, market=market, period=period,
        generated_at=datetime.now(UTC),
        composite_score=0, composite_label="中性", composite_confidence=0.0,
        agent_scores=[], contradiction=None, narrative="",
        chan_signals=[], actionable=None, disclaimer="",
        cached=False, token_usage=0, llm_mode="mock", locked=True,
    )


def _locked_strategy_signals(
    symbol: str, market: Market, period: Period, instrument: Instrument,
    strategy: StrategyKind,
) -> StrategySignalsResponse:
    """策略清单门控空壳 · 无真实信号(signals 空 · current_triggered=False)。"""
    return StrategySignalsResponse(
        symbol=symbol, market=market, period=period, instrument=instrument,
        strategy=strategy, bar_count=0, signals=[], current_triggered=False,
        last_signal=None, locked=True,
    )

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get(
    "/chan",
    response_model=ChanAnalysisResponse,
    summary="缠论分析 · 笔 + 顶底分型 + 中枢(M1 第一波)",
    description=(
        "返回笔(BI)/ 顶底分型(FX)/ 中枢(简化版 · 连续 3 笔重叠)。"
        "段 / 买卖点 / 多周期联动 在 M1 第二波 AI 决策卡里扩展。"
    ),
)
async def get_chan_analysis(
    ch: ClickHouseDep,
    cn: CnSourceDep,
    us: UsSourceDep,
    crypto: CryptoSourceDep,
    hk: HkSourceDep,
    binance_futures: BinanceFuturesSourceDep,
    lang: RequestLangDep,
    symbol: str = Query(..., min_length=1, examples=["BTC/USDT", "NVDA", "600519", "00700"]),
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
            detail=translate("common.perp_only_crypto", lang, market=market),
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
                    detail=translate("analysis.perp_kline_insufficient_chan", lang, e=e),
                ) from e
        else:
            source = _source_for(market, cn=cn, us=us, crypto=crypto, hk=hk)
            try:
                klines = await source.fetch_kline(symbol, period, limit=limit)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=translate("analysis.kline_insufficient_chan", lang, e=e),
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
            FractalPointResponse(ts=f.ts, price=f.price, kind=f.kind)
            for f in result.fractals
        ],
        bis=[
            BiResponse(
                start_ts=b.start_ts, end_ts=b.end_ts,
                start_price=b.start_price, end_price=b.end_price,
                direction=b.direction, high=b.high, low=b.low,
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
                kind=p.kind,
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
    hk: HkSourceDep | None = None,
) -> BaseDataSource:
    # hk 可选(chan/decision-card/strategy 港股已注入 hk · 不传则不含 hk · 防 KeyError)
    mapping: dict[Market, BaseDataSource] = {
        "cn": cn, "us": us, "crypto": crypto,
    }
    if hk is not None:
        mapping["hk"] = hk
    return mapping[market]


# ===== AI 决策卡 · 0012 ADR M1 二波 =====


@router.get(
    "/decision-card",
    response_model=DecisionCardResponse,
    summary="AI 决策卡 · 技术面单 Agent + 缠论买卖点(M1 第二波)",
    description=(
        "返回结构化 AI 决策卡:综合评分(M1 二波 = 技术面分)/ 解读 / 关键位 / "
        "缠论近期买卖点。"
        "当 DEEPSEEK_API_KEY 未配置时,llm_mode='mock' · 返回固定假分析以保持 UI 可用。"
    ),
)
async def get_decision_card(
    ch: ClickHouseDep,
    cn: CnSourceDep,
    us: UsSourceDep,
    crypto: CryptoSourceDep,
    hk: HkSourceDep,
    binance_futures: BinanceFuturesSourceDep,
    db: DbDep,
    user: OptionalCurrentUserDep,
    lang: RequestLangDep,
    symbol: str = Query(..., min_length=1, examples=["BTC/USDT", "NVDA", "600519", "BTCUSDT"]),
    market: Market = Query(...),
    period: Period = Query("1d"),
    limit: int = Query(300, ge=30, le=1000),
    instrument: Annotated[
        Instrument,
        Query(description="'spot' 现货(默认)· 'perp' USDT-M 永续合约 · 只 crypto 支持"),
    ] = "spot",
) -> DecisionCardResponse:
    # ★ Pro 门控:非 Pro(未登录 OR 免费)在跑 workflow / 查缓存【之前】拦截返 locked 空壳 ——
    #   后端真门控(防 F12)+ 不烧 LLM 不算因子(省算力)。Pro 用户照常走下方完整流程。
    plan = "free" if user is None else await resolve_plan(db, user.id)
    if plan != "pro":
        return _locked_decision_card(symbol, market, period)

    # ★i18n:语言由 RequestLangDep 解析 · 2026-07-05 收窄=仅显式 X-Lang override,否则 zh
    #   (language_pref / Accept 停用 · 见 i18n/lang.py + docs/decisions/0047)。
    #   ★zh 用户 lang="zh" → 全链路走原代码行、缓存原 key(无后缀),逐字节零变化。
    #   原直读 user.language_pref 是生产 bug 根源(Hans pref='en' → 决策卡英文),已根治。

    # M2-B 校验
    if instrument == "perp" and market != "crypto":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("common.perp_only_crypto", lang, market=market),
        )

    # 1. 缓存命中检查 · 注:cache key 暂用 (market, symbol, period) · M2-D 加 instrument
    # WIP:M2-D 联调时如果发现 spot/perp 缓存串扰 · 改 set_cached_card 接口加 instrument
    cached = await get_cached_card(market, symbol, period, language=lang)
    if cached is not None:
        logger.info(
            "[decision-card] CACHE HIT symbol=%s market=%s instrument=%s period=%s",
            symbol, market, instrument, period,
        )
        # 0036 批次甲:对缓存卡片补算 actionable(对旧缓存也鲁棒 · 幂等)
        return with_actionable(cached)

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
                    detail=translate("analysis.perp_kline_insufficient_decision_card", lang, e=e),
                ) from e
        else:
            # 港股阶段三单元1:decision-card 注入 hk(此前 _source_for 无 hk → market=hk KeyError)
            source = _source_for(market, cn=cn, us=us, crypto=crypto, hk=hk)
            try:
                klines = await source.fetch_kline(symbol, period, limit=limit)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=translate("analysis.kline_insufficient_decision_card", lang, e=e),
                ) from e

    # 3. 跑 LangGraph workflow(mock 或 real,workflow 不关心)
    card = await run_decision_workflow(symbol, market, period, klines, language=lang)

    logger.info(
        "[decision-card] symbol=%s market=%s period=%s score=%d label=%s"
        " signals=%d mode=%s",
        symbol, market, period, card.composite_score, card.composite_label,
        len(card.chan_signals), card.llm_mode,
    )

    # 4. 写缓存(不含 actionable · 由下方派生)· 失败不阻塞
    await set_cached_card(card, language=lang)

    # 5. 旁路记录决策卡历史(0036 批次乙 · best-effort · 永不阻塞响应)
    # price_at 用 klines[-1].close · 跟 workflow 内部 last_close 同源;
    # 失败已在 record_decision 内吞掉(只记 warning),此处不需 try/except。
    await record_decision(
        db, card=card, instrument=instrument, price_at=Decimal(str(klines[-1].close)),
        language=lang,
    )

    # 6. 派生 actionable 可下单建议(0036 批次甲 · API 层 · 不改 AI 管线)
    return with_actionable(card)


# ===== AI 历史命中率 · 0036 批次乙 sub-unit C(自学习闭环呈现层后端)=====


@router.get(
    "/ai-accuracy",
    response_model=AiAccuracyResponse,
    summary="AI 历史命中率 · 总体 + 市场 / 方向 / 置信度分桶(0036 批次乙)",
    description=(
        "返回 AI 决策卡历史命中率统计:基于 reflection 事后实测涨跌验证的记录"
        "(was_correct)聚合。总体 + 按市场 / 方向 / 置信度三维分桶,每桶带样本数。"
        "★ 纯只读统计(读 PG · 不打实时上游 · 不碰下单)。"
        "★ 小样本桶(sample_count < min_reliable_sample · reliable=false)命中率仅供参考。"
    ),
)
async def get_ai_accuracy(
    db: DbDep,
    since_days: Annotated[
        int | None,
        Query(ge=1, le=3650, description="只统计最近 N 天分析(analyzed_at)的记录 · 不传=全部历史"),
    ] = None,
    llm_mode: Annotated[
        Literal["mock", "real"] | None,
        Query(description="按 LLM 模式过滤 · 不传=全部(未来切真实模型后可只看 real)"),
    ] = None,
) -> AiAccuracyResponse:
    since = (
        datetime.now(UTC) - timedelta(days=since_days) if since_days is not None else None
    )
    return await compute_accuracy(
        db, since=since, since_days=since_days, llm_mode=llm_mode,
    )


# ===== AI 策略信号 + 推荐 · 0037 形态A 单元2(展示型 · 只读 · 不下单)=====


async def _fetch_klines_for_strategy(
    *,
    ch: ClickHouseDep,
    cn: CnSourceDep,
    us: UsSourceDep,
    crypto: CryptoSourceDep,
    hk: HkSourceDep,
    binance_futures: BinanceFuturesSourceDep,
    symbol: str,
    market: Market,
    period: Period,
    instrument: Instrument,
    limit: int,
    lang: str,
    purpose_key: str,
) -> list[Kline]:
    """策略端点专用 K 线获取(只读 · 先 CH 后回源)· 复用 decision-card 同源模式。

    ★ 只读 select_kline(CH 已采)· 不足回源拉(与 /chan、/decision-card 同源)·
    绝不写、绝不下单。不改现有 chan/decision-card 端点(它们各自内联,本 helper 仅新端点用)。
    ★i18n Phase3 刀2:双层插值 —— purpose_key(analysis.purpose_*)先按 lang 译成动词短语,
      再作为 {purpose} 填入错误模板;zh 下逐字节等于原 f-string。
    """
    # 双层插值:先把 purpose_key 译成本地化动词短语(zh → 原中文字面量)
    purpose = translate(purpose_key, lang)
    if instrument == "perp" and market != "crypto":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=translate("common.perp_only_crypto", lang, market=market),
        )
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
                    detail=translate(
                        "analysis.perp_kline_insufficient_purpose", lang, purpose=purpose, e=e,
                    ),
                ) from e
        else:
            source = _source_for(market, cn=cn, us=us, crypto=crypto, hk=hk)
            try:
                klines = await source.fetch_kline(symbol, period, limit=limit)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=translate(
                        "analysis.kline_insufficient_purpose", lang, purpose=purpose, e=e,
                    ),
                ) from e
    return klines


@router.get(
    "/strategy-signals",
    response_model=StrategySignalsResponse,
    summary="策略历史买卖信号点 · 形态A 单元2(展示型 · 只读)",
    description=(
        "返回某标的在某经典策略下的【历史买卖信号点序列】(穿越式离散信号)+ 当前是否触发。"
        "ma_cross 金叉/死叉 · rsi_reversal 超卖反弹/超买回落 · boll_reversion 触轨均值回归。"
        "★ 纯展示:只算信号、不下单、不执行;用户看完走第一层一键模拟下单。"
    ),
)
async def get_strategy_signals(
    ch: ClickHouseDep,
    cn: CnSourceDep,
    us: UsSourceDep,
    crypto: CryptoSourceDep,
    hk: HkSourceDep,
    binance_futures: BinanceFuturesSourceDep,
    db: DbDep,
    user: OptionalCurrentUserDep,
    lang: RequestLangDep,
    symbol: str = Query(..., min_length=1, examples=["BTC/USDT", "NVDA", "600519", "BTCUSDT"]),
    market: Market = Query(...),
    period: Period = Query("1d"),
    limit: int = Query(300, ge=30, le=1000),
    instrument: Annotated[
        Instrument,
        Query(description="'spot' 现货(默认)· 'perp' USDT-M 永续(只 crypto · 拍板⑦ 跟随详情页)"),
    ] = "spot",
    strategy: StrategyKind = Query(..., description="ma_cross / rsi_reversal / boll_reversion"),
) -> StrategySignalsResponse:
    # ★ Pro 门控:非 Pro(未登录 OR 免费)在 scan_signals【之前】拦截返 locked 空壳 ——
    #   后端真门控(防 F12)+ 不算信号(省算力)。Pro 用户照常走下方完整流程。
    plan = "free" if user is None else await resolve_plan(db, user.id)
    if plan != "pro":
        return _locked_strategy_signals(symbol, market, period, instrument, strategy)

    # ★i18n:lang 由 RequestLangDep 解析(2026-07-05 收窄=仅 X-Lang override,否则 zh ·
    #   language_pref/Accept 停用 · 见 lang.py + 0047)· zh 走原字面量逐字节零变化。
    klines = await _fetch_klines_for_strategy(
        ch=ch, cn=cn, us=us, crypto=crypto, hk=hk, binance_futures=binance_futures,
        symbol=symbol, market=market, period=period, instrument=instrument,
        limit=limit, lang=lang, purpose_key="analysis.purpose_gen_signals",
    )
    # extreme = 合约极端信号(★仅 crypto perp · 需 funding/OI/多空比)· 走专路;其余 5 个纯 klines。
    if strategy == "extreme":
        signals = await compute_extreme_signals(ch._client, symbol, market, instrument, klines)  # noqa: SLF001
    else:
        signals = scan_signals(klines, strategy)
    # 当前是否触发:最新一根 K 是否为信号点(klines / signals 均 ts 升序)
    current_triggered = bool(
        signals and klines and signals[-1].ts == klines[-1].ts,
    )
    logger.info(
        "[strategy-signals] symbol=%s market=%s instrument=%s period=%s strategy=%s"
        " bars=%d signals=%d triggered=%s",
        symbol, market, instrument, period, strategy,
        len(klines), len(signals), current_triggered,
    )
    return StrategySignalsResponse(
        symbol=symbol, market=market, period=period, instrument=instrument,
        strategy=strategy, bar_count=len(klines), signals=signals,
        current_triggered=current_triggered,
        last_signal=signals[-1] if signals else None,
    )


@router.get(
    "/strategy-recommend",
    response_model=StrategyRecommendResponse,
    summary="AI 推荐策略 · 形态A 单元2(纯规则 · 零 LLM · 只读)",
    description=(
        "给一个标的,纯规则推荐「现在适合用哪个经典策略」+ 可读理由。"
        "趋势市→均线金叉 · 震荡+RSI 极值→RSI 反弹 · 震荡+贴轨→布林均值回归。"
        "★ 确定性映射(类比 actionable.py)· 不调 LLM · 不改 AI 管线 · 只读不下单。"
    ),
)
async def get_strategy_recommend(
    ch: ClickHouseDep,
    cn: CnSourceDep,
    us: UsSourceDep,
    crypto: CryptoSourceDep,
    hk: HkSourceDep,
    binance_futures: BinanceFuturesSourceDep,
    lang: RequestLangDep,
    symbol: str = Query(..., min_length=1, examples=["BTC/USDT", "NVDA", "600519", "BTCUSDT"]),
    market: Market = Query(...),
    period: Period = Query("1d"),
    limit: int = Query(300, ge=30, le=1000),
    instrument: Annotated[
        Instrument,
        Query(description="'spot' 现货(默认)· 'perp' USDT-M 永续(只 crypto · 拍板⑦)"),
    ] = "spot",
) -> StrategyRecommendResponse:
    klines = await _fetch_klines_for_strategy(
        ch=ch, cn=cn, us=us, crypto=crypto, hk=hk, binance_futures=binance_futures,
        symbol=symbol, market=market, period=period, instrument=instrument,
        limit=limit, lang=lang, purpose_key="analysis.purpose_recommend",
    )
    rec = recommend_strategy(klines, lang)
    logger.info(
        "[strategy-recommend] symbol=%s market=%s instrument=%s period=%s → %s",
        symbol, market, instrument, period, rec.strategy,
    )
    return StrategyRecommendResponse(
        symbol=symbol, market=market, period=period, instrument=instrument,
        recommended_strategy=rec.strategy, reason=rec.reason,
    )
