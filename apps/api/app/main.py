import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import ccxt.async_support as ccxt_async
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as api_v1_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.redis_client import close_redis
from app.services.clickhouse_client import ClickHouseClient
from app.services.clickhouse_overview import ensure_overview_columns
from app.services.data_sources.binance_futures_source import BinanceFuturesSource
from app.services.data_sources.cn_source import AKShareCnSource
from app.services.data_sources.crypto_source import CcxtBinanceCryptoSource
from app.services.data_sources.us_source import YFinanceUsSource
from app.services.notifications.telegram_bind import register_webhook_if_configured

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """单例资源生命周期。

    启动时建立 ClickHouse client + ccxt async exchange + 三家数据源实例,
    挂到 app.state;关停时按 LIFO 顺序释放。
    """
    app.state.clickhouse = await ClickHouseClient.create()
    # ADR 0035 阶段A · reader 自保:幂等保证 overview 读依赖的 category/unit 列存在
    # (不依赖 worker worker_ready 时序 · 内部吞异常不阻断启动)
    await ensure_overview_columns(app.state.clickhouse._client)  # noqa: SLF001
    app.state.ccxt_binance = ccxt_async.binance({"enableRateLimit": True, "timeout": 30_000})
    app.state.cn_source = AKShareCnSource()
    app.state.us_source = YFinanceUsSource()
    app.state.crypto_source = CcxtBinanceCryptoSource(exchange=app.state.ccxt_binance)
    # M2-B(0017 ADR)· Binance Futures source · perp K + funding + OI + long-short
    app.state.binance_futures_source = BinanceFuturesSource()
    # 加自选 crypto 存在性校验用:后台预载 Binance 现货交易对到内存。
    # create_task → 不阻塞启动 / /health(不让上游可达性拖慢就绪)· 预载失败 fail-open。
    # 存 app.state 持引用,避免 task 被 GC。
    app.state.markets_preload_task = asyncio.create_task(
        app.state.crypto_source.ensure_markets_loaded(),
    )
    # Telegram 统一 bot(0024 v2 · M1-G G1)· 配了 token 才后台注册 webhook(不阻塞启动)
    app.state.tg_webhook_task = asyncio.create_task(
        register_webhook_if_configured(),
    )
    logger.info(
        "Lifespan startup: ClickHouse + ccxt exchange + 4 sources 就绪"
        "(cn / us / crypto-spot / crypto-perp)· crypto markets 后台预载中"
    )

    try:
        yield
    finally:
        await app.state.binance_futures_source.close()
        await app.state.ccxt_binance.close()
        await app.state.clickhouse.close()
        await close_redis()
        logger.info("Lifespan shutdown: 资源已释放")


app = FastAPI(
    title="点金 Midas API",
    description="面向 A 股 / 美股 / 加密的 AI 原生分析终端 API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "midas-api"}
