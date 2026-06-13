"""盘口深度采集(沙盘三期第二批 · 刀1)· pytest。

🔴 红线:全程只读盘口 · 校验采集解析 + 只 GET(无 sign/trade)· 采集层合法写 CH。

覆盖:
- fetch_depth 解析(httpx MockTransport · 不打外网):top-10 定长 / 不足补 0 / 截断多余 / 脏档降级
- ★ adapter 只 GET 断言:只命中 GET /fapi/v1/depth · 无 POST/sign/trade
- insert_depth ClickHouse 往返(集成 · CH 不可达 skip · 自建表)

注:depth_scan Celery 任务注册不在此单测 —— api 测试套件无法跨包 import apps.worker
(monorepo 分包),与现有 6 个 ingest 任务一致(它们也不在 api 套件测注册);
任务 @shared_task 在 celery_app.py 已 import 的 crypto_metrics_ingest 模块内,worker 启动自动注册。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest

from app.schemas.crypto import DEPTH_LEVELS, OrderbookDepth
from app.services.clickhouse_crypto import insert_depth, select_latest_depth
from app.services.data_sources.binance_futures_source import BinanceFuturesSource

# ============================================================================
# 1 · fetch_depth 解析 + 只 GET 断言(httpx MockTransport · 不打外网)
# ============================================================================

# 上游 fapi/v1/depth 形态:bids 价降序 / asks 价升序 · 字符串二元组
_DEPTH_PAYLOAD = {
    "lastUpdateId": 123456,
    "E": 1748073600000,
    "T": 1748073600500,
    "bids": [[f"{30000 - i}", f"{1.5 + i}"] for i in range(12)],  # 12 档 · 应截断到 10
    "asks": [[f"{30001 + i}", f"{2.0 + i}"] for i in range(3)],   # 3 档 · 应补到 10
}


@pytest.mark.asyncio
async def test_fetch_depth_parses_fixed_levels_and_only_gets() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        # ★ 红线:只 GET · /fapi/v1/depth · 永不 POST/sign/trade
        seen.append(request.method)
        assert request.method == "GET"
        assert request.url.path == "/fapi/v1/depth"
        assert request.url.params.get("symbol") == "BTCUSDT"
        return httpx.Response(200, json=_DEPTH_PAYLOAD)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    src = BinanceFuturesSource(client=client)
    try:
        depth = await src.fetch_depth("BTCUSDT", limit=DEPTH_LEVELS)
    finally:
        await client.aclose()

    assert seen == ["GET"]  # 只发了一个 GET
    assert depth.symbol == "BTCUSDT"
    assert depth.ts.tzinfo is not None  # tz-aware UTC(0002 教训)
    # bids 截断到 10 档 · 价降序首档 30000
    assert len(depth.bids) == DEPTH_LEVELS
    assert depth.bids[0] == (30000.0, 1.5)
    # asks 只 3 档 · 补到 10(后 7 档 (0,0))
    assert len(depth.asks) == DEPTH_LEVELS
    assert depth.asks[0] == (30001.0, 2.0)
    assert depth.asks[3:] == ((0.0, 0.0),) * (DEPTH_LEVELS - 3)


@pytest.mark.asyncio
async def test_fetch_depth_dirty_levels_degrade_to_zero() -> None:
    """脏档(缺字段/非数)降级 (0,0) · 不抛(整轮不因一档崩)。"""
    payload = {
        "T": 1748073600500,
        "bids": [["30000", "1.5"], ["bad"], ["29998", "x"]],  # 第2/3档脏
        "asks": [],
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    src = BinanceFuturesSource(client=client)
    try:
        depth = await src.fetch_depth("ETHUSDT")
    finally:
        await client.aclose()

    assert depth.bids[0] == (30000.0, 1.5)
    assert depth.bids[1] == (0.0, 0.0)  # ["bad"] → 降级
    assert depth.bids[2] == (0.0, 0.0)  # qty "x" 非数 → 降级
    assert depth.asks == ((0.0, 0.0),) * DEPTH_LEVELS  # 空 asks 全补 0


# ============================================================================
# 2 · ClickHouse 往返(集成 · CH 不可达时 skip · 自建表 · 与 init.sql 一致)
# ============================================================================

_CREATE_DEPTH_DDL = """
CREATE TABLE IF NOT EXISTS crypto_orderbook_depth (
    symbol String,
    ts DateTime,
    bid1_price Float64, bid2_price Float64, bid3_price Float64, bid4_price Float64, bid5_price Float64,
    bid6_price Float64, bid7_price Float64, bid8_price Float64, bid9_price Float64, bid10_price Float64,
    bid1_qty Float64, bid2_qty Float64, bid3_qty Float64, bid4_qty Float64, bid5_qty Float64,
    bid6_qty Float64, bid7_qty Float64, bid8_qty Float64, bid9_qty Float64, bid10_qty Float64,
    ask1_price Float64, ask2_price Float64, ask3_price Float64, ask4_price Float64, ask5_price Float64,
    ask6_price Float64, ask7_price Float64, ask8_price Float64, ask9_price Float64, ask10_price Float64,
    ask1_qty Float64, ask2_qty Float64, ask3_qty Float64, ask4_qty Float64, ask5_qty Float64,
    ask6_qty Float64, ask7_qty Float64, ask8_qty Float64, ask9_qty Float64, ask10_qty Float64,
    ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (symbol, ts)
TTL ingested_at + INTERVAL 7 DAY
SETTINGS index_granularity = 8192
"""


@pytest.fixture
async def ch_raw():  # noqa: ANN201
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
    await client.command(_CREATE_DEPTH_DDL)
    try:
        yield client
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_depth_round_trip(ch_raw) -> None:  # noqa: ANN001
    sym = f"__TEST{uuid.uuid4().hex[:6].upper()}USDT"
    ts = datetime(2026, 6, 13, 8, 0, 0, tzinfo=UTC)
    bids = tuple((30000.0 - i, 1.0 + i) for i in range(DEPTH_LEVELS))
    asks = tuple((30001.0 + i, 2.0 + i) for i in range(DEPTH_LEVELS))
    item = OrderbookDepth(symbol=sym, ts=ts, bids=bids, asks=asks)

    n = await insert_depth(ch_raw, [item])
    assert n == 1

    # flatten 列回读:首档 bid/ask price/qty 落库正确
    res = await ch_raw.query(
        "SELECT bid1_price, bid1_qty, ask1_price, ask1_qty, bid10_price, ask10_qty "
        "FROM crypto_orderbook_depth FINAL WHERE symbol = {s:String}",
        parameters={"s": sym},
    )
    assert res.result_rows
    bid1_price, bid1_qty, ask1_price, ask1_qty, bid10_price, ask10_qty = res.result_rows[0]
    assert bid1_price == 30000.0
    assert bid1_qty == 1.0
    assert ask1_price == 30001.0
    assert ask1_qty == 2.0
    assert bid10_price == 30000.0 - 9
    assert ask10_qty == 2.0 + 9


@pytest.mark.asyncio
async def test_insert_depth_empty_noop(ch_raw) -> None:  # noqa: ANN001
    assert await insert_depth(ch_raw, []) == 0


@pytest.mark.asyncio
async def test_select_latest_depth_takes_newest_ts(ch_raw) -> None:  # noqa: ANN001
    """刀2 读层:同 symbol 多条不同 ts → select_latest_depth 取最新一条(ORDER BY ts DESC)。"""
    sym = f"__TEST{uuid.uuid4().hex[:6].upper()}USDT"
    old = OrderbookDepth(
        symbol=sym, ts=datetime(2026, 6, 14, 0, 0, 0, tzinfo=UTC),
        bids=tuple((100.0, 1.0) for _ in range(DEPTH_LEVELS)),
        asks=tuple((101.0, 1.0) for _ in range(DEPTH_LEVELS)),
    )
    new = OrderbookDepth(
        symbol=sym, ts=datetime(2026, 6, 14, 0, 5, 0, tzinfo=UTC),  # 5min 后的新快照
        bids=tuple((200.0, 2.0) for _ in range(DEPTH_LEVELS)),
        asks=tuple((202.0, 2.0) for _ in range(DEPTH_LEVELS)),
    )
    await insert_depth(ch_raw, [old, new])

    latest = await select_latest_depth(ch_raw, sym)
    assert latest is not None
    assert latest.ts == new.ts  # 取最新 ts(秒级 UTC 往返)
    assert latest.bids[0] == (200.0, 2.0)  # 还原新快照的盘口
    assert latest.asks[0] == (202.0, 2.0)
    assert len(latest.bids) == DEPTH_LEVELS
    assert len(latest.asks) == DEPTH_LEVELS


@pytest.mark.asyncio
async def test_select_latest_depth_missing_symbol_none(ch_raw) -> None:  # noqa: ANN001
    """未采到该 symbol → None(如实留白,不伪造)。"""
    assert await select_latest_depth(ch_raw, "__NOPE_DEPTH_USDT__") is None
