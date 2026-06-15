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

    async def test_select_first_kline_at_or_after(self, ch: ClickHouseClient) -> None:
        """0036 批次乙 · reflection 回填用 · 取 ts >= 给定时刻的【最早一根】。

        ★ 验证语义精确(ASC LIMIT 1)· 不像 select_kline 的 DESC LIMIT 取最新根。
        """
        sym = _test_symbol()
        ts0 = datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)
        # day0..day9 · close = 100+i +2(_make_kline base+2)
        rows = [_make_kline(ts0 + timedelta(days=i), 100.0 + i) for i in range(10)]
        await ch.insert_kline(rows, symbol=sym, market="cn", period="1d")

        # 恰好落在某根上(day3 · close=105)
        k = await ch.select_first_kline_at_or_after(
            symbol=sym, market="cn", period="1d", at_or_after=ts0 + timedelta(days=3),
        )
        assert k is not None
        assert k.ts == ts0 + timedelta(days=3)
        assert k.close == 105.0  # 103 + 2

        # 落在两根之间(day3 12:00)→ 取下一根 day4(首个 >= 门槛)· 非最新根
        k2 = await ch.select_first_kline_at_or_after(
            symbol=sym, market="cn", period="1d",
            at_or_after=ts0 + timedelta(days=3, hours=12),
        )
        assert k2 is not None
        assert k2.ts == ts0 + timedelta(days=4)
        assert k2.close == 106.0  # 104 + 2 · 证明取的是首根而非 day9 最新根

        # 门槛超过最后一根 → None(horizon 未到 · CH 无数据)
        k3 = await ch.select_first_kline_at_or_after(
            symbol=sym, market="cn", period="1d", at_or_after=ts0 + timedelta(days=99),
        )
        assert k3 is None


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

    async def test_upsert_with_listed_date_none(self, ch: ClickHouseClient) -> None:
        """0002 翻车 6 回归:listed_date=None 时不能让 clickhouse-connect 翻车。"""
        sym = _test_symbol()
        meta = SymbolMeta(
            symbol=sym,
            market="us",
            name="No Listed Date Co",
            name_en="No Listed Date Co",
            listed_date=None,
            is_active=True,
            updated_at=datetime.now(tz=UTC),
        )
        n = await ch.upsert_symbol_meta([meta])
        assert n == 1

        # 读出时哨兵翻译回 None
        found = await ch.search_symbols(query=sym, market="us")
        first = next(m for m in found if m.symbol == sym)
        assert first.listed_date is None


# ── 本刀:已收盘根过滤(方案 C · 15m 采集只写已收盘)─────────────────────────


def test_drop_unclosed_klines_drops_current_window():
    """drop_unclosed_klines:当前 period 窗口的未收盘根被丢、已收盘根保留 · 未知 period 原样(纯函数·无需CH)。"""
    from app.services.clickhouse_client import drop_unclosed_klines

    secs = 900  # 15m
    now_epoch = int(datetime.now(tz=UTC).timestamp())
    boundary = datetime.fromtimestamp(now_epoch - now_epoch % secs, tz=UTC)
    current = _make_kline(boundary)                         # ts==窗口起点 → 当前未收盘根
    closed = _make_kline(boundary - timedelta(minutes=15))  # 上一根 → 已收盘
    older = _make_kline(boundary - timedelta(hours=3))      # 更早 → 已收盘

    out = drop_unclosed_klines([older, closed, current], "15m")
    out_ts = {k.ts for k in out}
    assert boundary not in out_ts                              # ★未收盘根被丢
    assert (boundary - timedelta(minutes=15)) in out_ts        # 已收盘根保留
    assert (boundary - timedelta(hours=3)) in out_ts
    # 未知 period → 保守原样返回(不丢)
    assert drop_unclosed_klines([current], "nope") == [current]
