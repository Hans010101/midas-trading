"""Premium Index(真标记价)· M2-C.2.1 · ADR-0020 pytest。

🔴 红线:全程只读行情 · 这里校验采集解析 + 价源切换逻辑,绝不接真实交易。

覆盖:
- fetch_premium_index 解析 + 过滤(交割合约 / 非法价 / 缺字段 跳过)· httpx MockTransport
- make_perp_mark_price_fetcher 价源切换:真 mark price 优先 · perp ticker 兜底 · 都缺返 None
  (M2-C.1 零回归的关键保证 —— 不依赖 CH,monkeypatch 两个 select)
- ClickHouse 往返:insert → select_premium_index_marks / select_latest_premium_index
  (集成 · CH 不可达时 skip · 自建表保证自包含)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from app.schemas.crypto import PremiumIndex, Ticker24h
from app.services.clickhouse_crypto import (
    insert_premium_index,
    select_latest_premium_index,
    select_premium_index_marks,
)
from app.services.data_sources.binance_futures_source import BinanceFuturesSource

# ============================================================================
# 1 · fetch_premium_index 解析 + 过滤(httpx MockTransport · 不打外网)
# ============================================================================

_PREMIUM_PAYLOAD = [
    # 正常 USDT 永续
    {
        "symbol": "BTCUSDT", "markPrice": "30000.5", "indexPrice": "29999.0",
        "lastFundingRate": "0.0001", "nextFundingTime": 1900000000000, "time": 1748073600000,
    },
    {
        "symbol": "ETHUSDT", "markPrice": "2000.0", "indexPrice": "1999.5",
        "lastFundingRate": "-0.0002", "nextFundingTime": 1900000000000, "time": 1748073600000,
    },
    # 交割合约(含 '_')· 非永续 · 跳过
    {
        "symbol": "BTCUSDT_240628", "markPrice": "30100.0", "indexPrice": "30050.0",
        "lastFundingRate": "0", "nextFundingTime": 1900000000000, "time": 1748073600000,
    },
    # mark<=0(下架/异常)· 跳过
    {
        "symbol": "BADUSDT", "markPrice": "0", "indexPrice": "100.0",
        "lastFundingRate": "0", "nextFundingTime": 1900000000000, "time": 1748073600000,
    },
    # 缺 nextFundingTime · 跳过
    {
        "symbol": "NOFUTUSDT", "markPrice": "5.0", "indexPrice": "5.0",
        "lastFundingRate": "0", "time": 1748073600000,
    },
]


@pytest.mark.asyncio
async def test_fetch_premium_index_parses_and_filters() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/fapi/v1/premiumIndex"
        return httpx.Response(200, json=_PREMIUM_PAYLOAD)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    src = BinanceFuturesSource(client=client)
    try:
        items = await src.fetch_premium_index()
    finally:
        await client.aclose()

    by = {i.symbol: i for i in items}
    # 只留两个正常永续 · 交割/非法/缺字段全部被过滤
    assert set(by) == {"BTCUSDT", "ETHUSDT"}
    assert by["BTCUSDT"].mark_price == 30000.5
    assert by["BTCUSDT"].index_price == 29999.0
    assert by["BTCUSDT"].last_funding_rate == 0.0001
    assert by["ETHUSDT"].last_funding_rate == -0.0002
    # funding_interval_hours 默认 8(per-symbol 周期 M2-C.2.2 才回源)
    assert by["BTCUSDT"].funding_interval_hours == 8
    # ts / next_funding_time 是 tz-aware UTC
    assert by["BTCUSDT"].ts.tzinfo is not None
    assert by["BTCUSDT"].next_funding_time.tzinfo is not None


# ============================================================================
# 2 · 价源切换 · make_perp_mark_price_fetcher(mark 优先 + ticker 兜底 + None)
#     M2-C.1 零回归的关键 —— monkeypatch 两个 select · 不依赖 CH
# ============================================================================


def _fake_ch() -> SimpleNamespace:
    """fetcher 只用 ch._client · 给个占位即可(patched select 忽略它)。"""
    return SimpleNamespace(_client=object())


@pytest.mark.asyncio
async def test_mark_fetcher_prefers_premium_mark(monkeypatch: pytest.MonkeyPatch) -> None:
    """premium_index 有 mark → 用真 mark price · 绝不再查 ticker。"""
    from app.api.v1 import perp

    async def fake_marks(_client: object, symbols: list[str]) -> dict[str, Decimal]:
        assert symbols == ["BTCUSDT"]
        return {"BTCUSDT": Decimal("31000")}

    async def fake_tickers(*_a: object, **_k: object) -> dict[str, Ticker24h]:
        raise AssertionError("mark 存在时不应回退查 ticker")

    monkeypatch.setattr(perp, "select_premium_index_marks", fake_marks)
    monkeypatch.setattr(perp, "select_tickers_by_symbols", fake_tickers)

    fetcher = perp.make_perp_mark_price_fetcher(_fake_ch())  # type: ignore[arg-type]
    assert await fetcher("BTCUSDT") == Decimal("31000")


@pytest.mark.asyncio
async def test_mark_fetcher_falls_back_to_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    """premium_index 缺该 symbol → 退回 perp ticker 最新价(零回归)。"""
    from app.api.v1 import perp

    async def fake_marks(_client: object, _symbols: list[str]) -> dict[str, Decimal]:
        return {}

    async def fake_tickers(
        _client: object, *, instrument: str, symbols: list[str],
    ) -> dict[str, Ticker24h]:
        assert instrument == "perp"
        assert symbols == ["BTC/USDT"]  # 兜底转 ccxt 风格
        return {
            "BTC/USDT": Ticker24h(
                symbol="BTC/USDT", instrument="perp", ts=datetime.now(UTC),
                last_price=29500.0, change_pct_24h=0.0,
                high_24h=1.0, low_24h=1.0, volume_24h=0.0, quote_volume_24h=0.0,
            ),
        }

    monkeypatch.setattr(perp, "select_premium_index_marks", fake_marks)
    monkeypatch.setattr(perp, "select_tickers_by_symbols", fake_tickers)

    fetcher = perp.make_perp_mark_price_fetcher(_fake_ch())  # type: ignore[arg-type]
    assert await fetcher("BTCUSDT") == Decimal("29500.0")


@pytest.mark.asyncio
async def test_mark_fetcher_none_when_both_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """premium + ticker 都缺 → None(撮合拒单 / 强平跳过不误杀)。"""
    from app.api.v1 import perp

    async def fake_marks(_client: object, _symbols: list[str]) -> dict[str, Decimal]:
        return {}

    async def fake_tickers(*_a: object, **_k: object) -> dict[str, Ticker24h]:
        return {}

    monkeypatch.setattr(perp, "select_premium_index_marks", fake_marks)
    monkeypatch.setattr(perp, "select_tickers_by_symbols", fake_tickers)

    fetcher = perp.make_perp_mark_price_fetcher(_fake_ch())  # type: ignore[arg-type]
    assert await fetcher("BTCUSDT") is None


# ============================================================================
# 3 · ClickHouse 往返(集成 · CH 不可达时 skip · 自建表)
# ============================================================================

# 与 docker/clickhouse-init.sql / apps/worker/ch_schema.py 一致 · 测试自建表保证自包含
_CREATE_PREMIUM_INDEX_DDL = """
CREATE TABLE IF NOT EXISTS crypto_premium_index (
    symbol String,
    ts DateTime,
    mark_price Float64,
    index_price Float64,
    last_funding_rate Float64,
    next_funding_time DateTime,
    funding_interval_hours UInt8 DEFAULT 8,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
TTL ingested_at + INTERVAL 7 DAY
SETTINGS index_granularity = 8192
"""


@pytest.fixture
async def ch_raw():  # noqa: ANN201
    """raw clickhouse_connect async client(session_timezone=UTC · 跟 worker 一致)。"""
    import clickhouse_connect

    from app.core.config import settings

    try:
        client = await clickhouse_connect.get_async_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
            database=settings.clickhouse_database,
            settings={"session_timezone": "UTC"},
        )
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"ClickHouse 不可达,跳过集成测试:{e}")
    await client.command(_CREATE_PREMIUM_INDEX_DDL)  # 幂等自建表
    try:
        yield client
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_premium_index_round_trip(ch_raw) -> None:  # noqa: ANN001
    sym = f"__TEST{uuid.uuid4().hex[:6].upper()}USDT"
    ts = datetime(2026, 5, 24, 8, 0, 0, tzinfo=UTC)
    nft = datetime(2026, 5, 24, 16, 0, 0, tzinfo=UTC)
    item = PremiumIndex(
        symbol=sym, ts=ts, mark_price=30000.5, index_price=29999.0,
        last_funding_rate=0.0001, next_funding_time=nft, funding_interval_hours=8,
    )

    n = await insert_premium_index(ch_raw, [item])
    assert n == 1

    # select_premium_index_marks → 撮合/强平价源 · Decimal mark
    marks = await select_premium_index_marks(ch_raw, [sym])
    assert marks[sym] == Decimal("30000.5")

    # select_latest_premium_index → futures/info 用 · 全字段 + tz-aware UTC 往返(0002 教训)
    latest = await select_latest_premium_index(ch_raw, sym)
    assert latest is not None
    assert latest.symbol == sym
    assert latest.mark_price == 30000.5
    assert latest.index_price == 29999.0
    assert latest.next_funding_time == nft  # 秒级 UTC 精确往返
    assert latest.funding_interval_hours == 8


@pytest.mark.asyncio
async def test_premium_index_missing_symbol(ch_raw) -> None:  # noqa: ANN001
    assert await select_premium_index_marks(ch_raw, ["__NOPE_USDT__"]) == {}
    assert await select_latest_premium_index(ch_raw, "__NOPE_USDT__") is None
