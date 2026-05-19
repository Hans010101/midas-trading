import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import ccxt.async_support as ccxt_async
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as api_v1_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.services.clickhouse_client import ClickHouseClient
from app.services.data_sources.cn_source import AKShareCnSource
from app.services.data_sources.crypto_source import CcxtBinanceCryptoSource
from app.services.data_sources.us_source import YFinanceUsSource

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """单例资源生命周期。

    启动时建立 ClickHouse client + ccxt async exchange + 三家数据源实例,
    挂到 app.state;关停时按 LIFO 顺序释放。
    """
    app.state.clickhouse = await ClickHouseClient.create()
    app.state.ccxt_binance = ccxt_async.binance({"enableRateLimit": True, "timeout": 30_000})
    app.state.cn_source = AKShareCnSource()
    app.state.us_source = YFinanceUsSource()
    app.state.crypto_source = CcxtBinanceCryptoSource(exchange=app.state.ccxt_binance)
    logger.info("Lifespan startup: ClickHouse + ccxt exchange + 3 sources 就绪")

    try:
        yield
    finally:
        await app.state.ccxt_binance.close()
        await app.state.clickhouse.close()
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
