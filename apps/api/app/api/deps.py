"""FastAPI 依赖注入工厂。

从 `app.state`(lifespan 里初始化的单例)取出共享资源,
路由用 `Annotated[X, Depends(get_x)]` 注入。

`app.state` 在 Starlette 里是动态属性 bag(类型 Any),
所以 getter 里用 `cast` 让 mypy strict 满意。

`CurrentUserDep` 用于受保护路由 · 从 Bearer JWT 提取并验证。
"""

from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.services.auth import decode_access_token, find_user_by_id
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


_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: Annotated[str | None, Depends(_oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未携带 Bearer JWT",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = decode_access_token(token)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"JWT 无效:{e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    user = await find_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已删除",
        )
    return user


ClickHouseDep = Annotated[ClickHouseClient, Depends(get_clickhouse)]
CnSourceDep = Annotated[AKShareCnSource, Depends(get_cn_source)]
UsSourceDep = Annotated[YFinanceUsSource, Depends(get_us_source)]
CryptoSourceDep = Annotated[CcxtBinanceCryptoSource, Depends(get_crypto_source)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
