"""ClickHouseClient 集成测试。

需要 docker compose up -d 起的 midas-clickhouse(host 端口 8123)。
不可达时整组测试 skip,不让 CI 因为本地没 docker 而炸。

测试用唯一 symbol(`__test_{uuid}`)避免与正常数据冲突,不做清理。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import pytest

from app.schemas.market import Kline, SymbolMeta
from app.services.clickhouse_client import ClickHouseClient


def _test_symbol() -> str:
    return f"__test_{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def ch() -> AsyncIterator[ClickHouseClient]:
    try:
        client = await ClickHouseClient.create()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"ClickHouse 不可达,跳过集成测试:{e}")
    try:
        yield client
    finally:
        await client.close()


def _make_kline(ts: datetime, base: float = 100.0) -> Kline:
    return Kline(
        ts=ts,
        open=base,
        high=base + 5,
        low=base - 5,
        close=base + 2,
        volume=1000.0,
        amount=base * 1000.0,
    )


class TestKlineRoundTrip:
    async def test_insert_then_select(self, ch: ClickHouseClient) -> None:
        sym = _test_symbol()
        ts0 = datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)
        rows = [_make_kline(ts0 + timedelta(days=i), 100.0 + i) for i in range(5)]

        inserted = await ch.insert_kline(rows, symbol=sym, market="cn", period="1d")
        assert inserted == 5

        fetched = await ch.select_kline(symbol=sym, market="cn", period="1d", limit=10)
        assert len(fetched) == 5
        # ts 升序
        assert [k.ts for k in fetched] == [k.ts for k in rows]
        # 数值往返一致
        assert fetched[0].open == 100.0
        assert fetched[4].close == 106.0  # 104 + 2

    async def test_insert_skips_duplicates(self, ch: ClickHouseClient) -> None:
        sym = _test_symbol()
        ts0 = datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)
        rows = [_make_kline(ts0 + timedelta(days=i)) for i in range(3)]

        first = await ch.insert_kline(rows, symbol=sym, market="cn", period="1d")
        second = await ch.insert_kline(rows, symbol=sym, market="cn", period="1d")
        assert first == 3
        assert second == 0  # 全部重复

    async def test_count(self, ch: ClickHouseClient) -> None:
        sym = _test_symbol()
        ts0 = datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)
        rows = [_make_kline(ts0 + timedelta(days=i)) for i in range(7)]
        await ch.insert_kline(rows, symbol=sym, market="cn", period="1d")

        n = await ch.count_kline(symbol=sym, market="cn", period="1d")
        assert n == 7

    async def test_select_with_since(self, ch: ClickHouseClient) -> None:
        sym = _test_symbol()
        ts0 = datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)
        rows = [_make_kline(ts0 + timedelta(days=i)) for i in range(5)]
        await ch.insert_kline(rows, symbol=sym, market="cn", period="1d")

        since = ts0 + timedelta(days=2)
        fetched = await ch.select_kline(symbol=sym, market="cn", period="1d", since=since)
        assert len(fetched) == 3  # day 2/3/4


class TestSymbolMeta:
    async def test_upsert_then_search(self, ch: ClickHouseClient) -> None:
        sym = _test_symbol()
        meta = SymbolMeta(
            symbol=sym,
            market="cn",
            name=f"测试标的-{sym}",
            name_en=f"Test-{sym}",
            listed_date=date(2020, 1, 1),
            is_active=True,
            updated_at=datetime.now(tz=UTC),
        )
        n = await ch.upsert_symbol_meta([meta])
        assert n == 1

        # 用 symbol 关键字搜
        found = await ch.search_symbols(query=sym, market="cn")
        assert len(found) >= 1
        first = next(m for m in found if m.symbol == sym)
        assert first.name == meta.name
        assert first.name_en == meta.name_en
