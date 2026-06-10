"""结构快照端点 pytest · GET /api/v1/structure/snapshot/{symbol}(authed 401 / 200 形状)。

service 层已单测(test_structure_snapshot)· 这里 mock get_structure_snapshot,只验门禁与序列化。
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_clickhouse
from app.main import app
from app.schemas.structure import StructureFactor, StructureSnapshot
from app.services.auth import issue_session
from tests.factories import make_user

_TS = datetime(2026, 6, 10, 8, 0, tzinfo=UTC)


def _canned_snapshot() -> StructureSnapshot:
    factor = StructureFactor(value={"latest": 2.0, "avg_24h": 1.5}, window="24h", asof=_TS)
    return StructureSnapshot(
        symbol="BTCUSDT", generated_at=_TS,
        account_long_short=factor, position_long_short=factor, taker_flow=factor,
        open_interest=None,  # 单因子缺失 → null 序列化
        funding_rate=StructureFactor(
            value={"latest": 0.0001, "avg_7d": 0.0001, "max_7d": 0.0002, "min_7d": 0.0},
            window="7d", asof=_TS,
        ),
        basis=None,
        sentiment=StructureFactor(
            value={"fear_greed": 30.0, "btc_dominance": 54.3},
            window="latest", asof=_TS, text="Fear",
        ),
    )


@pytest.mark.asyncio
async def test_snapshot_unauthenticated_401(client: AsyncClient) -> None:
    # CH 依赖也要覆盖:FastAPI 先解析 ch 依赖再走鉴权 · 测试不跑 lifespan,
    # 不覆盖会在 401 之前炸 app.state.clickhouse(CI 实测教训)。
    app.dependency_overrides[get_clickhouse] = lambda: SimpleNamespace(_client=object())
    r = await client.get("/api/v1/structure/snapshot/BTCUSDT")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_snapshot_authed_200_shape(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # CH 依赖给假 holder(端点取 ch._client)· service 整体 mock(已单测)
    app.dependency_overrides[get_clickhouse] = lambda: SimpleNamespace(_client=object())

    async def fake_get(client: Any, symbol: str) -> StructureSnapshot:  # noqa: ARG001
        return _canned_snapshot()

    monkeypatch.setattr("app.api.v1.structure.get_structure_snapshot", fake_get)

    user = await make_user(db_session)
    token = await issue_session(db_session, user_id=user.id)
    await db_session.commit()

    r = await client.get(
        "/api/v1/structure/snapshot/btcusdt",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "BTCUSDT"
    assert body["account_long_short"]["window"] == "24h"
    assert body["account_long_short"]["value"]["latest"] == 2.0
    assert body["open_interest"] is None  # 缺失因子 = null,不是缺 key
    assert body["funding_rate"]["window"] == "7d"
    assert body["sentiment"]["text"] == "Fear"
