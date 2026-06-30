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
from app.services.data_sources.hk_source import AKShareHkSource
from app.services.data_sources.us_source import YFinanceUsSource


def get_clickhouse(request: Request) -> ClickHouseClient:
    return cast(ClickHouseClient, request.app.state.clickhouse)


def get_clickhouse_optional(request: Request) -> ClickHouseClient | None:
    """CH 客户端 · lifespan 未起时返回 None(不抛)· 0025 G3 webhook 用。

    Telegram webhook 在 prod 一定有 CH(lifespan 已初始化);测试不跑 lifespan,
    返回 None 不让依赖注入炸掉绑定路径的既有测试。G3 查询分支自己兜底 None。
    """
    return cast(
        "ClickHouseClient | None", getattr(request.app.state, "clickhouse", None),
    )


def get_cn_source(request: Request) -> AKShareCnSource:
    return cast(AKShareCnSource, request.app.state.cn_source)


def get_us_source(request: Request) -> YFinanceUsSource:
    return cast(YFinanceUsSource, request.app.state.us_source)


def get_crypto_source(request: Request) -> CcxtBinanceCryptoSource:
    return cast(CcxtBinanceCryptoSource, request.app.state.crypto_source)


def get_hk_source(request: Request) -> AKShareHkSource:
    """港股数据源(akshare · ADR 0034a P1-2)· 对齐 cn/us source 注入。"""
    return cast(AKShareHkSource, request.app.state.hk_source)


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
    # 刀3b-2:封禁全站立即失效点 —— banned 用户即使持有效 session,任何受保护请求即被拒。
    # 放此处 = 唯一干净的"现有 session 立即失效"位(所有端点经 CurrentUserDep)。
    if user.banned_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被停用",
        )
    return user


async def get_optional_current_user(
    token: Annotated[str | None, Depends(_oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """可选当前用户(公开端点门控用)· 无 token / 无效 / 过期 / 已封禁 → None(不抛 401/403)。

    与 get_current_user 同 session 解析逻辑,只是失败一律返 None ——
    未登录访客访问公开详情页(决策卡/策略清单门控)不被 401 破坏页面 + 伤 SEO。
    门控端点据此:None=未登录 / 返回的 User 再过 resolve_plan 判 free/pro。
    """
    if not token:
        return None
    user = await verify_session(db, token=token)
    if user is None or user.banned_at is not None:
        return None
    return user


async def get_current_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """管理员鉴权(用户管理刀1)· 🔴 admin 端点唯一安全边界,每个端点必挂。

    detail 用通用 Forbidden,不泄露「需要 admin 角色」语义(降低探测面)。
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
    return current_user


async def get_current_platinum(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """铂金用户鉴权(多账户 PR-5)· 🔴 自助端点唯一安全边界,每个端点必挂(集中=新端点不漏挂)。

    ★面向铂金用户的功能,403 文案明确「需铂金权限」(Hans 定:清楚提示 > 防探测)。
    ★越权红线:user_id 只从这里(token 反查的 current_user.id)取,端点签名绝不接受前端传入的 user_id。
    """
    if not current_user.is_platinum:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需铂金权限",
        )
    return current_user


ClickHouseDep = Annotated[ClickHouseClient, Depends(get_clickhouse)]
OptionalClickHouseDep = Annotated[
    ClickHouseClient | None, Depends(get_clickhouse_optional),
]
CnSourceDep = Annotated[AKShareCnSource, Depends(get_cn_source)]
UsSourceDep = Annotated[YFinanceUsSource, Depends(get_us_source)]
HkSourceDep = Annotated[AKShareHkSource, Depends(get_hk_source)]
CryptoSourceDep = Annotated[CcxtBinanceCryptoSource, Depends(get_crypto_source)]
BinanceFuturesSourceDep = Annotated[BinanceFuturesSource, Depends(get_binance_futures_source)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
# 可选登录(公开端点门控用 · None=未登录,不抛 401)
OptionalCurrentUserDep = Annotated[User | None, Depends(get_optional_current_user)]
AdminDep = Annotated[User, Depends(get_current_admin)]
# 铂金用户(登录 + is_platinum 门)· 多账户自助端点用(PR-5)
PlatinumDep = Annotated[User, Depends(get_current_platinum)]
