"""FastAPI 依赖注入工厂。

从 `app.state`(lifespan 里初始化的单例)取出共享资源,
路由用 `Annotated[X, Depends(get_x)]` 注入。

`app.state` 在 Starlette 里是动态属性 bag(类型 Any),
所以 getter 里用 `cast` 让 mypy strict 满意。

`CurrentUserDep` 用于受保护路由 · 从 Bearer session token 查 DB session。
(0006 ADR 2026-05-21 回归 · JWT → DB session)。
"""

from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.services.auth import verify_session
from app.services.clickhouse_client import ClickHouseClient
from app.services.data_sources.binance_futures_source import BinanceFuturesSource
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


def get_binance_futures_source(request: Request) -> BinanceFuturesSource:
    """M2-B(0017 ADR)· perp K 线 + funding/OI/long-short 数据源。

    生命周期 lifespan 管理 · 单例 · 复用 httpx 连接池。
    """
    return cast(BinanceFuturesSource, request.app.state.binance_futures_source)


_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: Annotated[str | None, Depends(_oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """从 Bearer session token 查 DB session · 0006 ADR 2026-05-21 回归。

    旧 JWT token 已不在 session 表 · 查询不到 · 用户被迫重新登录(产品负责人指令)。
    成功路径副作用:verify_session 续 7 天 TTL + 写 last_used_at。
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未携带 Bearer session token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await verify_session(db, token=token)
    if user is None:
        # session 不存在 / 已过期 / 用户已删除 · 也涵盖旧 JWT 迁移场景
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="session 无效或已过期 · 请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


ClickHouseDep = Annotated[ClickHouseClient, Depends(get_clickhouse)]
CnSourceDep = Annotated[AKShareCnSource, Depends(get_cn_source)]
UsSourceDep = Annotated[YFinanceUsSource, Depends(get_us_source)]
CryptoSourceDep = Annotated[CcxtBinanceCryptoSource, Depends(get_crypto_source)]
BinanceFuturesSourceDep = Annotated[BinanceFuturesSource, Depends(get_binance_futures_source)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
