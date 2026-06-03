"""A股全市场搜索 helper 集成测试(select_spot_search · 真 ClickHouse)。

照搬 test_premium_index 的真 CH fixture 范式(CH 不可达 → skip · 幂等建表)。
★ 隔离:测试行写【远未来 ts(2099)】→ 它即 max(ts),搜索只命中本测试数据,不混入真实快照;
   seed 前 + teardown 都用 ALTER TABLE DELETE(mutations_sync=1 同步)清掉,绝不污染真实榜单
   (select_latest_spot 也是按 max(ts) 取,若残留 2099 行会让真实榜单看到测试数据 → 必须同步清)。
★ 红线:只读搜索逻辑 + 临时写测试快照,永不碰下单/撮合。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.schemas.cn_market import CnSpotRow
from app.services.clickhouse_cn_market import insert_spot_snapshot, select_spot_search

# 远未来 ts → 必为 max(ts),隔离真实快照(真实数据是当下时点)
_TEST_TS = datetime(2099, 6, 1, 1, 30, 0, tzinfo=UTC)

# cn_spot_snapshot 建表(对齐 docker/clickhouse-init.sql · 本地兜底,CI 由 init.sql 建)
_CREATE_CN_SPOT_DDL = """
CREATE TABLE IF NOT EXISTS cn_spot_snapshot (
    symbol String, name String, ts DateTime,
    last_price Float64, change_pct Float64, change_amount Float64,
    amount Float64, volume Float64, ingested_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toDate(ts) ORDER BY (ts, symbol)
TTL ingested_at + INTERVAL 2 DAY SETTINGS index_granularity = 8192
"""

# 成交额降序:茅台 9e9 > 平安 8e9 > 招商 7e9 > 工商 6e9 > TCL 1e9
_SEED = [
    CnSpotRow(symbol="600519", name="贵州茅台", last_price=1700.0, change_pct=1.5,
              change_amount=25.0, amount=9.0e9, volume=1.0e6),
    CnSpotRow(symbol="000001", name="平安银行", last_price=12.0, change_pct=-0.5,
              change_amount=-0.06, amount=8.0e9, volume=5.0e8),
    CnSpotRow(symbol="600036", name="招商银行", last_price=38.0, change_pct=0.8,
              change_amount=0.30, amount=7.0e9, volume=2.0e8),
    CnSpotRow(symbol="601398", name="工商银行", last_price=5.5, change_pct=0.2,
              change_amount=0.01, amount=6.0e9, volume=3.0e8),
    CnSpotRow(symbol="000100", name="TCL科技", last_price=5.0, change_pct=2.0,
              change_amount=0.10, amount=1.0e9, volume=4.0e8),
]

_DELETE_TEST_ROWS = "ALTER TABLE cn_spot_snapshot DELETE WHERE ts = %(ts)s"
_SYNC = {"mutations_sync": 1}  # 同步等 mutation 完成 · 清理可靠


@pytest.fixture
async def seeded_ch():  # noqa: ANN201
    """真 CH client + 播 5 行测试快照(ts=2099)· teardown 同步清掉。"""
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
    await client.command(_CREATE_CN_SPOT_DDL)
    # seed 前先同步清残留(防上次 run 的 2099 行未清导致 ReplacingMergeTree 重复行)
    await client.command(_DELETE_TEST_ROWS, parameters={"ts": _TEST_TS}, settings=_SYNC)
    await insert_spot_snapshot(client, _SEED, ts=_TEST_TS)
    try:
        yield client
    finally:
        await client.command(_DELETE_TEST_ROWS, parameters={"ts": _TEST_TS}, settings=_SYNC)
        await client.close()


@pytest.mark.asyncio
async def test_search_hit_by_symbol(seeded_ch) -> None:  # noqa: ANN001
    """命中代码:搜 '600519' → 贵州茅台。"""
    rows = await select_spot_search(seeded_ch, query="600519", limit=30)
    assert [r.symbol for r in rows] == ["600519"]
    assert rows[0].name == "贵州茅台"


@pytest.mark.asyncio
async def test_search_hit_by_chinese_name(seeded_ch) -> None:  # noqa: ANN001
    """命中中文名:搜 '茅台' → 600519。"""
    rows = await select_spot_search(seeded_ch, query="茅台", limit=30)
    assert [r.symbol for r in rows] == ["600519"]


@pytest.mark.asyncio
async def test_search_chinese_name_multi_hit_amount_desc(seeded_ch) -> None:  # noqa: ANN001
    """多命中 + 成交额降序:搜 '银行' → 平安(8e9)> 招商(7e9)> 工商(6e9)。"""
    rows = await select_spot_search(seeded_ch, query="银行", limit=30)
    assert [r.symbol for r in rows] == ["000001", "600036", "601398"]
    # 成交额严格降序
    amounts = [r.amount for r in rows]
    assert amounts == sorted(amounts, reverse=True)


@pytest.mark.asyncio
async def test_search_case_insensitive(seeded_ch) -> None:  # noqa: ANN001
    """大小写不敏感:小写 'tcl' 命中 'TCL科技'(positionCaseInsensitive)。"""
    lower = await select_spot_search(seeded_ch, query="tcl", limit=30)
    upper = await select_spot_search(seeded_ch, query="TCL", limit=30)
    assert [r.symbol for r in lower] == ["000100"]
    assert [r.symbol for r in upper] == ["000100"]


@pytest.mark.asyncio
async def test_search_respects_limit(seeded_ch) -> None:  # noqa: ANN001
    """限量:'银行' 有 3 个,limit=2 只返 2(且仍是成交额前 2)。"""
    rows = await select_spot_search(seeded_ch, query="银行", limit=2)
    assert len(rows) == 2
    assert [r.symbol for r in rows] == ["000001", "600036"]


@pytest.mark.asyncio
async def test_search_no_match_returns_empty(seeded_ch) -> None:  # noqa: ANN001
    """无命中:搜不存在的串 → 空列表。"""
    rows = await select_spot_search(seeded_ch, query="不存在的板块XYZ", limit=30)
    assert rows == []
