"""bot 核心查询层 pytest · 0025 M1-G G3。

query_symbol / query_watchlist / query_positions —— 只读 CH(用 FakeCH 替身)+ PG(真库)。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.perp import MarginMode, PerpSide, VirtualPerpPosition
from app.models.virtual import PositionSide, VirtualPosition
from app.services.bot import query as q
from tests.factories import make_user, make_virtual_account, make_watchlist_item


class _FakeCH:
    """最小 ClickHouseClient 替身 · 只实现 select_kline + _client(crypto 衍生取不到→None)。"""

    def __init__(self, klines: list[Any] | None = None) -> None:
        self._klines = klines or []
        self._client = object()  # crypto 衍生 select_* 拿它会失败 → fail-soft None

    async def select_kline(self, **_kwargs: Any) -> list[Any]:
        return list(self._klines)


def _bar(close: float, volume: float) -> SimpleNamespace:
    return SimpleNamespace(close=Decimal(str(close)), volume=Decimal(str(volume)))


@pytest.mark.asyncio
async def test_query_symbol_no_data_returns_none():
    quote = await q.query_symbol(_FakeCH([]), "us", "NVDA")  # type: ignore[arg-type]
    assert quote is None


@pytest.mark.asyncio
async def test_query_symbol_price_and_change():
    ch = _FakeCH([_bar(100.0, 1000), _bar(110.0, 2000)])
    quote = await q.query_symbol(ch, "us", "NVDA")  # type: ignore[arg-type]
    assert quote is not None
    assert quote.price == 110.0
    assert quote.volume == 2000.0
    assert quote.change_pct == pytest.approx(10.0)  # (110-100)/100
    assert quote.currency == "USD"
    # 非 crypto · 衍生字段全 None
    assert quote.funding_rate is None
    assert quote.basis_pct is None


@pytest.mark.asyncio
async def test_query_symbol_crypto_extras_failsoft():
    """crypto 标的:K 线有价,衍生指标 FakeCH 取不到 → 各 None(不抛)。"""
    ch = _FakeCH([_bar(60000.0, 5), _bar(61200.0, 6)])
    quote = await q.query_symbol(ch, "crypto", "BTC/USDT")  # type: ignore[arg-type]
    assert quote is not None
    assert quote.price == 61200.0
    assert quote.currency == "USDT"
    assert quote.funding_rate is None
    assert quote.open_interest_usd is None
    assert quote.long_short_ratio is None
    assert quote.basis_pct is None


@pytest.mark.asyncio
async def test_query_watchlist(db_session: AsyncSession):
    user = await make_user(db_session)
    await make_watchlist_item(db_session, user_id=user.id, symbol="NVDA", market="us", sort_order=0)
    await make_watchlist_item(db_session, user_id=user.id, symbol="AAPL", market="us", sort_order=1)
    await db_session.commit()

    ch = _FakeCH([_bar(100.0, 10), _bar(105.0, 12)])
    rows = await q.query_watchlist(db_session, ch, user.id)  # type: ignore[arg-type]
    assert {r.symbol for r in rows} == {"NVDA", "AAPL"}
    assert all(r.price == 105.0 for r in rows)
    assert all(r.change_pct == pytest.approx(5.0) for r in rows)


@pytest.mark.asyncio
async def test_query_positions_spot_and_perp(db_session: AsyncSession):
    user = await make_user(db_session)
    crypto_acct = await make_virtual_account(db_session, user_id=user.id, market="crypto")
    us_acct = await make_virtual_account(db_session, user_id=user.id, market="us")

    # 现货活仓(美股)
    db_session.add(
        VirtualPosition(
            account_id=us_acct.id, symbol="NVDA", market="us",
            position_side=PositionSide.LONG,
            quantity=Decimal("10"), avg_entry_price=Decimal("100"),
        ),
    )
    # 永续活仓(加密 · 10x 多)
    db_session.add(
        VirtualPerpPosition(
            account_id=crypto_acct.id, symbol="BTCUSDT", side=PerpSide.LONG,
            margin_mode=MarginMode.ISOLATED, leverage=10,
            quantity=Decimal("0.5"), entry_price=Decimal("60000"),
            initial_margin=Decimal("3000"), maintenance_margin_rate=Decimal("0.005"),
            liquidation_price=Decimal("54500"),
        ),
    )
    await db_session.commit()

    rows = await q.query_positions(db_session, user.id)
    by_kind = {r.kind: r for r in rows}
    assert set(by_kind) == {"spot", "perp"}
    assert by_kind["spot"].symbol == "NVDA"
    assert by_kind["spot"].side == "long"
    assert by_kind["spot"].quantity == 10.0
    assert by_kind["perp"].symbol == "BTCUSDT"
    assert by_kind["perp"].leverage == 10
    assert by_kind["perp"].currency == "USDT"


@pytest.mark.asyncio
async def test_query_positions_empty_when_no_account(db_session: AsyncSession):
    user = await make_user(db_session)
    await db_session.commit()
    rows = await q.query_positions(db_session, user.id)
    assert rows == []


# ── detect_symbol_markets / symbol_exists(本刀:扫库判定 + 大小写模糊 + 同名双出)──────


class _ScanCH:
    """探测替身 · exists = 命中的 (market, canonical_symbol) 集合。"""

    def __init__(self, exists: set[tuple[str, str]]) -> None:
        self._exists = exists

    async def symbol_exists(
        self, market: str, symbol: str, instrument: str = "spot",  # noqa: ARG002
    ) -> bool:
        return (market, symbol) in self._exists


@pytest.mark.asyncio
async def test_detect_crypto_only():
    ch = _ScanCH({("crypto", "BTC/USDT")})
    assert await q.detect_symbol_markets(ch, "BTC") == [("crypto", "BTC/USDT")]  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_detect_us_only():
    ch = _ScanCH({("us", "NVDA")})
    assert await q.detect_symbol_markets(ch, "NVDA") == [("us", "NVDA")]  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_detect_lowercase_uppercased():
    """小写输入 → upper 后命中(问题②)。"""
    ch = _ScanCH({("us", "NVDA")})
    assert await q.detect_symbol_markets(ch, "nvda") == [("us", "NVDA")]  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_detect_same_name_both_crypto_first():
    """同名两库都中 → 都出 · 加密在前、美股在后。"""
    ch = _ScanCH({("crypto", "AAA/USDT"), ("us", "AAA")})
    assert await q.detect_symbol_markets(ch, "aaa") == [  # type: ignore[arg-type]
        ("crypto", "AAA/USDT"),
        ("us", "AAA"),
    ]


@pytest.mark.asyncio
async def test_detect_no_hit_empty():
    ch = _ScanCH(set())
    assert await q.detect_symbol_markets(ch, "ZZZ") == []  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_symbol_exists_limit1_query():
    """ClickHouseClient.symbol_exists:有行 True / 无行 False · SQL 带 SELECT 1 + LIMIT 1(不 SELECT *)。"""
    from app.services.clickhouse_client import ClickHouseClient

    captured: dict[str, Any] = {}

    class _Raw:
        def __init__(self, rows: list[Any]) -> None:
            self._rows = rows

        async def query(
            self, sql: str, parameters: dict[str, Any] | None = None,
        ) -> Any:
            captured["sql"] = sql
            captured["params"] = parameters
            return SimpleNamespace(result_rows=self._rows)

    has = SimpleNamespace(_client=_Raw([[1]]))
    assert await ClickHouseClient.symbol_exists(has, "us", "NVDA") is True
    assert "SELECT 1" in captured["sql"]
    assert "LIMIT 1" in captured["sql"]
    assert captured["params"]["s"] == "NVDA"

    empty = SimpleNamespace(_client=_Raw([]))
    assert await ClickHouseClient.symbol_exists(empty, "crypto", "ZZZ/USDT") is False


# ── 本刀:中文名搜索 + 轻量卡数据源 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_select_hk_spot_search_returns_rows():
    """select_hk_spot_search:查 hk_spot_snapshot · 子串匹配 · 成交额降序 · 返回 HkSpotRow。"""
    from app.services import clickhouse_hk_market as hk

    captured: dict[str, Any] = {}

    class _Raw:
        async def query(self, sql: str, parameters: dict[str, Any] | None = None) -> Any:
            captured["sql"] = sql
            captured["params"] = parameters
            return SimpleNamespace(result_rows=[
                ["00700", "腾讯控股", 380.0, 1.2, 4.5, 9.9e9, 1e7],
            ])

    rows = await hk.select_hk_spot_search(_Raw(), query="腾讯", limit=8)  # type: ignore[arg-type]
    assert len(rows) == 1
    assert rows[0].symbol == "00700"
    assert rows[0].name == "腾讯控股"
    assert "hk_spot_snapshot" in captured["sql"]
    assert "positionCaseInsensitive" in captured["sql"]
    assert captured["params"]["q"] == "腾讯"


@pytest.mark.asyncio
async def test_get_spot_lite_found_and_missing():
    """get_spot_lite:cn/hk 有行 → SpotLite(ts tz-aware) · 无行 → None · 非 cn/hk → None(不查)。"""
    from datetime import datetime

    naive_ts = datetime(2026, 6, 15, 4, 30)  # noqa: DTZ001 — 模拟 CH 读出的 naive ts

    class _Raw:
        def __init__(self, rows: list[Any]) -> None:
            self._rows = rows

        async def query(self, _sql: str, parameters: dict[str, Any] | None = None) -> Any:  # noqa: ARG002
            return SimpleNamespace(result_rows=self._rows)

    ch_has = SimpleNamespace(_client=_Raw([
        ["600519", "贵州茅台", 1688.0, -1.2, 4.56e9, naive_ts],
    ]))
    lite = await q.get_spot_lite(ch_has, "cn", "600519")  # type: ignore[arg-type]
    assert lite is not None
    assert lite.name == "贵州茅台"
    assert lite.ts.tzinfo is not None  # naive → 补 UTC

    ch_empty = SimpleNamespace(_client=_Raw([]))
    assert await q.get_spot_lite(ch_empty, "hk", "99999") is None  # type: ignore[arg-type]

    # 非 cn/hk → 直接 None,不应触碰 _client(给一个会炸的 _client 证明没查)
    ch_boom = SimpleNamespace(_client=object())
    assert await q.get_spot_lite(ch_boom, "us", "NVDA") is None  # type: ignore[arg-type]
    assert await q.get_spot_lite(ch_boom, "crypto", "BTC/USDT") is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_search_by_name_merges_cn_hk_by_amount(monkeypatch: pytest.MonkeyPatch):
    """search_by_name:并 cn+hk · 跨市场按成交额降序 · 截断 · NameHit(market,symbol,name)。"""
    from app.schemas.cn_market import CnSpotRow
    from app.schemas.hk_market import HkSpotRow
    from app.services import clickhouse_cn_market as cn
    from app.services import clickhouse_hk_market as hk

    def _row(cls: Any, sym: str, name: str, amount: float) -> Any:
        return cls(
            symbol=sym, name=name, last_price=1.0, change_pct=0.0,
            change_amount=0.0, amount=amount, volume=0.0,
        )

    async def _fake_cn(_client: Any, *, query: str, limit: int) -> Any:  # noqa: ARG001
        return [_row(CnSpotRow, "600036", "招商银行", 3e9)]

    async def _fake_hk(_client: Any, *, query: str, limit: int) -> Any:  # noqa: ARG001
        return [_row(HkSpotRow, "00700", "腾讯控股", 9e9)]

    monkeypatch.setattr(cn, "select_spot_search", _fake_cn)
    monkeypatch.setattr(hk, "select_hk_spot_search", _fake_hk)

    ch = SimpleNamespace(_client=object())
    hits = await q.search_by_name(ch, "银行", limit=8)  # type: ignore[arg-type]
    # 跨市场按成交额降序:腾讯 9e9(hk)在前,招行 3e9(cn)在后
    assert [(h.market, h.symbol) for h in hits] == [("hk", "00700"), ("cn", "600036")]


@pytest.mark.asyncio
async def test_search_by_name_empty_query():
    ch = SimpleNamespace(_client=object())
    assert await q.search_by_name(ch, "   ", limit=8) == []  # type: ignore[arg-type]
