"""FastAPI 依赖注入工厂。

从 `app.state`(lifespan 里初始化的单例)取出共享资源,
路由用 `Annotated[X, Depends(get_x)]` 注入。

`app.state` 在 Starlette 里是动态属性 bag(类型 Any),
所以 getter 里用 `cast` 让 mypy strict 满意。
"""

from typing import Annotated, cast

from fastapi import Depends, Request

from app.services.clickhouse_client import ClickHouseClient
from app.services.data_sources.cn_source import AKShareCnSource
from app.services.data_sources.crypto_source import CcxtBinanceCryptoSource
from app.services.data_sources.us_source import YFinanceUsSource


def get_clickhouse(request: Request) -> ClickHouseClient:
    return cast(ClickHouseClient, request.app.state.clickhouse)


def get_cn_source(request: Request) -> AKShareCnSource:
    return cast(AKShareCnSource, request.app.state.cn_source)


def get_us_source(request: Request) -> YFinanceUsSource:
    return cast(YFinanceUsSource, request.app.state.us_source)


def get_crypto_source(request: Request) -> CcxtBinanceCryptoSource:
    return cast(CcxtBinanceCryptoSource, request.app.state.crypto_source)


ClickHouseDep = Annotated[ClickHouseClient, Depends(get_clickhouse)]
CnSourceDep = Annotated[AKShareCnSource, Depends(get_cn_source)]
UsSourceDep = Annotated[YFinanceUsSource, Depends(get_us_source)]
CryptoSourceDep = Annotated[CcxtBinanceCryptoSource, Depends(get_crypto_source)]
