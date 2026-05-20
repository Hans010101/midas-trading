"""Pytest 全局 fixtures · 测试基建。

策略:
- 测试用 midas_test 数据库(独立 schema,跟开发库 midas 隔离)
- alembic 已在 docker exec 阶段迁移到 head
- 每个 test 用 engine.connect → begin transaction → SAVEPOINT 嵌套 → 结束 rollback
  · 测试之间数据完全隔离,不留下任何 row
- FastAPI ASGI 测试用 httpx.AsyncClient + ASGITransport · 不走真实 HTTP
- get_db 依赖被覆盖为 yield 同一个 test 事务的 session
- 不跑 lifespan(app.state 不初始化):auth + watchlist 不需要 CH / ccxt / data sources

在导入 app.* 之前注入测试用环境变量。conftest.py 由 pytest 在收集测试前最先加载。
"""

from __future__ import annotations

import os

# ⚠ 必须在 import app.* 之前设置 env(配置 Settings 会读)
os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://midas:midas_dev@localhost:5432/midas_test"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production")
os.environ.setdefault("CLICKHOUSE_USER", "midas")
os.environ.setdefault("CLICKHOUSE_PASSWORD", "midas_dev")

from collections.abc import AsyncIterator  # noqa: E402

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.database import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Async engine 指向 midas_test · 每个 test 独立 engine + NullPool。

    用 NullPool 避免连接复用,杜绝 pytest_asyncio 默认每 test 新 event loop
    跟 asyncpg connection.loop 不匹配的「got Future attached to a different loop」。
    """
    eng = create_async_engine(
        os.environ["DATABASE_URL"], future=True, poolclass=NullPool,
    )
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncIterator[AsyncSession]:
    """每个 test 一个 session,基于连接级事务 + SAVEPOINT。

    模式参考 SQLAlchemy 官方文档「Joining a Session into an External Transaction」。
    测试结束后 rollback 外层事务 · 数据完全清理。
    """
    connection: AsyncConnection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)

    # 开第一个 savepoint
    await connection.begin_nested()

    # 每次 session.commit() / rollback 会结束当前 savepoint;
    # 在它结束时自动开下一个,让测试代码可以无感地 commit
    @event.listens_for(session.sync_session, "after_transaction_end")
    def _restart_savepoint(_sync_session, trans):  # noqa: ANN001, ANN202
        if trans.nested and not trans._parent.nested:
            # 在 sync 上下文里用 sync API 重开 savepoint
            sync_conn = connection.sync_connection
            assert sync_conn is not None  # noqa: S101
            sync_conn.begin_nested()

    try:
        yield session
    finally:
        await session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """ASGI 测试 client · get_db 被覆盖为返回测试 session。

    不走 lifespan,所以 app.state.clickhouse 等不会初始化。
    auth / watchlist 路由不需要这些,可以安全跑。
    """

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c

    app.dependency_overrides.clear()
